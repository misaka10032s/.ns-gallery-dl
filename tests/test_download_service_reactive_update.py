"""
tests/test_download_service_reactive_update.py

download_service.download_request() — on-error reactive downloader-update hook:
- Only triggers on a "stale extractor"-classified FAILED error.
- Retries the SAME download once if updater_service.maybe_reactive_update() signals
  a version change (retried=True).
- HARD CAP: at most one auto-update-retry per job, even across multiple provider
  candidates in the same job (e.g. a MULTI_PROVIDER_DOMAINS url).
- Leaves non-stale-extractor failures completely untouched (no updater call at all).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import DownloadResult, JobRequest
from app.services.download_service import download_request


def _result(status: Provider, provider: Provider, error: str = "") -> DownloadResult:
    return DownloadResult(status=status, provider=provider, domain="youtube.com", download_path="", error=error)


class TestReactiveUpdateRetry:
    def test_non_stale_extractor_failure_never_calls_updater(self):
        request = JobRequest(url="https://www.youtube.com/watch?v=abc", source=JobSource.API)
        failed = _result(JobStatus.FAILED, Provider.YTDLP, error="HTTP Error 403: Forbidden")

        with (
            patch("app.services.download_service._download_with_provider", return_value=failed),
            patch("app.services.download_service.updater_service.maybe_reactive_update") as mock_update,
        ):
            result = download_request(request, tokens={})

        mock_update.assert_not_called()
        assert result.status == JobStatus.FAILED
        assert result.error == "HTTP Error 403: Forbidden"

    def test_stale_extractor_failure_retries_once_on_version_change(self):
        request = JobRequest(url="https://www.youtube.com/watch?v=abc", source=JobSource.API)
        failed = _result(JobStatus.FAILED, Provider.YTDLP, error="ERROR: Unable to extract video data")
        succeeded = _result(JobStatus.SUCCESS, Provider.YTDLP)

        with (
            patch("app.services.download_service._download_with_provider", side_effect=[failed, succeeded]) as mock_download,
            patch(
                "app.services.download_service.updater_service.maybe_reactive_update",
                return_value={"retried": True, "changed": True, "message": ""},
            ) as mock_update,
        ):
            result = download_request(request, tokens={})

        assert mock_download.call_count == 2
        mock_update.assert_called_once_with(Provider.YTDLP.value)
        assert result.status == JobStatus.SUCCESS
        assert result.metadata["attempts"][-1]["auto_update_retry"] is True

    def test_stale_extractor_failure_already_latest_does_not_retry(self):
        request = JobRequest(url="https://www.youtube.com/watch?v=abc", source=JobSource.API)
        failed = _result(JobStatus.FAILED, Provider.YTDLP, error="ERROR: Cannot parse data")

        with (
            patch("app.services.download_service._download_with_provider", return_value=failed) as mock_download,
            patch(
                "app.services.download_service.updater_service.maybe_reactive_update",
                return_value={"retried": False, "changed": False, "message": "已是最新 yt-dlp 2024.06.01，仍失敗"},
            ),
        ):
            result = download_request(request, tokens={})

        # Not retried → _download_with_provider called only once for the single candidate.
        mock_download.assert_called_once()
        assert result.status == JobStatus.FAILED
        assert result.error == "已是最新 yt-dlp 2024.06.01，仍失敗"

    def test_hard_cap_one_retry_per_job_across_multiple_provider_candidates(self):
        """
        A MULTI_PROVIDER_DOMAINS url (facebook.com) tries [GALLERY_DL, YTDLP] in
        sequence. Both fail with a stale-extractor-looking error — the updater must
        be consulted at most ONCE for the whole job, not once per provider.
        """
        request = JobRequest(url="https://www.facebook.com/video/12345", source=JobSource.API)
        failed_gallery = _result(JobStatus.FAILED, Provider.GALLERY_DL, error="unable to extract post")
        failed_ytdlp = _result(JobStatus.FAILED, Provider.YTDLP, error="ERROR: Unable to extract video data")

        with (
            patch(
                "app.services.download_service._download_with_provider",
                side_effect=[failed_gallery, failed_ytdlp],
            ) as mock_download,
            patch(
                "app.services.download_service.updater_service.maybe_reactive_update",
                return_value={"retried": False, "changed": False, "message": "已是最新，仍失敗"},
            ) as mock_update,
        ):
            result = download_request(request, tokens={})

        assert mock_download.call_count == 2  # one per provider candidate, no extra retry
        mock_update.assert_called_once()  # consulted only once for the whole job
        assert result.status == JobStatus.FAILED
