"""
tests/test_gallery_dl_auth_retry.py

app.providers.gallery_dl.provider.download() — the retry/cooldown restructure
from dispatch item 1 (phase 1a):
  - A domain already in its auth-failure cooldown is never even probed —
    zero credentialed requests for that job.
  - An AUTH-classified failure (app.domain.auth_failure.classify) stops the
    whole retry loop immediately (ONE request, not up to
    max_retries * len(cookie_candidates) — previously up to 5*2=10) and arms
    the cooldown (app.domain.auth_cooldown) for the domain.
  - A NOT_AUTH / INDETERMINATE failure keeps the EXISTING retry behaviour
    completely unchanged (regression guard against over-applying the new
    early-stop rule).
  - Every FAILED result — early-stop or exhausted-retries — carries an
    `auth_classification` metadata key, and its `error` text has been routed
    through app.domain.error_sanitizer before reaching the caller.

subprocess is ALWAYS mocked — no real gallery-dl process is spawned.
"""
from __future__ import annotations

from unittest.mock import patch

from app.domain import auth_failure
from app.providers.gallery_dl import provider as gallery_provider


class TestCooldownSkipsEveryRequest:
    def test_domain_in_cooldown_never_calls_simulate(self, tmp_path):
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch(
                "app.providers.gallery_dl.provider.auth_cooldown.in_cooldown",
                return_value=(True, "2026-09-02T18:00:00"),
            ),
            patch("app.providers.gallery_dl.provider._simulate") as mock_simulate,
        ):
            result = gallery_provider.download("https://danbooru.donmai.us/posts/1", tokens={})

        mock_simulate.assert_not_called()
        assert result.status.value == "failed"
        assert "danbooru.donmai.us" in result.error
        assert "2026-09-02T18:00:00" in result.error
        assert result.metadata["auth_classification"] == auth_failure.AUTH
        assert result.metadata["auth_cooldown"] is True


class TestAuthClassifiedFailureStopsAtOneAttempt:
    def test_simulate_auth_failure_stops_after_one_call_and_arms_cooldown(self, tmp_path):
        auth_error = "[twitter][error] AuthRequired: Protected Tweet"
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.gallery_dl.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.gallery_dl.provider.auth_cooldown.record_auth_failure") as mock_record,
            patch("app.providers.gallery_dl.provider.resolve_cookie_file", return_value="C:/cookies/x.com.txt"),
            patch("app.providers.gallery_dl.provider._probe_user_root", side_effect=lambda url, env, domain, root, candidates: root),
            patch("app.providers.gallery_dl.provider._simulate", return_value=(1, 0, auth_error)) as mock_simulate,
        ):
            result = gallery_provider.download(
                "https://x.com/someone/status/1", tokens={}, max_retries=5, retry_delay=0
            )

        # x.com has TWO cookie candidates ([None, cookie_path]) and 5 max
        # retries — the OLD behaviour would call _simulate up to 5*2=10
        # times. The new one-attempt-and-stop rule means exactly ONE call.
        assert mock_simulate.call_count == 1
        mock_record.assert_called_once_with("x.com", auth_error)
        assert result.status.value == "failed"
        assert result.metadata["auth_classification"] == auth_failure.AUTH

    def test_download_stage_auth_failure_also_stops_immediately(self, tmp_path):
        """The failure can also surface at the _gallery_download stage (after
        a successful --simulate probe) — same one-attempt-and-stop rule."""
        auth_error = "[instagram][error] HTTP redirect to login page (https://www.instagram.com/accounts/login/)"
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.gallery_dl.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.gallery_dl.provider.auth_cooldown.record_auth_failure") as mock_record,
            patch("app.providers.gallery_dl.provider._simulate", return_value=(0, 3, "")),
            patch("app.providers.gallery_dl.provider._gallery_download", return_value=("failed", 0, 0, auth_error)) as mock_dl,
        ):
            result = gallery_provider.download(
                "https://www.instagram.com/p/abc/", tokens={}, max_retries=5, retry_delay=0
            )

        assert mock_dl.call_count == 1
        mock_record.assert_called_once_with("instagram.com", auth_error)
        assert result.metadata["auth_classification"] == auth_failure.AUTH


class TestNonAuthFailureKeepsExistingRetryBehaviour:
    def test_not_auth_error_retries_up_to_max_retries(self, tmp_path):
        """Regression guard: a NOT_AUTH-classified failure (here, a plain
        HTTP 500 — a server error, not a credential problem) must retry
        EXACTLY as before this change — the new early-stop rule must never
        fire for it."""
        server_error = "[danbooru][error] HttpError: '500 Internal Server Error' for 'https://danbooru.donmai.us/x'"
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.gallery_dl.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.gallery_dl.provider.auth_cooldown.record_auth_failure") as mock_record,
            patch("app.providers.gallery_dl.provider._simulate", return_value=(1, 0, server_error)) as mock_simulate,
        ):
            result = gallery_provider.download(
                "https://danbooru.donmai.us/posts/1", tokens={}, max_retries=3, retry_delay=0
            )

        # danbooru.donmai.us has ONE cookie candidate ([None]) — 3 retries * 1
        # candidate = 3 calls, exactly the pre-existing behaviour.
        assert mock_simulate.call_count == 3
        mock_record.assert_not_called()
        assert result.status.value == "failed"
        assert result.metadata["auth_classification"] == auth_failure.NOT_AUTH
        assert result.error == server_error  # no credentials embedded — sanitizer is a no-op here

    def test_indeterminate_error_also_retries_up_to_max_retries(self, tmp_path):
        ambiguous_error = "[twitter][error] 'Unavailable'"
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.gallery_dl.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.gallery_dl.provider.auth_cooldown.record_auth_failure") as mock_record,
            patch("app.providers.gallery_dl.provider._simulate", return_value=(1, 0, ambiguous_error)) as mock_simulate,
        ):
            result = gallery_provider.download(
                "https://danbooru.donmai.us/posts/1", tokens={}, max_retries=2, retry_delay=0
            )

        assert mock_simulate.call_count == 2
        mock_record.assert_not_called()
        assert result.metadata["auth_classification"] == auth_failure.INDETERMINATE


class TestErrorTextSanitizedOnAuthStop:
    def test_credential_bearing_url_in_auth_error_is_redacted(self, tmp_path):
        raw_error = "[somesite][error] AuthRequired: '401 Unauthorized' for 'https://user:hunter2@somesite.example/x'"
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.gallery_dl.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.gallery_dl.provider.auth_cooldown.record_auth_failure"),
            patch("app.providers.gallery_dl.provider._simulate", return_value=(1, 0, raw_error)),
        ):
            result = gallery_provider.download(
                "https://danbooru.donmai.us/posts/1", tokens={}, max_retries=1, retry_delay=0
            )

        assert "hunter2" not in result.error
        assert "user:hunter2" not in result.error
        # surviving half — host and path must still be present
        assert "somesite.example" in result.error
        assert "/x" in result.error
