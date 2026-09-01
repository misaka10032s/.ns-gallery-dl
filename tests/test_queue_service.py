"""
tests/test_queue_service.py

覆蓋 app/services/queue_service.py：
- enqueue_requests：建立 job 記錄、依序寫入內部佇列、回傳建立數量、provider_mode 判定。
- get_state：pending / current / total 快照組成（含 current 不被 pending 重複計算、
  display 額外項目排除已在 pending / current 中的重複）。
- _run_job：RUNNING → 終態的完整生命週期 —— DownloadResult 的 status/download_path/
  error/meta/provider 正確寫回 jobs_repo，並且 history_service.add_to_history() 收到
  download_service.history_payload() 產生的內容，含 Task 1 新增的 error 欄位。

下載本身一律 mock（不打真實網路、不呼叫真正的 gallery-dl/yt-dlp）。queue_service 的
_queue / _current_url / _display_urls 是 module-level 全域狀態，每個測試前後重置，
避免測試互相汙染（_worker_started 的背景執行緒故意不啟動 —— 直接呼叫 _run_job 讓行為
決定性、可斷言）。
"""
from __future__ import annotations

import json

import pytest

from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import DownloadResult, JobRequest
from app.services import queue_service
from app.storage.repositories import history_repo, jobs_repo


@pytest.fixture(autouse=True)
def _reset_queue_globals():
    def _drain():
        while not queue_service._queue.empty():
            queue_service._queue.get_nowait()
        queue_service._current_url = None
        queue_service._display_urls = []

    _drain()
    yield
    _drain()


class TestEnqueueRequests:
    def test_creates_one_job_per_request_and_returns_count(self, tmp_db):
        requests = [
            JobRequest(url="https://example.com/a"),
            JobRequest(url="https://example.com/b"),
        ]
        created = queue_service.enqueue_requests(requests)
        assert created == 2
        rows = jobs_repo.list_recent()
        assert {row["url"] for row in rows} == {"https://example.com/a", "https://example.com/b"}
        assert all(row["status"] == "queued" for row in rows)

    def test_enqueued_job_ids_land_on_the_internal_queue_in_order(self, tmp_db):
        queue_service.enqueue_requests([JobRequest(url="https://example.com/a")])
        queue_service.enqueue_requests([JobRequest(url="https://example.com/b")])
        rows = {row["url"]: row["id"] for row in jobs_repo.list_recent()}

        first_id = queue_service._queue.get_nowait()
        second_id = queue_service._queue.get_nowait()

        assert first_id == rows["https://example.com/a"]
        assert second_id == rows["https://example.com/b"]

    def test_forced_provider_marks_provider_mode_forced_and_persists_provider(self, tmp_db):
        queue_service.enqueue_requests([JobRequest(url="https://example.com/a", provider=Provider.YTDLP)])
        row = jobs_repo.list_recent()[0]
        meta = json.loads(row["meta_json"])
        assert meta["provider_mode"] == "forced"
        assert row["provider"] == Provider.YTDLP.value

    def test_auto_provider_classifies_from_url_and_marks_mode_auto(self, tmp_db):
        queue_service.enqueue_requests([JobRequest(url="https://www.pixiv.net/artworks/1")])
        row = jobs_repo.list_recent()[0]
        meta = json.loads(row["meta_json"])
        assert meta["provider_mode"] == "auto"
        assert row["provider"] == Provider.GALLERY_DL.value


class TestGetState:
    def test_empty_state(self, tmp_db):
        assert queue_service.get_state() == {"current": None, "pending": [], "total": 0}

    def test_pending_reflects_queued_jobs(self, tmp_db):
        queue_service.enqueue_requests([JobRequest(url="https://example.com/a")])
        state = queue_service.get_state()
        assert state["pending"] == ["https://example.com/a"]
        assert state["total"] == 1
        assert state["current"] is None

    def test_current_url_is_not_double_counted_against_pending(self, tmp_db):
        """Once a job moves to RUNNING (as _run_job does), it drops out of
        list_pending_urls(); get_state() must still count it exactly once via
        `current`, not lose it and not double-count it."""
        queue_service.enqueue_requests([JobRequest(url="https://example.com/a")])
        job_id = jobs_repo.list_recent()[0]["id"]
        jobs_repo.update_job(job_id, JobStatus.RUNNING.value)
        queue_service._current_url = "https://example.com/a"

        state = queue_service.get_state()

        assert state["current"] == "https://example.com/a"
        assert state["pending"] == []
        assert state["total"] == 1

    def test_display_extra_not_yet_in_db_is_still_counted(self, tmp_db):
        """A URL added via add_to_display() (queued to run but not yet
        persisted as a job row) must still show up in the snapshot."""
        queue_service.add_to_display("https://example.com/extra")
        state = queue_service.get_state()
        assert state["pending"] == ["https://example.com/extra"]
        assert state["total"] == 1

    def test_remove_from_display_is_idempotent_on_missing_url(self, tmp_db):
        # must not raise even though the URL was never added
        queue_service.remove_from_display("https://example.com/never-added")
        assert queue_service.get_state()["total"] == 0


class TestRunJob:
    def test_missing_job_is_a_noop(self, tmp_db):
        queue_service._run_job(999999)  # must not raise
        assert jobs_repo.get_job(999999) is None  # and it must not have fabricated a row either

    def test_success_updates_job_and_writes_history(self, tmp_db, monkeypatch):
        queue_service.enqueue_requests([JobRequest(url="https://example.com/a", source=JobSource.API)])
        job_id = jobs_repo.list_recent()[0]["id"]

        fake_result = DownloadResult(
            status=JobStatus.SUCCESS,
            provider=Provider.GALLERY_DL,
            domain="example.com",
            download_path="/download/example.com/a",
        )
        monkeypatch.setattr(queue_service.download_service, "download_request", lambda *a, **k: fake_result)
        monkeypatch.setattr(queue_service, "_load_tokens", lambda: {})

        queue_service._run_job(job_id)

        row = jobs_repo.get_job(job_id)
        assert row["status"] == JobStatus.SUCCESS.value
        assert row["download_path"] == "/download/example.com/a"
        assert row["error"] == ""

        entries = [item for items in history_repo.list_grouped().values() for item in items]
        assert len(entries) == 1
        assert entries[0]["url"] == "https://example.com/a"
        assert entries[0]["result"] == "success"

    def test_failure_persists_the_real_error_reason_to_job_and_history(self, tmp_db, monkeypatch):
        """The Task-1 payoff: a wnacg-shaped failure with a real error string
        must land BOTH on the job row's `error` column (JobsView.vue reads
        this directly) and inside the history entry's meta.error (Task 1's
        history_payload() addition) — not silently stay empty."""
        queue_service.enqueue_requests(
            [JobRequest(url="https://www.wnacg.com/photos-index-aid-1.html", source=JobSource.API)]
        )
        job_id = jobs_repo.list_recent()[0]["id"]

        error_text = "CONFIG API（主線路）取得下載連結失敗: 403 Client Error；備用線路（Server 2）也找不到下載連結"
        fake_result = DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.GALLERY_DL,
            domain="wnacg.com",
            download_path="",
            error=error_text,
        )
        monkeypatch.setattr(queue_service.download_service, "download_request", lambda *a, **k: fake_result)
        monkeypatch.setattr(queue_service, "_load_tokens", lambda: {})

        queue_service._run_job(job_id)

        row = jobs_repo.get_job(job_id)
        assert row["status"] == JobStatus.FAILED.value
        assert row["error"] == error_text

        entries = [item for items in history_repo.list_grouped().values() for item in items]
        assert len(entries) == 1
        assert entries[0]["result"] == "failed"
        assert entries[0]["meta"]["error"] == error_text

    def test_current_url_is_cleared_by_the_worker_finally_block_semantics(self, tmp_db, monkeypatch):
        """_run_job itself does not clear _current_url (the _worker() loop's
        `finally` does) — pin that division of responsibility so a future
        change doesn't silently clear it twice or never."""
        queue_service.enqueue_requests([JobRequest(url="https://example.com/a")])
        job_id = jobs_repo.list_recent()[0]["id"]
        fake_result = DownloadResult(status=JobStatus.SUCCESS, provider=Provider.GALLERY_DL, domain="example.com")
        monkeypatch.setattr(queue_service.download_service, "download_request", lambda *a, **k: fake_result)
        monkeypatch.setattr(queue_service, "_load_tokens", lambda: {})

        queue_service._run_job(job_id)

        assert queue_service._current_url == "https://example.com/a"
