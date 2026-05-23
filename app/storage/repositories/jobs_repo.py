from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlparse

from app.storage.db import connection, execute, fetch_all, fetch_one, insert


def _domain_for_url(url: str) -> str:
    if url.startswith("ytdlp://"):
        url = url[len("ytdlp://") :]
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
    try:
        return (urlparse(url).hostname or "unknown").lower()
    except ValueError:
        return "unknown"


def create_job(url: str, provider: str, source: str, meta: dict | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    return insert(
        """
        INSERT INTO jobs (url, provider, source, status, domain, download_path, meta_json, error, created_at, updated_at)
        VALUES (?, ?, ?, 'queued', ?, '', ?, '', ?, ?)
        """,
        (url, provider, source, _domain_for_url(url), json.dumps(meta or {}, ensure_ascii=False), now, now),
    )


def get_job(job_id: int) -> dict | None:
    row = fetch_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if not row:
        return None
    return dict(row)


def update_job(
    job_id: int,
    status: str,
    download_path: str = "",
    error: str = "",
    meta: dict | None = None,
    provider: str | None = None,
) -> None:
    # Read current row and write update in a single connection so the two
    # operations are atomic and don't open an extra round-trip.
    with connection() as conn:
        current = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        current = dict(current) if current else {}
        meta_payload = json.dumps(
            meta if meta is not None else json.loads(current.get("meta_json", "{}")),
            ensure_ascii=False,
        )
        conn.execute(
            """
            UPDATE jobs
            SET provider = ?, status = ?, download_path = ?, error = ?, meta_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                provider or current.get("provider", ""),
                status,
                download_path,
                error,
                meta_payload,
                datetime.now().isoformat(timespec="seconds"),
                job_id,
            ),
        )


def list_recent(limit: int = 100) -> list[dict]:
    rows = fetch_all(
        """
        SELECT * FROM jobs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(row) for row in rows]


def counts_by_status() -> dict[str, int]:
    rows = fetch_all(
        """
        SELECT status, COUNT(*) AS count
        FROM jobs
        GROUP BY status
        """
    )
    return {row["status"]: int(row["count"]) for row in rows}


def list_pending_urls() -> list[str]:
    rows = fetch_all("SELECT url FROM jobs WHERE status = 'queued' ORDER BY id ASC")
    return [row["url"] for row in rows]
