"""
tests/test_pixiv_oauth_tty_guard.py

app.providers.gallery_dl.auth.get_pixiv_refresh_token — the TTY guard from
dispatch item 3 (phase 1a). `gallery-dl oauth:pixiv` calls Python's builtin
`input()` (gallery_dl/extractor/oauth.py::OAuthPixiv, verified against the
installed package) to wait for a human to paste an OAuth code. This function
is called from the queue worker's single background daemon thread
(app/services/queue_service.py) whenever the cached/config refresh token is
missing — with no TTY guard, that `input()` call can block the ENTIRE
download queue forever the instant the token needs refreshing.

subprocess is ALWAYS mocked — no real `gallery-dl oauth:pixiv` is spawned,
and no real terminal I/O happens in this test file.
"""
from __future__ import annotations

import subprocess as real_subprocess
from unittest.mock import patch

from app.providers.gallery_dl import auth as pixiv_auth


class TestHeadlessNeverBlocks:
    def test_no_tty_and_no_cached_token_returns_none_without_spawning_oauth(self, tmp_path):
        """The core fix: when there is no interactive terminal AND no token
        is available anywhere (in-memory cache, data/tokens.json, or
        gallery-dl's own config.json), get_pixiv_refresh_token must return
        None immediately — never call `subprocess.run(["gallery-dl",
        "oauth:pixiv"])`, which is the call that can block forever."""
        with (
            patch("app.providers.gallery_dl.auth._gallery_dl_config_path", return_value=tmp_path / "config.json"),
            patch("sys.stdin") as mock_stdin,
            patch("app.providers.gallery_dl.auth.subprocess.run") as mock_run,
        ):
            mock_stdin.isatty.return_value = False
            result = pixiv_auth.get_pixiv_refresh_token({})

        mock_run.assert_not_called()
        assert result is None

    def test_no_tty_but_cached_token_exists_returns_it_without_touching_tty_at_all(self, tmp_path):
        """The TTY check must never even be consulted when a cached token
        already satisfies the request — the guard only matters on the
        actually-missing-credential path."""
        with (
            patch("app.providers.gallery_dl.auth.subprocess.run") as mock_run,
        ):
            result = pixiv_auth.get_pixiv_refresh_token({"pixiv_refresh_token": "cached-token-value"})

        mock_run.assert_not_called()
        assert result == "cached-token-value"


class TestInteractivePathStillWorks:
    def test_tty_present_still_invokes_oauth_flow_with_timeout(self, tmp_path):
        """The interactive path must NOT be removed — a human running this
        from a real terminal still gets the OAuth flow, now with a bounded
        timeout as a second-layer defense (the TTY check is the primary
        guard; this covers the rarer case of an interactive session that
        then goes idle)."""
        config_path = tmp_path / "config.json"

        def fake_run(cmd, **kwargs):
            # Simulate gallery-dl writing the refreshed token to its config
            # file as a side effect of the (mocked) oauth flow.
            config_path.write_text(
                '{"extractor": {"pixiv": {"refresh-token": "freshly-obtained-token"}}}',
                encoding="utf-8",
            )
            return None

        with (
            patch("app.providers.gallery_dl.auth._gallery_dl_config_path", return_value=config_path),
            patch("sys.stdin") as mock_stdin,
            patch("app.providers.gallery_dl.auth.subprocess.run", side_effect=fake_run) as mock_run,
            patch("app.providers.gallery_dl.auth.save_tokens"),
        ):
            mock_stdin.isatty.return_value = True
            result = pixiv_auth.get_pixiv_refresh_token({})

        mock_run.assert_called_once()
        call_args, call_kwargs = mock_run.call_args
        assert call_args[0] == ["gallery-dl", "oauth:pixiv"]
        assert call_kwargs.get("timeout") == pixiv_auth.PIXIV_OAUTH_TIMEOUT_SECONDS
        assert result == "freshly-obtained-token"

    def test_oauth_timeout_is_handled_without_raising(self, tmp_path):
        config_path = tmp_path / "config.json"  # never created — oauth times out
        with (
            patch("app.providers.gallery_dl.auth._gallery_dl_config_path", return_value=config_path),
            patch("sys.stdin") as mock_stdin,
            patch(
                "app.providers.gallery_dl.auth.subprocess.run",
                side_effect=real_subprocess.TimeoutExpired(cmd=["gallery-dl", "oauth:pixiv"], timeout=300),
            ),
        ):
            mock_stdin.isatty.return_value = True
            result = pixiv_auth.get_pixiv_refresh_token({})

        assert result is None

    def test_oauth_process_error_still_handled_without_raising(self, tmp_path):
        config_path = tmp_path / "config.json"
        with (
            patch("app.providers.gallery_dl.auth._gallery_dl_config_path", return_value=config_path),
            patch("sys.stdin") as mock_stdin,
            patch(
                "app.providers.gallery_dl.auth.subprocess.run",
                side_effect=real_subprocess.CalledProcessError(returncode=1, cmd=["gallery-dl", "oauth:pixiv"]),
            ),
        ):
            mock_stdin.isatty.return_value = True
            result = pixiv_auth.get_pixiv_refresh_token({})

        assert result is None
