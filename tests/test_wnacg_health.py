"""
tests/test_wnacg_health.py

覆蓋 app/providers/sites/wnacg_health.py — wnacg 連續失敗告警：
- 未達門檻不告警（單次暫時性失敗不該吵人）。
- 達門檻恰好觸發一次告警，同一次故障期間即使繼續失敗也不重複告警（防洗版）。
- 中途一次成功會重置累計次數，並在下一次故障重新武裝告警。
- 未設定 DISCORD_BOT_TOKEN / DISCORD_CHANNEL_IDS 時退化為只印 console，不嘗試網路請求。
- 有設定時對每個 channel 各發一次 POST，且單一 channel 的例外不影響其他 channel。

_send_discord_alert 的網路呼叫一律 mock（不打真實 Discord API）；module-level 的計數器
狀態在每個測試前後透過 reset_for_tests() 重置，避免測試互相汙染。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.providers.sites import wnacg_health


@pytest.fixture(autouse=True)
def _reset_health_state():
    wnacg_health.reset_for_tests()
    yield
    wnacg_health.reset_for_tests()


class TestRecordResultThreshold:
    def test_failures_below_threshold_never_alert(self):
        with patch.object(wnacg_health, "WNACG_ALERT_THRESHOLD", 3), patch.object(
            wnacg_health, "_send_discord_alert"
        ) as mock_alert:
            wnacg_health.record_result(success=False)
            wnacg_health.record_result(success=False)
            mock_alert.assert_not_called()
            assert mock_alert.call_count == 0

    def test_reaching_threshold_fires_exactly_one_alert(self):
        with patch.object(wnacg_health, "WNACG_ALERT_THRESHOLD", 3), patch.object(
            wnacg_health, "_send_discord_alert"
        ) as mock_alert:
            wnacg_health.record_result(success=False)
            wnacg_health.record_result(success=False)
            wnacg_health.record_result(success=False)
            mock_alert.assert_called_once()
            assert "3" in mock_alert.call_args[0][0]

    def test_continued_failures_past_threshold_do_not_spam(self):
        """A sustained outage must alert ONCE, not on every subsequent failure —
        this is the anti-spam requirement from the dispatch brief."""
        with patch.object(wnacg_health, "WNACG_ALERT_THRESHOLD", 2), patch.object(
            wnacg_health, "_send_discord_alert"
        ) as mock_alert:
            for _ in range(6):
                wnacg_health.record_result(success=False)
            mock_alert.assert_called_once()
            assert mock_alert.call_count == 1

    def test_success_resets_the_streak(self):
        with patch.object(wnacg_health, "WNACG_ALERT_THRESHOLD", 3), patch.object(
            wnacg_health, "_send_discord_alert"
        ) as mock_alert:
            wnacg_health.record_result(success=False)
            wnacg_health.record_result(success=False)
            wnacg_health.record_result(success=True)
            wnacg_health.record_result(success=False)
            wnacg_health.record_result(success=False)
            mock_alert.assert_not_called()  # only 2 consecutive failures since the reset
            assert mock_alert.call_count == 0

    def test_success_after_an_outage_rearms_the_next_alert(self):
        """A single transient failure never alerts, but a SECOND distinct
        outage (after a recovery) must alert again — the dedup is per-outage,
        not permanent."""
        with patch.object(wnacg_health, "WNACG_ALERT_THRESHOLD", 2), patch.object(
            wnacg_health, "_send_discord_alert"
        ) as mock_alert:
            wnacg_health.record_result(success=False)
            wnacg_health.record_result(success=False)  # outage #1 alert
            wnacg_health.record_result(success=True)  # recovery
            wnacg_health.record_result(success=False)
            wnacg_health.record_result(success=False)  # outage #2 alert
            assert mock_alert.call_count == 2


class TestSendDiscordAlert:
    def test_missing_config_logs_to_console_and_never_calls_urlopen(self, capsys):
        with patch.object(wnacg_health, "DISCORD_BOT_TOKEN", ""), patch.object(
            wnacg_health, "DISCORD_CHANNEL_IDS", set()
        ), patch.object(wnacg_health, "urlopen") as mock_urlopen:
            wnacg_health._send_discord_alert("test message")
            mock_urlopen.assert_not_called()
            assert "test message" in capsys.readouterr().out

    def test_posts_once_per_configured_channel(self):
        with patch.object(wnacg_health, "DISCORD_BOT_TOKEN", "fake-token"), patch.object(
            wnacg_health, "DISCORD_CHANNEL_IDS", {111, 222}
        ), patch.object(wnacg_health, "urlopen") as mock_urlopen:
            wnacg_health._send_discord_alert("outage!")
            assert mock_urlopen.call_count == 2

    def test_one_channel_failure_does_not_block_the_other(self):
        with patch.object(wnacg_health, "DISCORD_BOT_TOKEN", "fake-token"), patch.object(
            wnacg_health, "DISCORD_CHANNEL_IDS", {111, 222}
        ), patch.object(wnacg_health, "urlopen", side_effect=[Exception("boom"), MagicMock()]) as mock_urlopen:
            wnacg_health._send_discord_alert("outage!")  # must not raise
            assert mock_urlopen.call_count == 2
