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

                CREATE INDEX IF NOT EXISTS idx_jobs_status_id ON jobs(status, id);
                CREATE INDEX IF NOT EXISTS idx_history_event_date ON history_entries(event_date DESC);
                CREATE INDEX IF NOT EXISTS idx_history_domain ON history_entries(domain);
                CREATE INDEX IF NOT EXISTS idx_cookies_domain_provider ON cookie_entries(domain, provider);
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
