"""
tests/test_ytdlp_resolve_executable.py

app.providers.ytdlp.provider._resolve_executable — fix for the dead
`.ns-yt-dlp` sibling-repo fallback (that repo no longer exists on disk):
- A repo-root override .exe still wins when present (local troubleshooting).
- Otherwise resolves via PATH (`which`) — the venv-installed console script.
- No longer touches ROOT_DIR.parent / ".ns-yt-dlp" at all.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.providers.ytdlp.provider import _resolve_executable


class TestResolveExecutable:
    def test_prefers_repo_root_override_when_present(self, tmp_path):
        fake_root = tmp_path
        (fake_root / "yt-dlp.exe").write_text("", encoding="utf-8")
        with patch("app.providers.ytdlp.provider.ROOT_DIR", fake_root):
            result = _resolve_executable("yt-dlp")
        assert result == str(fake_root / "yt-dlp.exe")

    def test_falls_back_to_path_when_no_override(self, tmp_path):
        fake_root = tmp_path  # empty dir, no yt-dlp.exe here
        venv_path = str(Path("venv/Scripts/yt-dlp.exe"))
        with (
            patch("app.providers.ytdlp.provider.ROOT_DIR", fake_root),
            patch("app.providers.ytdlp.provider.which", return_value=venv_path) as mock_which,
        ):
            result = _resolve_executable("yt-dlp")
        mock_which.assert_called_once_with("yt-dlp")
        assert result == venv_path

    def test_returns_none_when_nothing_resolves(self, tmp_path):
        with (
            patch("app.providers.ytdlp.provider.ROOT_DIR", tmp_path),
            patch("app.providers.ytdlp.provider.which", return_value=None),
        ):
            assert _resolve_executable("yt-dlp") is None

    def test_never_touches_dead_sibling_ns_yt_dlp_path(self, tmp_path):
        """
        Regression guard: even if a stray ".ns-yt-dlp" sibling directory happens to
        exist next to ROOT_DIR with a matching exe in it, _resolve_executable must
        NOT resolve to it — that fallback is removed entirely, not just "usually
        empty". Only the repo-root override or PATH may be used.
        """
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        sibling = tmp_path / ".ns-yt-dlp"
        sibling.mkdir()
        (sibling / "yt-dlp.exe").write_text("", encoding="utf-8")

        with (
            patch("app.providers.ytdlp.provider.ROOT_DIR", fake_root),
            patch("app.providers.ytdlp.provider.which", return_value=None),
        ):
            assert _resolve_executable("yt-dlp") is None
