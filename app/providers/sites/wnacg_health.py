from __future__ import annotations

import json
import threading
from urllib.request import Request, urlopen

from app.config.settings import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_IDS, WNACG_ALERT_THRESHOLD

# Lightweight consecutive-failure alert for the wnacg provider (see
# docs/blueprint or the dispatch report this shipped with for the design
# rationale). Deliberately talks to Discord's REST API directly with the bot
# token rather than importing `app.services.discord_service`'s live gateway
# client:
#   1. Layering — `app.providers.*` may depend on `app.config` (below it) but
#      never on `app.services` (above it); `discord_service` itself imports
#      `download_service` (a service), so importing it FROM a provider would
#      also risk a new import cycle. See cluster-conventions
#      `## Backend architecture` / this repo's G4 gate.
#   2. The alert must fire even when only the web server is running
#      (`dl.cmd -s`, no `-b`) — the gateway client only exists/connects when
#      the bot process (`-b`) is up, but downloads (and therefore wnacg
#      failures) happen with or without it.
# A REST POST needs no live gateway session, just the same DISCORD_BOT_TOKEN
# + DISCORD_CHANNEL_IDS config the bot already uses.

_lock = threading.Lock()
_consecutive_failures = 0
_alert_sent_for_current_outage = False


def _send_discord_alert(message: str) -> None:
    """Best-effort POST to every configured Discord channel. Any failure
    (missing config, network error, bad token, ...) is logged to console and
    swallowed — an alerting bug must never break or delay a download."""
    if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_IDS:
        print(f"[wnacg][alert] (未設定 DISCORD_BOT_TOKEN / DISCORD_CHANNEL_IDS，僅記錄於 console) {message}")
        return
    payload = json.dumps({"content": message}).encode("utf-8")
    for channel_id in DISCORD_CHANNEL_IDS:
        try:
            request = Request(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                data=payload,
                headers={
                    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            urlopen(request, timeout=10)
        except Exception as exc:  # alerting must never raise into the caller
            print(f"[wnacg][alert] Discord 通知發送失敗（channel {channel_id}）: {exc}")


def record_result(success: bool) -> None:
    """Track consecutive wnacg failures across ALL entry points (web UI,
    queue, bot) — this is called once per terminal wnacg download outcome
    from `app.providers.gallery_dl.provider.download`, the single choke
    point every wnacg download passes through regardless of trigger.

    Fires exactly ONE alert per outage episode, at the moment the streak
    first reaches `WNACG_ALERT_THRESHOLD` — never re-fires on every
    subsequent failure while the outage continues (that would spam), and
    never fires at all for a streak shorter than the threshold (a single
    transient failure is not an outage). A success resets the streak AND
    re-arms the next outage's alert.
    """
    global _consecutive_failures, _alert_sent_for_current_outage
    count = 0
    threshold = 0
    should_alert = False
    with _lock:
        if success:
            _consecutive_failures = 0
            _alert_sent_for_current_outage = False
        else:
            _consecutive_failures += 1
            if _consecutive_failures >= WNACG_ALERT_THRESHOLD and not _alert_sent_for_current_outage:
                _alert_sent_for_current_outage = True
                should_alert = True
                count = _consecutive_failures
                threshold = WNACG_ALERT_THRESHOLD
    if should_alert:
        _send_discord_alert(f"⚠️ [wnacg] 連續 {count} 次下載失敗（門檻 {threshold}），主線路與備用線路可能同時異常，請檢查。")


def reset_for_tests() -> None:
    """Test-only helper — the module-level counters are process-global state,
    so tests must reset them between cases to stay isolated."""
    global _consecutive_failures, _alert_sent_for_current_outage
    with _lock:
        _consecutive_failures = 0
        _alert_sent_for_current_outage = False
