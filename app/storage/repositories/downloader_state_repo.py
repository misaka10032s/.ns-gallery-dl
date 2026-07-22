from __future__ import annotations

from app.storage.db import execute, fetch_one


def get_state(package: str) -> dict | None:
    row = fetch_one(
        "SELECT package, last_checked_version, last_checked_at FROM downloader_state WHERE package = ?",
        (package,),
    )
    return dict(row) if row else None


def set_state(package: str, version: str, checked_at: str) -> None:
    execute(
        """
        INSERT INTO downloader_state (package, last_checked_version, last_checked_at)
        VALUES (?, ?, ?)
        ON CONFLICT(package) DO UPDATE SET
            last_checked_version = excluded.last_checked_version,
            last_checked_at = excluded.last_checked_at
        """,
        (package, version, checked_at),
    )
