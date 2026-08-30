"""
tests/test_discord_backfill.py

覆蓋 app/services/discord_service.py 新增的 on_ready backfill 路徑：
- _scan_and_process_channel：共用掃描迴圈（$d 與 backfill 共用），確認 skip_message_id
  正確跳過觸發訊息、其餘訊息照常收集/處理/反應。
- _backfill_channel：重疊防護（同一頻道不會併發跑兩次）、Forbidden/NotFound 頻道
  跳過而不中斷、完成後釋放防護旗標。
- _backfill_all_channels：對 DISCORD_CHANNEL_IDS 逐一呼叫。

全部用假物件，不連真正的 Discord。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord

from app.services import discord_service as ds


class _FakeChannel:
    def __init__(self, messages):
        self._messages = messages

    def history(self, limit=1000, oldest_first=True):
        async def gen():
            for message in self._messages:
                yield message

        return gen()


class _FakeMessage:
    def __init__(self, id, content=""):
        self.id = id
        self.author = SimpleNamespace(name="someone")
        self.content = content
        self.attachments = []
        self.embeds = []
        self.reactions = []
        self.channel = SimpleNamespace()


# ──────────────────────────────────────────────────────────
# _scan_and_process_channel
# ──────────────────────────────────────────────────────────


class TestScanAndProcessChannel:
    def test_skips_message_by_id_and_processes_the_rest(self, monkeypatch):
        trigger = _FakeMessage(id=1, content="")
        other = _FakeMessage(id=2, content="https://example.com/gallery")
        channel = _FakeChannel([trigger, other])

        monkeypatch.setattr(ds, "_is_supported_url", lambda url: True)
        monkeypatch.setattr(ds, "_extract_urls", lambda text: [text] if text else [])

        download_calls: list[str] = []

        async def fake_download_url(url):
            download_calls.append(url)
            return True

        monkeypatch.setattr(ds, "_download_url", fake_download_url)

        reacted: list[tuple[str, int]] = []

        async def fake_react(message, cfg, fallback):
            reacted.append(("react", message.id))

        async def fake_unreact(message, cfg, fallback):
            reacted.append(("unreact", message.id))

        monkeypatch.setattr(ds, "_react", fake_react)
        monkeypatch.setattr(ds, "_unreact", fake_unreact)

        total_ok, total_failed = asyncio.run(ds._scan_and_process_channel(channel, skip_message_id=trigger.id))

        assert (total_ok, total_failed) == (1, 0)
        assert download_calls == ["https://example.com/gallery"]
        # trigger (id=1) was skipped entirely — it must never get a reaction
        assert all(message_id != 1 for _, message_id in reacted)
        assert ("react", 2) in reacted

    def test_none_skip_id_processes_every_message(self, monkeypatch):
        """The on_ready backfill passes skip_message_id=None — no message id is ever
        `None`, so nothing gets excluded on that basis."""
        first = _FakeMessage(id=10, content="https://example.com/a")
        second = _FakeMessage(id=11, content="https://example.com/b")
        channel = _FakeChannel([first, second])

        monkeypatch.setattr(ds, "_is_supported_url", lambda url: True)
        monkeypatch.setattr(ds, "_extract_urls", lambda text: [text] if text else [])

        download_calls: list[str] = []

        async def fake_download_url(url):
            download_calls.append(url)
            return True

        monkeypatch.setattr(ds, "_download_url", fake_download_url)
        monkeypatch.setattr(ds, "_react", lambda *a, **k: _noop())
        monkeypatch.setattr(ds, "_unreact", lambda *a, **k: _noop())

        total_ok, total_failed = asyncio.run(ds._scan_and_process_channel(channel, skip_message_id=None))

        assert (total_ok, total_failed) == (2, 0)
        assert sorted(download_calls) == ["https://example.com/a", "https://example.com/b"]


async def _noop():
    return None


# ──────────────────────────────────────────────────────────
# _backfill_channel — overlap guard + Forbidden/NotFound handling
# ──────────────────────────────────────────────────────────


class TestBackfillChannel:
    def setup_method(self):
        ds._backfill_running.clear()

    def teardown_method(self):
        ds._backfill_running.clear()

    def test_skips_when_already_running_for_same_channel(self, monkeypatch):
        scan_calls = []

        async def fake_scan(channel, skip_message_id=None):
            scan_calls.append(channel)
            return (0, 0)

        monkeypatch.setattr(ds, "_scan_and_process_channel", fake_scan)
        monkeypatch.setattr(ds.client, "get_channel", lambda cid: SimpleNamespace())

        ds._backfill_running.add(123)
        asyncio.run(ds._backfill_channel(123))

        assert scan_calls == []  # never touched — overlap guard short-circuited it

    def test_clears_guard_flag_after_success(self, monkeypatch):
        async def fake_scan(channel, skip_message_id=None):
            return (3, 1)

        monkeypatch.setattr(ds, "_scan_and_process_channel", fake_scan)
        monkeypatch.setattr(ds.client, "get_channel", lambda cid: SimpleNamespace())

        asyncio.run(ds._backfill_channel(456))

        assert 456 not in ds._backfill_running

    def test_clears_guard_flag_even_on_scan_error(self, monkeypatch):
        fake_response = SimpleNamespace(status=403, reason="Forbidden")

        async def fake_scan(channel, skip_message_id=None):
            raise discord.Forbidden(fake_response, "Missing Access")

        monkeypatch.setattr(ds, "_scan_and_process_channel", fake_scan)
        monkeypatch.setattr(ds.client, "get_channel", lambda cid: SimpleNamespace())

        asyncio.run(ds._backfill_channel(789))  # must not raise

        assert 789 not in ds._backfill_running

    def test_not_found_channel_is_skipped_not_raised(self, monkeypatch):
        fake_response = SimpleNamespace(status=404, reason="Not Found")

        async def fake_fetch_channel(cid):
            raise discord.NotFound(fake_response, "Unknown Channel")

        scan_calls = []

        async def fake_scan(channel, skip_message_id=None):
            scan_calls.append(channel)
            return (0, 0)

        monkeypatch.setattr(ds.client, "get_channel", lambda cid: None)
        monkeypatch.setattr(ds.client, "fetch_channel", fake_fetch_channel)
        monkeypatch.setattr(ds, "_scan_and_process_channel", fake_scan)

        asyncio.run(ds._backfill_channel(999))  # must not raise

        assert scan_calls == []
        assert 999 not in ds._backfill_running

    def test_forbidden_fetching_channel_is_skipped_not_raised(self, monkeypatch):
        fake_response = SimpleNamespace(status=403, reason="Forbidden")

        async def fake_fetch_channel(cid):
            raise discord.Forbidden(fake_response, "Missing Access")

        monkeypatch.setattr(ds.client, "get_channel", lambda cid: None)
        monkeypatch.setattr(ds.client, "fetch_channel", fake_fetch_channel)

        asyncio.run(ds._backfill_channel(555))  # must not raise

        assert 555 not in ds._backfill_running


# ──────────────────────────────────────────────────────────
# _backfill_all_channels
# ──────────────────────────────────────────────────────────


class TestBackfillAllChannels:
    def test_calls_backfill_channel_for_every_configured_channel(self, monkeypatch):
        monkeypatch.setattr(ds, "DISCORD_CHANNEL_IDS", {111, 222})
        seen: list[int] = []

        async def fake_backfill_channel(channel_id):
            seen.append(channel_id)

        monkeypatch.setattr(ds, "_backfill_channel", fake_backfill_channel)

        asyncio.run(ds._backfill_all_channels())

        assert sorted(seen) == [111, 222]


# ──────────────────────────────────────────────────────────
# _track_background_task — strong-reference retention
# ──────────────────────────────────────────────────────────


class TestTrackBackgroundTask:
    def setup_method(self):
        ds._background_tasks.clear()

    def teardown_method(self):
        ds._background_tasks.clear()

    def test_task_is_retained_while_running_and_discarded_after_completion(self):
        """`asyncio.create_task` alone keeps only a weak reference inside the
        event loop; pins that `_track_background_task` holds a STRONG
        reference (the task must survive until it actually completes) and
        releases it via the done-callback once finished."""

        async def quick_coro():
            return "done"

        async def run():
            ds._track_background_task(quick_coro())
            assert len(ds._background_tasks) == 1  # strong ref held immediately
            for _ in range(20):
                if not ds._background_tasks:
                    break
                await asyncio.sleep(0)
            assert ds._background_tasks == set()  # done-callback released it

        asyncio.run(run())
