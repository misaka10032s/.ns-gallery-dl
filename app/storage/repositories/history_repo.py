from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlparse

from app.storage.db import fetch_all, fetch_one, execute


def _domain_for_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "unknown").lower()
    except ValueError:
        return "unknown"


def list_grouped(limit: int = 5000) -> dict[str, list[dict[str, str]]]:
    rows = fetch_all(
        """
        SELECT event_date, url, status, domain, provider, source, download_path, meta_json
        FROM history_entries
        ORDER BY event_date DESC, updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["event_date"], []).append(
            {
                "url": row["url"],
                "result": row["status"],
                "domain": row["domain"],
                "provider": row["provider"],
                "source": row["source"],
                "download_path": row["download_path"],
                "meta": json.loads(row["meta_json"] or "{}"),
            }
        )
    return grouped


def has_success(url: str) -> bool:
    row = fetch_one(
        "SELECT 1 FROM history_entries WHERE url = ? AND status = 'success' LIMIT 1",
        (url,),
    )
    return row is not None


def upsert_entry(
    url: str,
    status: str,
    source: str,
    provider: str,
    download_path: str = "",
    meta: dict | None = None,
    event_date: str | None = None,
) -> None:
    # history_entries uses UNIQUE(url) — this is a last-write-wins store, not an audit log.
    # Re-downloading the same URL overwrites the previous record with the latest outcome.
    event_date = event_date or datetime.now().strftime("%Y-%m-%d")
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    domain = _domain_for_url(url)
    execute(
        """
        INSERT INTO history_entries
        (url, event_date, status, domain, source, provider, download_path, meta_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            event_date = excluded.event_date,
            status = excluded.status,
            domain = excluded.domain,
            source = excluded.source,
            provider = excluded.provider,
            download_path = excluded.download_path,
            meta_json = excluded.meta_json,
            updated_at = excluded.updated_at
        """,
        (
            url,
            event_date,
            status,
            domain,
            source,
            provider,
            download_path,
            meta_json,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def delete_entry(event_date: str, url: str) -> bool:
    before = fetch_one(
        "SELECT id FROM history_entries WHERE event_date = ? AND url = ?",
        (event_date, url),
    )
    if not before:
        return False
    execute("DELETE FROM history_entries WHERE event_date = ? AND url = ?", (event_date, url))
    return True


def update_status(event_date: str, url: str, status: str) -> bool:
    before = fetch_one(
        "SELECT id FROM history_entries WHERE event_date = ? AND url = ?",
        (event_date, url),
    )
    if not before:
        return False
    execute(
        """
        UPDATE history_entries
        SET status = ?, updated_at = ?
        WHERE event_date = ? AND url = ?
        """,
        (status, datetime.now().isoformat(timespec="seconds"), event_date, url),
    )
    return True


def summary(limit_domains: int = 10, limit_days: int = 14) -> dict:
    totals_row = fetch_one(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
            SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) AS skipped_count
        FROM history_entries
        """
    )
    domain_rows = fetch_all(
        """
        SELECT domain, COUNT(*) AS count
        FROM history_entries
        GROUP BY domain
        ORDER BY count DESC, domain ASC
        LIMIT ?
        """,
        (limit_domains,),
    )
    day_rows = fetch_all(
        """
        SELECT event_date, COUNT(*) AS count
        FROM history_entries
        GROUP BY event_date
        ORDER BY event_date DESC
        LIMIT ?
        """,
        (limit_days,),
    )
    total = int(totals_row["total"]) if totals_row and totals_row["total"] is not None else 0
    success = int(totals_row["success_count"]) if totals_row and totals_row["success_count"] is not None else 0
    failed = int(totals_row["failed_count"]) if totals_row and totals_row["failed_count"] is not None else 0
    skipped = int(totals_row["skipped_count"]) if totals_row and totals_row["skipped_count"] is not None else 0
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "top_domains": [{"domain": row["domain"], "count": int(row["count"])} for row in domain_rows],
        "recent_days": [{"date": row["event_date"], "count": int(row["count"])} for row in day_rows],
    }
