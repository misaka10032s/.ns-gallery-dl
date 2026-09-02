"""
tests/test_ytdlp_auth_cooldown.py

app.providers.ytdlp.provider.download() — the cooldown check + classification
recording from dispatch items 1/2 (phase 1a). yt-dlp has no retry loop to cut
(a single subprocess invocation is already "one attempt"), but it MUST still:
  - consult the SAME cross-engine cooldown gallery-dl checks (youtube.com/
    youtu.be are yt-dlp-only; facebook.com/fb.watch/twitter.com/x.com are
    tried by BOTH engines against the same cookie file), skipping the
    subprocess call entirely while a domain is cooling down;
  - classify a failure and arm the cooldown when it's AUTH;
  - route the error text through the sanitizer and record the classification
    in DownloadResult.metadata for phase 1b.

subprocess is ALWAYS mocked — no real yt-dlp process is spawned.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain import auth_failure
from app.providers.ytdlp import provider as ytdlp_provider


def _fake_process(lines: list[str], returncode: int):
    process = MagicMock()
    iterator = iter([*lines, ""])  # readline() returns "" to signal EOF
    process.stdout.readline.side_effect = lambda: next(iterator)
    process.wait.return_value = None
    process.returncode = returncode
    return process


class TestCooldownSkipsSubprocessEntirely:
    def test_domain_in_cooldown_never_spawns_yt_dlp(self, tmp_path):
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.ytdlp.provider._resolve_executable", return_value="yt-dlp"),
            patch(
                "app.providers.ytdlp.provider.auth_cooldown.in_cooldown",
                return_value=(True, "2026-09-02T18:00:00"),
            ),
            patch("app.providers.ytdlp.provider.subprocess.Popen") as mock_popen,
        ):
            result = ytdlp_provider.download("https://youtube.com/watch?v=abc")

        mock_popen.assert_not_called()
        assert result.status.value == "failed"
        assert "youtube.com" in result.error
        assert result.metadata["auth_classification"] == auth_failure.AUTH
        assert result.metadata["auth_cooldown"] is True


class TestCookiePathWiredIntoCooldownSelfHeal:
    """fix-round-2: resolve_cookie_file() now runs BEFORE the cooldown check
    (previously after), and its result is passed into in_cooldown(domain,
    cookie_path) — the same mtime self-heal gallery-dl's provider already
    had. Without this, in_cooldown() was always called with cookie_path
    omitted (defaulting to None inside app.domain.auth_cooldown), so an
    out-of-band jar rewrite (the engine's own write-back, a manual replace,
    or a MULTI_PROVIDER_DOMAINS alias sibling) could never clear a yt-dlp
    cooldown early — the owner had no escape hatch but the 6h TTL or the
    manual endpoint."""

    def test_in_cooldown_is_called_with_the_resolved_cookie_path_not_omitted(self, tmp_path):
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.ytdlp.provider._resolve_executable", return_value="yt-dlp"),
            patch("app.providers.ytdlp.provider.resolve_cookie_file", return_value="C:/cookies/x-com.txt"),
            patch("app.providers.ytdlp.provider.auth_cooldown.in_cooldown", return_value=(False, None)) as mock_in_cooldown,
            patch("app.providers.ytdlp.provider._probe_user_root", side_effect=lambda executable, url, root, cookie_path: root),
            patch("app.providers.ytdlp.provider.subprocess.Popen", return_value=_fake_process(["ok.mp4\n"], returncode=0)),
        ):
            ytdlp_provider.download("https://x.com/someone/status/1")

        mock_in_cooldown.assert_called_once_with("x.com", "C:/cookies/x-com.txt")
        # literal assert alongside the mock assertion above — the mock's own
        # assert_called_once_with() is invisible to this repo's AST-based
        # G3(b) assertion-presence check (it only recognizes ast.Assert /
        # pytest.raises, see quality-gates/check_test_assertions.py), so a
        # test using ONLY a mock assertion reads as zero-assertion to it.
        called_args = mock_in_cooldown.call_args.args
        assert called_args == ("x.com", "C:/cookies/x-com.txt")


class TestAuthClassifiedFailureArmsCooldown:
    def test_login_required_failure_records_cooldown(self, tmp_path):
        auth_line = (
            "ERROR: [twitter] 123: You are not authorized to view this protected tweet. "
            "Use --cookies, --cookies-from-browser, --username and --password, "
            "--netrc-cmd, or --netrc (twitter) to provide account credentials."
        )
        process = _fake_process([auth_line + "\n"], returncode=1)
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.ytdlp.provider._resolve_executable", return_value="yt-dlp"),
            patch("app.providers.ytdlp.provider._probe_user_root", side_effect=lambda executable, url, root, cookie_path: root),
            patch("app.providers.ytdlp.provider.resolve_cookie_file", return_value=None),
            patch("app.providers.ytdlp.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.ytdlp.provider.auth_cooldown.record_auth_failure") as mock_record,
            patch("app.providers.ytdlp.provider.subprocess.Popen", return_value=process),
        ):
            result = ytdlp_provider.download("https://x.com/someone/status/1")

        mock_record.assert_called_once_with("x.com", auth_line)
        assert result.metadata["auth_classification"] == auth_failure.AUTH


class TestNonAuthFailureDoesNotArmCooldown:
    def test_generic_failure_does_not_record_cooldown(self, tmp_path):
        process = _fake_process(["ERROR: [youtube] abc: Video unavailable\n"], returncode=1)
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.ytdlp.provider._resolve_executable", return_value="yt-dlp"),
            patch("app.providers.ytdlp.provider._probe_user_root", side_effect=lambda executable, url, root, cookie_path: root),
            patch("app.providers.ytdlp.provider.resolve_cookie_file", return_value=None),
            patch("app.providers.ytdlp.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.ytdlp.provider.auth_cooldown.record_auth_failure") as mock_record,
            patch("app.providers.ytdlp.provider.subprocess.Popen", return_value=process),
        ):
            result = ytdlp_provider.download("https://youtube.com/watch?v=abc")

        mock_record.assert_not_called()
        assert result.metadata["auth_classification"] == auth_failure.INDETERMINATE


class TestErrorTextSanitizedOnFailure:
    def test_credential_bearing_url_is_redacted(self, tmp_path):
        raw_line = "ERROR: unable to download video data: HTTP Error 403: for https://user:hunter2@cdn.example/x"
        process = _fake_process([raw_line + "\n"], returncode=1)
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.ytdlp.provider._resolve_executable", return_value="yt-dlp"),
            patch("app.providers.ytdlp.provider._probe_user_root", side_effect=lambda executable, url, root, cookie_path: root),
            patch("app.providers.ytdlp.provider.resolve_cookie_file", return_value=None),
            patch("app.providers.ytdlp.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.ytdlp.provider.auth_cooldown.record_auth_failure"),
            patch("app.providers.ytdlp.provider.subprocess.Popen", return_value=process),
        ):
            result = ytdlp_provider.download("https://youtube.com/watch?v=abc")

        assert "hunter2" not in result.error
        assert "cdn.example" in result.error
        assert "/x" in result.error


class TestSuccessResultUnaffected:
    def test_success_returns_no_error_and_no_metadata_needed(self, tmp_path):
        process = _fake_process(["/download/path/video.mp4\n"], returncode=0)
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.ytdlp.provider._resolve_executable", return_value="yt-dlp"),
            patch("app.providers.ytdlp.provider._probe_user_root", side_effect=lambda executable, url, root, cookie_path: root),
            patch("app.providers.ytdlp.provider.resolve_cookie_file", return_value=None),
            patch("app.providers.ytdlp.provider.auth_cooldown.in_cooldown", return_value=(False, None)),
            patch("app.providers.ytdlp.provider.subprocess.Popen", return_value=process),
        ):
            result = ytdlp_provider.download("https://youtube.com/watch?v=abc")

        assert result.status.value == "success"
        assert result.error == ""
