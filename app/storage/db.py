from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.config.paths import DATA_DIR, DB_FILE, LEGACY_HISTORY_FILE


_INIT_LOCK = threading.Lock()
_READY = False


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL 模式允許讀寫並發，避免多執行緒下的 "database is locked" 錯誤
    conn.execute("PRAGMA journal_mode=WAL")
    # WAL alone does not make a second writer wait — without a busy timeout, two
    # connections colliding on the same write instant raise "database is locked"
    # immediately instead of one waiting briefly for the other. 5s is generous for
    # this app's short, single-row writes.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def execute(query: str, params: tuple[Any, ...] = ()) -> None:
    with connection() as conn:
        conn.execute(query, params)


def insert(query: str, params: tuple[Any, ...] = ()) -> int:
    with connection() as conn:
        cursor = conn.execute(query, params)
        return int(cursor.lastrowid)


def execute_many(query: str, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    with connection() as conn:
        conn.executemany(query, rows)


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with connection() as conn:
        return conn.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with connection() as conn:
        return conn.execute(query, params).fetchall()


def init_db() -> None:
    global _READY
    if _READY:
        return
    with _INIT_LOCK:
        if _READY:
            return
        with connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    download_path TEXT DEFAULT '',
                    meta_json TEXT DEFAULT '{}',
                    error TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS history_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    -- UNIQUE(url): this table stores the *latest* known status per URL,
                    -- not a full append-only log. Each upsert overwrites the previous record.
                    url TEXT NOT NULL UNIQUE,
                    event_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    source TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    download_path TEXT DEFAULT '',
                    meta_json TEXT DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cookie_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    source TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    updated_at TEXT NOT NULL,
                    UNIQUE(domain, provider, file_path)
                );

                -- Reactive downloader-update guard state (app/services/updater_service.py):
                -- one row per pip package (app.config.downloaders.DOWNLOADER_PACKAGES),
                -- tracking the version we last confirmed via a stale-extractor check so a
                -- repeated failure within the cooldown doesn't re-trigger a pointless update.
                CREATE TABLE IF NOT EXISTS downloader_state (
                    package TEXT PRIMARY KEY,
                    last_checked_version TEXT DEFAULT '',
                    last_checked_at TEXT DEFAULT ''
                );

                -- Doujinshi (本子) book metadata — one row per book FOLDER (path
                -- relative to DOWNLOAD_DIR, e.g. "wnacg/100873_[...] さなえの湯(泡)").
                -- Rows are created LAZILY: a folder under a doujinshi-mode source
                -- (app.config.gallery_modes) is a book whether or not the user has
                -- ever touched it — no pre-scan populates this table up front.
                -- page_count is a cache of the on-disk page count, refreshed every
                -- time the row is touched; page_count_override, when set (NOT
                -- NULL), wins over it for display. cover_page is the filename of
                -- the user-chosen cover page within the folder; '' means "auto —
                -- use the first page in natural order".
                CREATE TABLE IF NOT EXISTS doujin_books (
                    folder_path TEXT PRIMARY KEY,
                    title TEXT DEFAULT '',
                    artist TEXT DEFAULT '',
                    circle TEXT DEFAULT '',
                    size_label TEXT DEFAULT '',
                    color_pages TEXT DEFAULT '',
                    series TEXT DEFAULT '',
                    purchase_state TEXT NOT NULL DEFAULT 'not_purchased',
                    page_count INTEGER NOT NULL DEFAULT 0,
                    page_count_override INTEGER,
                    cover_page TEXT DEFAULT '',
                    last_page_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                -- Plural links per book (N網/P網/購買網...). folder_path is not
                -- enforced as a hard FK (no PRAGMA foreign_keys — matches the rest
                -- of this schema) because a link can be added the same lazy way a
                -- book row is created; the service layer always ensures the parent
                -- doujin_books row exists first.
                CREATE TABLE IF NOT EXISTS doujin_book_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book TEXT NOT NULL REFERENCES doujin_books(folder_path),
                    label TEXT DEFAULT '',
                    url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(book, url)
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_status_id ON jobs(status, id);
                CREATE INDEX IF NOT EXISTS idx_history_event_date ON history_entries(event_date DESC);
                CREATE INDEX IF NOT EXISTS idx_history_domain ON history_entries(domain);
                CREATE INDEX IF NOT EXISTS idx_cookies_domain_provider ON cookie_entries(domain, provider);
                CREATE INDEX IF NOT EXISTS idx_doujin_links_book ON doujin_book_links(book);
                """
            )
        migrate_legacy_history()
        _READY = True


def migrate_legacy_history() -> None:
    if not LEGACY_HISTORY_FILE.exists():
        return
    count_row = fetch_one("SELECT COUNT(*) AS count FROM history_entries")
    if count_row and count_row["count"] > 0:
        return

    try:
        payload = json.loads(LEGACY_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    rows: list[tuple[Any, ...]] = []
    now = datetime.now().isoformat(timespec="seconds")
    for event_date, entries in payload.items():
        for entry in entries:
            url = (entry or {}).get("url")
            status = (entry or {}).get("result", "failed")
            if not url:
                continue
            try:
                domain = url.split("/")[2].lower()
            except IndexError:
                domain = "unknown"
            rows.append(
                (
                    url,
                    event_date,
                    status,
                    domain,
                    "legacy",
                    "gallery-dl",
                    "",
                    "{}",
                    now,
                )
            )

    execute_many(
        """
        INSERT OR IGNORE INTO history_entries
        (url, event_date, status, domain, source, provider, download_path, meta_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
