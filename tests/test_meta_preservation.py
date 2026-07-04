"""
tests/test_meta_preservation.py

Regression: selected_urls must survive in the completed job's stored meta.

Review finding: _with_attempt_metadata built a fresh attempt-only dict,
discarding original meta keys like selected_urls.  The retry endpoint
(jobs.py:54-72) reads the stored meta — if selected_urls is gone, the
retry silently degrades a selection job into a full-page download.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import DownloadResult, JobRequest
from app.services.download_service import download_request


def _success_result() -> DownloadResult:
    """Minimal DownloadResult that gallery_provider returns for Bahamut (empty metadata)."""
    return DownloadResult(
        status=JobStatus.SUCCESS,
        provider=Provider.GALLERY_DL,
        domain="forum.gamer.com.tw",
        download_path="/download/gallery-dl/forum.gamer.com.tw",
        metadata={},
    )


class TestSelectedUrlsPreservation:
    """Original meta keys (e.g. selected_urls) must survive in result.metadata."""

    def test_selected_urls_present_after_completion(self):
        """
        A selection job (meta contains selected_urls) completes →
        result.metadata must still contain selected_urls.
        """
        selected = [
            "https://img.bahamut.com.tw/1.jpg",
            "https://img.bahamut.com.tw/2.png",
        ]
        request = JobRequest(
            url="https://forum.gamer.com.tw/Co.php?bsn=74934&sn=83404",
            provider=Provider.GALLERY_DL,
            source=JobSource.API,
            metadata={"selected_urls": selected},
        )

        with patch("app.services.download_service._download_with_provider", return_value=_success_result()):
            result = download_request(request, tokens={})

        assert "selected_urls" in result.metadata, (
            "selected_urls was discarded from result.metadata; "
            "retry endpoint would re-submit without it"
        )
        assert result.metadata["selected_urls"] == selected

    def test_attempt_keys_also_present(self):
        """Attempt tracking keys are added alongside the original meta keys."""
        request = JobRequest(
            url="https://forum.gamer.com.tw/Co.php?bsn=1&sn=2",
            provider=Provider.GALLERY_DL,
            source=JobSource.API,
            metadata={"selected_urls": ["https://img.example.com/1.jpg"]},
        )

        with patch("app.services.download_service._download_with_provider", return_value=_success_result()):
            result = download_request(request, tokens={})

        assert "attempted_providers" in result.metadata
        assert "selected_provider" in result.metadata
        assert "provider_mode" in result.metadata

    def test_retry_meta_includes_selected_urls(self):
        """
        Simulate the retry endpoint's meta-filtering logic (jobs.py:55-59):
        keys in {attempted_providers, attempts, selected_provider} are stripped,
        but selected_urls must survive so the retry re-submits as a selection job.
        """
        selected = ["https://img.example.com/1.jpg"]
        request = JobRequest(
            url="https://forum.gamer.com.tw/Co.php?bsn=74934&sn=1",
            provider=Provider.GALLERY_DL,
            source=JobSource.API,
            metadata={"selected_urls": selected},
        )

        with patch("app.services.download_service._download_with_provider", return_value=_success_result()):
            result = download_request(request, tokens={})

        # Replay the retry endpoint's filtering (jobs.py:55-59)
        retry_meta = {
            key: value
            for key, value in result.metadata.items()
            if key not in {"attempted_providers", "attempts", "selected_provider"}
        }

        assert "selected_urls" in retry_meta, (
            "After retry-endpoint filtering, selected_urls is gone — "
            "retry would fall back to full-page download"
        )
        assert retry_meta["selected_urls"] == selected
