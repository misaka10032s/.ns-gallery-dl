"""
tests/test_updater_service.py

app.services.updater_service — generic pip-managed downloader updater:
- is_stale_extractor_error(): tight, low-false-positive classifier.
- update_downloader() / update_all_downloaders(): version-before/after + changed flag.
- maybe_reactive_update(): anti-mindless-update guard (cooldown + already-latest skip,
  one-retry signal on an actual version change).

subprocess is ALWAYS mocked — these tests never invoke a real pip install / --version.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services import updater_service


class TestIsStaleExtractorError:
    @pytest.mark.parametrize(
        "error",
        [
            # yt-dlp
            "ERROR: Cannot parse data",
            "ERROR: Unable to extract video data",
            "unable to extract user info",
            # gallery-dl (verified real wording — see updater_service.py comment)
            "[gallery-dl][error] Unable to extract bootstrap data",
            "[danbooru][error] Failed to parse JSON data:  JSONDecodeError: Expecting value",
            "[pixiv][error] An unexpected error occurred: KeyError - 'illustId'. "
            "Please run gallery-dl again with the --verbose flag, copy its output "
            "and report this issue on https://github.com/mikf/gallery-dl/issues .",
        ],
    )
    def test_matches_known_signatures(self, error):
        assert updater_service.is_stale_extractor_error(error) is True

    @pytest.mark.parametrize(
        "error",
        [
            "",
            None,
            "HTTP Error 403: Forbidden",
            # gallery-dl: deliberately NOT matched (see updater_service.py comment)
            "[gallery-dl][error] Unsupported URL 'https://example.com/nope'",
            "[danbooru][error] HttpError: '404 Not Found' for 'https://danbooru.donmai.us/posts/1.json'",
            "Connection timed out",
            "Sign in to confirm your age",
        ],
    )
    def test_does_not_match_unrelated_errors(self, error):
        assert updater_service.is_stale_extractor_error(error) is False


class TestUpdateDownloader:
    def test_reports_changed_when_version_differs(self):
        version_calls = iter(["2024.01.01", "2024.06.01"])

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            if "--version" in cmd:
                result.stdout = next(version_calls)
                result.stderr = ""
            else:
                result.stdout = ""
                result.stderr = ""
            return result

        with patch("app.services.updater_service.subprocess.run", side_effect=fake_run):
            outcome = updater_service.update_downloader("yt-dlp")

        assert outcome == {
            "package": "yt-dlp",
            "old_version": "2024.01.01",
            "new_version": "2024.06.01",
            "changed": True,
        }

    def test_reports_unchanged_when_already_latest(self):
        def fake_run(cmd, **kwargs):
            result = MagicMock()
            if "--version" in cmd:
                result.stdout = "2024.06.01"
                result.stderr = ""
            else:
                result.stdout = ""
                result.stderr = ""
            return result

        with patch("app.services.updater_service.subprocess.run", side_effect=fake_run):
            outcome = updater_service.update_downloader("yt-dlp")

        assert outcome["changed"] is False
        assert outcome["old_version"] == outcome["new_version"] == "2024.06.01"

    def test_uses_python_module_pip_not_import_pip(self):
        """Never `import pip` — always `python -m pip install -U <package>`."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            result = MagicMock()
            result.stdout = "1.0.0"
            result.stderr = ""
            return result

        with patch("app.services.updater_service.subprocess.run", side_effect=fake_run):
            updater_service.update_downloader("gallery-dl")

        pip_calls = [c for c in calls if "pip" in c]
        assert len(pip_calls) == 1
        assert pip_calls[0][0] == updater_service.sys.executable
        assert pip_calls[0][1:] == ["-m", "pip", "install", "-U", "gallery-dl"]

    def test_update_all_downloaders_covers_every_registered_package(self):
        with patch("app.services.updater_service.update_downloader") as mock_update:
            mock_update.side_effect = lambda pkg: {"package": pkg, "old_version": "1", "new_version": "1", "changed": False}
            results = updater_service.update_all_downloaders()

        updated_packages = {r["package"] for r in results}
        assert updated_packages == set(updater_service.DOWNLOADER_PACKAGES.values())


class TestMaybeReactiveUpdate:
    def test_unknown_provider_is_a_noop(self):
        outcome = updater_service.maybe_reactive_update("not-a-real-provider")
        assert outcome == {"retried": False, "changed": False, "message": ""}

    def test_within_cooldown_and_already_latest_skips_update_entirely(self):
        recent = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
        with (
            patch("app.services.updater_service.init_db"),
            patch(
                "app.services.updater_service.downloader_state_repo.get_state",
                return_value={"package": "yt-dlp", "last_checked_version": "2024.06.01", "last_checked_at": recent},
            ),
            patch("app.services.updater_service.get_installed_version", return_value="2024.06.01"),
            patch("app.services.updater_service.update_downloader") as mock_update,
        ):
            outcome = updater_service.maybe_reactive_update("ytdlp")

        mock_update.assert_not_called()
        assert outcome["retried"] is False
        assert outcome["changed"] is False
        assert "已是最新" in outcome["message"]
        assert "2024.06.01" in outcome["message"]

    def test_outside_cooldown_runs_update_and_signals_retry_on_change(self):
        stale = (datetime.now() - timedelta(hours=12)).isoformat(timespec="seconds")
        with (
            patch("app.services.updater_service.init_db"),
            patch(
                "app.services.updater_service.downloader_state_repo.get_state",
                return_value={"package": "yt-dlp", "last_checked_version": "2024.01.01", "last_checked_at": stale},
            ),
            patch("app.services.updater_service.downloader_state_repo.set_state") as mock_set_state,
            patch("app.services.updater_service.get_installed_version", return_value="2024.01.01"),
            patch(
                "app.services.updater_service.update_downloader",
                return_value={"package": "yt-dlp", "old_version": "2024.01.01", "new_version": "2024.06.01", "changed": True},
            ),
        ):
            outcome = updater_service.maybe_reactive_update("ytdlp")

        assert outcome == {"retried": True, "changed": True, "message": ""}
        mock_set_state.assert_called_once()
        assert mock_set_state.call_args[0][0] == "yt-dlp"
        assert mock_set_state.call_args[0][1] == "2024.06.01"

    def test_update_runs_but_already_latest_returns_message_not_retry(self):
        """Cooldown expired (or first check ever) → we DO check pip, but pip says
        no newer version exists → still don't retry, just report 'already latest'."""
        with (
            patch("app.services.updater_service.init_db"),
            patch("app.services.updater_service.downloader_state_repo.get_state", return_value=None),
            patch("app.services.updater_service.downloader_state_repo.set_state") as mock_set_state,
            patch("app.services.updater_service.get_installed_version", return_value="2024.06.01"),
            patch(
                "app.services.updater_service.update_downloader",
                return_value={"package": "yt-dlp", "old_version": "2024.06.01", "new_version": "2024.06.01", "changed": False},
            ),
        ):
            outcome = updater_service.maybe_reactive_update("ytdlp")

        assert outcome["retried"] is False
        assert outcome["changed"] is False
        assert "已是最新" in outcome["message"]
        mock_set_state.assert_called_once()

    def test_no_prior_state_and_cooldown_irrelevant_still_updates(self):
        """No stored state at all (first-ever check) must NOT be treated as
        'already confirmed latest' — it must run the real update check."""
        with (
            patch("app.services.updater_service.init_db"),
            patch("app.services.updater_service.downloader_state_repo.get_state", return_value=None),
            patch("app.services.updater_service.downloader_state_repo.set_state"),
            patch("app.services.updater_service.get_installed_version", return_value="2024.01.01"),
            patch(
                "app.services.updater_service.update_downloader",
                return_value={"package": "yt-dlp", "old_version": "2024.01.01", "new_version": "2024.06.01", "changed": True},
            ) as mock_update,
        ):
            outcome = updater_service.maybe_reactive_update("ytdlp")

        mock_update.assert_called_once()
        assert outcome["retried"] is True
