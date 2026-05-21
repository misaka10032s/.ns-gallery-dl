from __future__ import annotations

from app.domain.enums import JobSource
from app.domain.jobs import JobRequest
from app.services.queue_service import add_to_display, get_state, remove_from_display, start_worker
from app.services.queue_service import enqueue_requests as _enqueue_requests


def enqueue(links: list[str]) -> None:
    _enqueue_requests([JobRequest(url=link, source=JobSource.API) for link in links])


__all__ = ["add_to_display", "enqueue", "get_state", "remove_from_display", "start_worker"]
