"""
tests/test_gallery_dl_error_capture.py

Reviewer PASS-WITH-NOTES follow-up: app/providers/gallery_dl/provider.py used to
leave DownloadResult.error empty on FAILED downloads, so gallery-dl output never
reached updater_service.is_stale_extractor_error() — the reactive on-error
auto-update could only ever trigger for yt-dlp. This file covers the fix:
  - _last_error_line(): picks the real "[name][error] message" line gallery-dl
    actually emits (verified live against the installed gallery-dl CLI — see
    the docstring in provider.py and updater_service.py's signature comment).
  - _simulate() / _gallery_download(): now return that captured error text.
  - download(): threads it into the final FAILED DownloadResult.error.
  - End-to-end: a stale-extractor-shaped gallery-dl failure now flows through
    updater_service.is_stale_extractor_error() as True (the dead path is closed);
    an unrelated failure (e.g. a plain 404) still flows through as False.

subprocess is ALWAYS mocked — no real gallery-dl process is spawned.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.providers.gallery_dl import provider as gallery_provider
from app.services import updater_service


class TestLastErrorLine:
    def test_picks_the_error_tagged_line(self):
        text = (
            "[gallery-dl][debug] Starting DownloadJob for 'https://example.com'\n"
            "[gallery-dl][error] Unsupported URL 'https://example.com'\n"
        )
        assert gallery_provider._last_error_line(text) == "[gallery-dl][error] Unsupported URL 'https://example.com'"

    def test_picks_the_last_error_line_when_several(self):
        text = (
            "[danbooru][error] HttpError: '500 Internal Server Error' for 'https://a'\n"
            "[danbooru][error] HttpError: '500 Internal Server Error' for 'https://b'\n"
        )
        assert gallery_provider._last_error_line(text).endswith("'https://b'")

    def test_falls_back_to_last_nonblank_line_without_error_tag(self):
        text = "some plain diagnostic output\nwith no bracketed error tag\n"
        assert gallery_provider._last_error_line(text) == "with no bracketed error tag"

    def test_empty_input_returns_empty_string(self):
        assert gallery_provider._last_error_line("") == ""
        assert gallery_provider._last_error_line("   \n  \n") == ""


class TestSimulateCapturesError:
    def test_nonzero_exit_captures_stderr_error_line(self):
        fake_result = MagicMock()
        fake_result.returncode = 64
        fake_result.stdout = ""
        fake_result.stderr = "[gallery-dl][error] Unsupported URL 'https://example.com/x'\n"

        with patch("app.providers.gallery_dl.provider.subprocess.run", return_value=fake_result):
            code, count, error = gallery_provider._simulate("https://example.com/x", env={})

        assert code == 64
        assert count == 0
        assert error == "[gallery-dl][error] Unsupported URL 'https://example.com/x'"

    def test_success_needs_no_error(self):
        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = "/download/path/file1.jpg\n/download/path/file2.jpg\n"
        fake_result.stderr = ""

        with patch("app.providers.gallery_dl.provider.subprocess.run", return_value=fake_result):
            code, count, error = gallery_provider._simulate("https://example.com/ok", env={})

        assert code == 0
        assert count == 2
        assert error == ""


class TestGalleryDownloadCapturesError:
    def _fake_process(self, lines: list[str], returncode: int):
        process = MagicMock()
        iterator = iter([*lines, ""])  # readline() returns "" to signal EOF
        process.stdout.readline.side_effect = lambda: next(iterator)
        process.wait.return_value = None
        process.returncode = returncode
        return process

    def test_failed_run_captures_error_tagged_line(self, tmp_path):
        process = self._fake_process(
            [
                "[danbooru][debug] some progress line\n",
                "[danbooru][error] HttpError: '404 Not Found' for 'https://danbooru.donmai.us/x.json'\n",
            ],
            returncode=4,
        )
        with patch("app.providers.gallery_dl.provider.subprocess.Popen", return_value=process):
            status, downloaded, skipped, error = gallery_provider._gallery_download(
                "https://danbooru.donmai.us/x", env={}, download_root=tmp_path
            )

        assert status == "failed"
        assert "404 Not Found" in error

    def test_successful_run_reports_no_error(self, tmp_path):
        process = self._fake_process(["some/path/file.jpg\n"], returncode=0)
        with patch("app.providers.gallery_dl.provider.subprocess.Popen", return_value=process):
            status, downloaded, skipped, error = gallery_provider._gallery_download(
                "https://example.com/ok", env={}, download_root=tmp_path
            )

        assert status == "success"
        assert downloaded == 1
        assert error == ""


class TestDownloadEndToEndErrorPropagation:
    """download() must surface the real gallery-dl error text on its FAILED
    DownloadResult, and that text must correctly classify via
    updater_service.is_stale_extractor_error() — this is the actual dead-path fix.

    Uses danbooru.donmai.us (not pixiv/facebook/x) so _probe_user_root() takes the
    plain "return root" branch — no real network call — and DOWNLOAD_DIR is
    patched to tmp_path so category_root()'s mkdir() never touches the real
    download/ folder.
    """

    def test_stale_extractor_error_now_flows_through_and_classifies_true(self, tmp_path):
        stale_error = (
            "[danbooru][error] An unexpected error occurred: KeyError - 'illustId'. "
            "Please run gallery-dl again with the --verbose flag, copy its output "
            "and report this issue on https://github.com/mikf/gallery-dl/issues ."
        )
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.gallery_dl.provider._simulate", return_value=(1, 0, stale_error)),
        ):
            result = gallery_provider.download("https://danbooru.donmai.us/posts/1", tokens={}, max_retries=1, retry_delay=0)

        assert result.error == stale_error
        assert updater_service.is_stale_extractor_error(result.error) is True

    def test_unrelated_404_error_flows_through_but_classifies_false(self, tmp_path):
        http_error = "[danbooru][error] HttpError: '404 Not Found' for 'https://danbooru.donmai.us/posts/1.json'"
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.gallery_dl.provider._simulate", return_value=(4, 0, http_error)),
        ):
            result = gallery_provider.download("https://danbooru.donmai.us/posts/1", tokens={}, max_retries=1, retry_delay=0)

        assert result.error == http_error
        assert updater_service.is_stale_extractor_error(result.error) is False

    def test_failed_result_never_leaves_error_empty(self, tmp_path):
        """Even with no captured error text at all, a fallback message is set —
        the field must never silently stay empty on a FAILED result."""
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("app.providers.gallery_dl.provider._simulate", return_value=(1, 0, "")),
        ):
            result = gallery_provider.download("https://danbooru.donmai.us/posts/1", tokens={}, max_retries=1, retry_delay=0)

        assert result.error == "gallery-dl failed"
