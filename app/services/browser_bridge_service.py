from __future__ import annotations

from app.domain.enums import JobSource, Provider
from app.domain.jobs import JobRequest
from app.services import queue_service


def submit_urls(
    urls: list[str],
    source: JobSource = JobSource.API,
    metadata: dict | None = None,
    provider: Provider | None = None,
) -> int:
    requests = [JobRequest(url=url, source=source, metadata=dict(metadata or {}), provider=provider) for url in urls]
    return queue_service.enqueue_requests(requests)


def submit_requests(requests: list[JobRequest]) -> int:
    return queue_service.enqueue_requests(requests)
