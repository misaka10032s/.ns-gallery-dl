from __future__ import annotations

from app.storage.db import init_db
from app.storage.repositories import history_repo


def load_history() -> dict[str, list[dict[str, str]]]:
    init_db()
    return history_repo.list_grouped()


def filter_by_history(urls: list[str]) -> list[str]:
    init_db()
    return [url for url in urls if not history_repo.has_success(url)]


def add_to_history(results: list[dict]) -> None:
    init_db()
    for result in results:
        history_repo.upsert_entry(
            url=result["url"],
            status=result.get("result", "failed"),
            source=result.get("source", "api"),
            provider=result.get("provider", "gallery-dl"),
            download_path=result.get("download_path", ""),
            meta=result.get("meta", {}),
            event_date=result.get("event_date"),
        )


def delete_from_history(event_date: str, url: str) -> bool:
    init_db()
    return history_repo.delete_entry(event_date, url)


def update_history_status(event_date: str, url: str, status: str) -> bool:
    init_db()
    return history_repo.update_status(event_date, url, status)
