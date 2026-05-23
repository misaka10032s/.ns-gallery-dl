from __future__ import annotations

import json
import threading
from queue import Queue

from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import JobRequest, QueueState
from app.services import download_service, history_service
from app.storage.db import init_db
from app.storage.repositories import jobs_repo


_queue: Queue[int] = Queue()
_worker_started = False
_worker_lock = threading.Lock()
_current_url: str | None = None
_display_urls: list[str] = []
_display_lock = threading.Lock()


def enqueue_requests(requests: list[JobRequest]) -> int:
    init_db()
    created = 0
    for request in requests:
        meta = dict(request.metadata or {})
        meta.setdefault("provider_mode", "forced" if request.provider else "auto")
        provider = request.provider or download_service.classify_provider(request.url)
        job_id = jobs_repo.create_job(
            url=download_service.normalize_url(request.url),
            provider=provider.value,
            source=request.source.value,
            meta=meta,
        )
        _queue.put(job_id)
        created += 1
    return created


def add_to_display(url: str) -> None:
    with _display_lock:
        _display_urls.append(url)


def remove_from_display(url: str) -> None:
    with _display_lock:
        try:
            _display_urls.remove(url)
        except ValueError:
            pass


def get_state() -> dict:
    init_db()
    pending = jobs_repo.list_pending_urls()
    with _display_lock:
        # Exclude _current_url from extras to avoid double-counting it in total
        # (it could still appear in `pending` if the DB hasn't been updated to
        # 'running' yet, but that window is tiny and self-corrects on next poll).
        extras = [url for url in _display_urls if url not in pending and url != _current_url]
        current_snap = _current_url
    snapshot = QueueState(
        current=current_snap,
        pending=pending + extras,
        total=len(pending) + len(extras) + (1 if current_snap else 0),
    )
    return {"current": snapshot.current, "pending": snapshot.pending, "total": snapshot.total}


def _run_job(job_id: int) -> None:
    global _current_url
    job = jobs_repo.get_job(job_id)
    if not job:
        return
    meta = json.loads(job.get("meta_json", "{}") or "{}")
    provider_mode = meta.get("provider_mode")
    if provider_mode is None:
        provider_mode = "forced" if job["provider"] == Provider.DIRECT_FILE.value else "auto"
        meta["provider_mode"] = provider_mode
    provider = None if provider_mode == "auto" else Provider(job["provider"])
    request = JobRequest(url=job["url"], provider=provider, source=JobSource(job["source"]), metadata=meta)
    jobs_repo.update_job(job_id, JobStatus.RUNNING.value, meta=meta)
    with _display_lock:
        _current_url = job["url"]
    tokens = _load_tokens()
    result = download_service.download_request(request, tokens=tokens)
    jobs_repo.update_job(
        job_id,
        result.status.value,
        download_path=result.download_path,
        error=result.error,
        meta=result.metadata or meta,
        provider=result.provider.value,
    )
    history_service.add_to_history([download_service.history_payload(job["url"], request.source, result)])


def _worker() -> None:
    global _current_url
    while True:
        job_id = _queue.get()
        try:
            _run_job(job_id)
        finally:
            with _display_lock:
                _current_url = None
            _queue.task_done()


def start_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker, daemon=True, name="ns-media-hub-worker")
        thread.start()
        _worker_started = True


def _load_tokens() -> dict:
    from app.services.token_service import load_tokens

    return load_tokens()
