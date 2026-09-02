from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.services.token_service import save_tokens

# `gallery-dl oauth:pixiv` calls Python's builtin `input()` to wait for the
# user to paste an OAuth code (gallery_dl/extractor/oauth.py::OAuthPixiv,
# verified against the installed package) — a genuinely interactive flow.
# This function is called from the queue worker (a single background daemon
# thread, app/services/queue_service.py), which has no human at a keyboard
# ever. `input()` on a non-tty stdin (the normal case for a background
# thread/service) either raises EOFError immediately or blocks forever
# depending on how stdin is wired up for this process — neither is
# acceptable, and the blocking case previously stalled the ENTIRE download
# queue the instant the cached refresh token was ever missing or revoked
# (item 3). The primary guard below is the `sys.stdin.isatty()` check, which
# is what actually prevents the deadlock in the real failure mode (no
# terminal attached at all). PIXIV_OAUTH_TIMEOUT_SECONDS is a second,
# defense-in-depth layer only — generous enough for a human to actually see
# the browser prompt and paste the code back, in the rarer case this runs
# from a genuine interactive terminal that then goes idle.
PIXIV_OAUTH_TIMEOUT_SECONDS = 300


def _gallery_dl_config_path() -> Path:
    return Path.home() / ".config" / "gallery-dl" / "config.json"


def _read_gallery_dl_refresh_token() -> str:
    config_path = _gallery_dl_config_path()
    if not config_path.exists():
        return ""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("[Pixiv] could not parse gallery-dl config.json")
        return ""
    return config.get("extractor", {}).get("pixiv", {}).get("refresh-token", "")


def get_pixiv_refresh_token(tokens: dict) -> str | None:
    token = tokens.get("pixiv_refresh_token", "")
    if token:
        return token

    token = _read_gallery_dl_refresh_token()
    if token:
        tokens["pixiv_refresh_token"] = token
        save_tokens(tokens)
        return token

    if not sys.stdin.isatty():
        # A background worker (queue_service's single daemon thread, or the
        # Discord bot thread) can never satisfy an interactive prompt — fail
        # fast and clearly instead of risking a hang. The interactive path
        # below is untouched and still works for a human running this from
        # an actual terminal (`dl.cmd <url>` batch mode, or a manual
        # `python -m app.main` invocation with a real console attached).
        #
        # Residual risk (review finding N2, 2026-09-02, recorded rather than
        # left implied as impossible): `isatty()` only tells you a tty is
        # ATTACHED, not that a human is actually present at it. If this
        # process is ever launched with an INHERITED tty and no human
        # watching (e.g. `dl.cmd` invoked from a wrapper/CI-like shell that
        # doesn't detach stdin), a pixiv job can still block the queue worker
        # for up to PIXIV_OAUTH_TIMEOUT_SECONDS (5 minutes) waiting on an
        # `input()` nobody will ever answer. Normal interactive use (a human
        # running `dl.cmd` directly) and normal background-service use (`-s`/
        # `-b`, no tty at all) are both unaffected — this is narrower than the
        # deadlock this guard closes, not a reason to change anything here.
        print(
            "[Pixiv] refresh token missing and no interactive terminal is attached — "
            "run `gallery-dl oauth:pixiv` manually once from a real terminal to authenticate."
        )
        return None

    print("[Pixiv] refresh token missing, starting gallery-dl oauth flow...")
    try:
        subprocess.run(["gallery-dl", "oauth:pixiv"], check=True, timeout=PIXIV_OAUTH_TIMEOUT_SECONDS)
    except subprocess.CalledProcessError:
        print("[Pixiv] oauth flow failed.")
        return None
    except subprocess.TimeoutExpired:
        print(f"[Pixiv] oauth flow timed out after {PIXIV_OAUTH_TIMEOUT_SECONDS}s waiting for interactive input.")
        return None

    config_path = _gallery_dl_config_path()
    if not config_path.exists():
        print("[Pixiv] gallery-dl config.json not found after auth.")
        return None

    token = _read_gallery_dl_refresh_token()
    if token:
        tokens["pixiv_refresh_token"] = token
        save_tokens(tokens)
    return token or None
