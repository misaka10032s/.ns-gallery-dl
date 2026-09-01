"""
tests/test_history_service.py

覆蓋 app/services/history_service.py（薄封裝）與其底層
app/storage/repositories/history_repo.py 的實際持久化行為（真的寫進 SQLite 再讀出來，
不只是斷言記憶體物件）：
- add_to_history → load_history 的往返（依 event_date 分組）。
- filter_by_history：只有 status='success' 的紀錄才會排除重下；failed 紀錄不得攔下重試。
- update_history_status / delete_from_history 的狀態轉換與找不到時回傳 False。
- upsert 語意（history_entries 為 UNIQUE(url)）：同一 URL 再次寫入是覆蓋，不是疊加。
- Task 1 payoff：download_service.history_payload() 產出的 meta.error 欄位，經過
  add_to_history() 寫入 SQLite meta_json 後，load_history() 讀回來仍然完整 —— 證明
  wnacg 的失敗原因真的走得到歷史紀錄，而不只是在記憶體裡看起來對。
"""
from __future__ import annotations

from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import DownloadResult
from app.services import download_service, history_service


def _all_entries() -> list[dict]:
    grouped = history_service.load_history()
    return [item for items in grouped.values() for item in items]


class TestAddAndLoadHistory:
    def test_round_trip_basic_fields(self, tmp_db):
        history_service.add_to_history(
            [
                {
                    "url": "https://example.com/a",
                    "result": "success",
                    "source": "api",
                    "provider": "gallery-dl",
                    "download_path": "/download/a",
                    "meta": {"downloaded": 3, "skipped": 0},
                }
            ]
        )
        entries = _all_entries()
        assert len(entries) == 1
        assert entries[0]["url"] == "https://example.com/a"
        assert entries[0]["result"] == "success"
        assert entries[0]["provider"] == "gallery-dl"
        assert entries[0]["meta"] == {"downloaded": 3, "skipped": 0}

    def test_grouped_by_event_date(self, tmp_db):
        history_service.add_to_history(
            [
                {
                    "url": "https://example.com/a",
                    "result": "success",
                    "source": "api",
                    "provider": "gallery-dl",
                    "event_date": "2026-01-01",
                },
                {
                    "url": "https://example.com/b",
                    "result": "success",
                    "source": "api",
                    "provider": "gallery-dl",
                    "event_date": "2026-01-02",
                },
            ]
        )
        grouped = history_service.load_history()
        assert set(grouped.keys()) == {"2026-01-01", "2026-01-02"}
        assert grouped["2026-01-01"][0]["url"] == "https://example.com/a"
        assert grouped["2026-01-02"][0]["url"] == "https://example.com/b"

    def test_reupserting_same_url_overwrites_not_duplicates(self, tmp_db):
        """history_entries has UNIQUE(url) — a last-write-wins store per
        history_repo.upsert_entry's own docstring, not an append-only log."""
        history_service.add_to_history(
            [{"url": "https://example.com/a", "result": "failed", "source": "api", "provider": "gallery-dl"}]
        )
        history_service.add_to_history(
            [{"url": "https://example.com/a", "result": "success", "source": "api", "provider": "gallery-dl"}]
        )
        entries = _all_entries()
        assert len(entries) == 1
        assert entries[0]["result"] == "success"


class TestFilterByHistory:
    def test_urls_without_any_history_pass_through(self, tmp_db):
        assert history_service.filter_by_history(["https://example.com/new"]) == ["https://example.com/new"]

    def test_url_with_success_entry_is_filtered_out(self, tmp_db):
        history_service.add_to_history(
            [{"url": "https://example.com/done", "result": "success", "source": "api", "provider": "gallery-dl"}]
        )
        result = history_service.filter_by_history(["https://example.com/done", "https://example.com/new"])
        assert result == ["https://example.com/new"]

    def test_url_with_only_a_failed_entry_still_passes_through(self, tmp_db):
        """A failed entry must NOT suppress a retry — only a recorded success does."""
        history_service.add_to_history(
            [{"url": "https://example.com/retry", "result": "failed", "source": "api", "provider": "gallery-dl"}]
        )
        assert history_service.filter_by_history(["https://example.com/retry"]) == ["https://example.com/retry"]


class TestUpdateAndDelete:
    def test_update_history_status_changes_status(self, tmp_db):
        history_service.add_to_history(
            [
                {
                    "url": "https://example.com/a",
                    "result": "failed",
                    "source": "api",
                    "provider": "gallery-dl",
                    "event_date": "2026-01-01",
                }
            ]
        )
        assert history_service.update_history_status("2026-01-01", "https://example.com/a", "success") is True
        assert _all_entries()[0]["result"] == "success"

    def test_update_history_status_returns_false_for_missing_entry(self, tmp_db):
        assert history_service.update_history_status("2026-01-01", "https://example.com/missing", "success") is False

    def test_delete_from_history_removes_entry(self, tmp_db):
        history_service.add_to_history(
            [
                {
                    "url": "https://example.com/a",
                    "result": "success",
                    "source": "api",
                    "provider": "gallery-dl",
                    "event_date": "2026-01-01",
                }
            ]
        )
        assert history_service.delete_from_history("2026-01-01", "https://example.com/a") is True
        assert _all_entries() == []

    def test_delete_from_history_returns_false_for_missing_entry(self, tmp_db):
        assert history_service.delete_from_history("2026-01-01", "https://example.com/missing") is False


class TestErrorFieldRoundTrip:
    """Task 1: DownloadResult.error must survive the full path —
    download_service.history_payload() -> history_service.add_to_history() ->
    SQLite meta_json -> history_service.load_history() — not just look right
    in-memory before it is ever persisted."""

    def test_wnacg_failure_error_survives_the_db_round_trip(self, tmp_db):
        result = DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.GALLERY_DL,
            domain="wnacg.com",
            download_path="",
            error="檔案下載失敗: 403 Client Error",
        )
        payload = download_service.history_payload(
            "https://www.wnacg.com/photos-index-aid-1.html", JobSource.API, result
        )
        history_service.add_to_history([payload])

        entries = _all_entries()
        assert len(entries) == 1
        assert entries[0]["meta"]["error"] == "檔案下載失敗: 403 Client Error"

    def test_success_result_carries_no_error_key(self, tmp_db):
        result = DownloadResult(status=JobStatus.SUCCESS, provider=Provider.GALLERY_DL, domain="wnacg.com", download_path="/x")
        payload = download_service.history_payload(
            "https://www.wnacg.com/photos-index-aid-2.html", JobSource.API, result
        )
        history_service.add_to_history([payload])

        entries = _all_entries()
        assert "error" not in entries[0]["meta"]

    def test_attempts_metadata_error_does_not_get_overwritten_by_top_level_error(self, tmp_db):
        """download_request() (a different code path than the direct
        history_payload() call above) already threads result.error into
        metadata['attempts'][-1]['error'] via _with_attempt_metadata — the new
        top-level meta['error'] must not clobber a differently-shaped existing
        'error' key some other caller may have set on purpose."""
        result = DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.GALLERY_DL,
            domain="wnacg.com",
            download_path="",
            error="檔案下載失敗: timeout",
            metadata={"error": "custom-caller-supplied-value", "attempts": [{"provider": "gallery-dl", "error": "檔案下載失敗: timeout"}]},
        )
        payload = download_service.history_payload(
            "https://www.wnacg.com/photos-index-aid-3.html", JobSource.API, result
        )
        history_service.add_to_history([payload])

        entries = _all_entries()
        assert entries[0]["meta"]["error"] == "custom-caller-supplied-value"
        assert entries[0]["meta"]["attempts"][0]["error"] == "檔案下載失敗: timeout"
