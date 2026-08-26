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

                -- Controlled vocabulary for 分類 (series). A book references a row
                -- here by id, never a re-typed string — that is the whole point:
                -- a typo/case/spacing slip can no longer silently fork one series
                -- into two, and renaming a series fixes every book at once.
                -- `name` is the display form (preserves the user's original
                -- casing/spacing); `normalized_name` (trimmed, internal whitespace
                -- collapsed to one space, lowercased) is the UNIQUE key used for
                -- exact-duplicate resolution — see app.services.doujin_service
                -- normalize_series_name() / resolve_or_create_series().
                CREATE TABLE IF NOT EXISTS doujin_series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
                -- use the first page in natural order". series_id is NULL for "no
                -- series" (a first-class state, not an empty-string sentinel) or a
                -- FK into doujin_series (unenforced — no PRAGMA foreign_keys, same
                -- as the rest of this schema; the service layer validates it).
                -- 彩頁 (color_pages) was dropped 2026-08-26 (block-1 follow-up,
                -- carried no data yet) — do not re-add without a stated reason.
                --
                -- title/artist/circle: NO folder-name parsing (deliberately
                -- rejected 2026-08-26 — the folder name is a lossy rendering,
                -- not the source of truth; see app.services.doujin_meta_service).
                -- Precedence, computed at read time, never stored pre-merged:
                -- *_override (manual, wins, set by the user editing the field)
                -- > *_fetched (site-sourced, via app.providers.sites.nhentai
                -- today) > a plain default computed on the fly (folder name
                -- for title, '' for artist/circle) — not a column, since it
                -- needs no storage. All six columns are NULL until touched:
                -- override = "user never edited this field", fetched = "never
                -- fetched, or fetch didn't return this field".
                -- meta_fetch_status / meta_fetched_at / meta_source_url record
                -- the outcome of the last fetch ATTEMPT (ok / blocked /
                -- not_found / network_error / no_gallery_id / unsupported_source)
                -- even when it did not yield usable fields, so a failure is
                -- visible rather than indistinguishable from "never tried".
                -- page_count_fetched is a cross-check value only — it never
                -- feeds page_count/page_count_override, which stay purely
                -- derived from the local file count per the original spec.
                CREATE TABLE IF NOT EXISTS doujin_books (
                    folder_path TEXT PRIMARY KEY,
                    title_override TEXT,
                    artist_override TEXT,
                    circle_override TEXT,
                    title_fetched TEXT,
                    artist_fetched TEXT,
                    circle_fetched TEXT,
                    page_count_fetched INTEGER,
                    meta_fetch_status TEXT,
                    meta_fetched_at TEXT,
                    meta_source_url TEXT,
                    size_label TEXT DEFAULT '',
                    series_id INTEGER REFERENCES doujin_series(id),
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
                CREATE INDEX IF NOT EXISTS idx_doujin_books_series_id ON doujin_books(series_id);
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
