from __future__ import annotations

from datetime import datetime

from app.storage.db import execute, fetch_all, fetch_one


def upsert_cookie(domain: str, provider: str, file_name: str, file_path: str, source: str = "scan", notes: str = "") -> None:
    execute(
        """
        INSERT INTO cookie_entries (domain, provider, file_name, file_path, source, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(domain, provider, file_path) DO UPDATE SET
            file_name = excluded.file_name,
            source = excluded.source,
            notes = excluded.notes,
            updated_at = excluded.updated_at
        """,
        (
            domain,
            provider,
            file_name,
            file_path,
            source,
            notes,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def list_cookies() -> list[dict]:
    rows = fetch_all(
        """
        SELECT domain, provider, file_name, file_path, source, notes, updated_at
        FROM cookie_entries
        ORDER BY domain, provider, file_name
        """
    )
    return [dict(row) for row in rows]


def clear_scanned_entries() -> None:
    execute("DELETE FROM cookie_entries WHERE source = 'scan'")


def count_cookies() -> int:
    row = fetch_one("SELECT COUNT(*) AS count FROM cookie_entries")
    return int(row["count"]) if row else 0


def find_cookie(domain: str, provider: str | None = None) -> str | None:
    if provider:
        row = fetch_one(
            """
            SELECT file_path FROM cookie_entries
            WHERE domain = ? AND provider IN (?, 'shared')
            ORDER BY CASE provider WHEN ? THEN 0 ELSE 1 END, updated_at DESC
            LIMIT 1
            """,
            (domain, provider, provider),
        )
    else:
        row = fetch_one(
            """
            SELECT file_path FROM cookie_entries
            WHERE domain = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (domain,),
        )
    return row["file_path"] if row else None
