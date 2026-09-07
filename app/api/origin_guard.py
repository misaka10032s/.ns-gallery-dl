"""Origin/Host guard for state-changing requests (待回答 #47).

The Web UI's API binds to loopback only (`app/api/app.py::run_server`,
default `127.0.0.1:7601`), but until this module nothing server-side
verified that a state-changing request actually came from this machine's
own frontend: this app has ZERO session/token auth on any mutating endpoint
(see `app/api/routes/misc.py::_check_same_origin`'s own docstring, which
states this plainly), and before this change only TWO routes even had that
narrower, Origin-or-Referer-hostname-only check
(`/api/cookies*`, `POST /api/downloaders/update`) — every other mutating
route (`POST /api/jobs`, `POST /download`, `POST /api/jobs/<id>/retry`,
`DELETE`/`PUT /api/history`, `POST /api/history/requeue`, every
`/api/gallery/doujin/*` mutation) had NO same-origin check at all. A
malicious page open in the same browser (classic drive-by CSRF) — or a
DNS-rebinding attacker who gets a victim's browser to resolve some domain to
127.0.0.1 — could already reach every one of those with no defence but the
browser's own same-origin policy, which a non-credentialed "simple" request
does not need to satisfy to be SENT (only to have its response read).

This module is the ONE shared, generalized guard: registered once, globally,
via `app.before_request` in `app/api/app.py::create_app()`, so it applies to
every current AND future mutating route with no per-route opt-in to forget.
It does not replace `_check_same_origin` (left in place, unchanged, for its
own existing test coverage — `tests/test_csrf_protection.py`,
`tests/test_downloaders_route.py`, `tests/test_cookie_cooldown_route.py`) —
running both on the two routes that already had it is strictly more
defensive, never less; this guard is what NOW additionally covers every
route that previously had nothing.

Checks, in order (POST/PUT/PATCH/DELETE only — GET/HEAD/OPTIONS exempt):

* `Host` header (if present) must name this machine (loopback: 127.0.0.1 /
  localhost / ::1) AND the exact configured API port
  (`app.config.settings.API_PORT`) — never skipped just because a port is
  absent from the header (an absent port compares against the HTTP scheme
  default, 80, UNCONDITIONALLY, so it fails unless the server itself is
  bound to port 80).
* `Origin` header (if present) must be an EXACT match (never a substring or
  any-port check) against `resolve_allowed_origins()`. A `null` Origin
  (a sandboxed iframe, a `file://` page, or a redirected cross-origin
  request) is always rejected.
* Requests with NEITHER header present (a local CLI tool, e.g. `curl` run
  from the user's own shell) pass on the Host check alone — this is the
  intended local-tool path, not a bypass: a real browser always sends
  `Origin` on a cross-origin (or same-origin state-changing) request, so the
  absence of both headers never lets a remote/browser attacker through.

This repo's own Chrome extension (`chromeExtension/`) issues cross-origin
POSTs whose Origin is `chrome-extension://<extension-id>`, which is NOT in
the default allow-list (待回答 #47 review F1 — deliberately: blanket-allowing
the `chrome-extension://` SCHEME would admit every extension installed in
the browser, not just this one, and this app has no other auth to fall back
on). The owner enables it explicitly with a concrete id, one entry:
`NS_MEDIA_HUB_EXTRA_ORIGINS=chrome-extension://<32-char-id>` (find the id at
`chrome://extensions` with 開發人員模式 on). A rejected Origin is logged once
per distinct value per process with the exact env line to add — see
`_log_origin_rejection_once`.
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlsplit

from flask import Flask, jsonify, request

from app.config.settings import API_PORT

_logger = logging.getLogger(__name__)

STATE_CHANGING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_LOOPBACK_HOSTNAMES: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})

# Vite's own default dev-server port. frontend/vite.config.js sets no
# `server.port`, so `npm run dev` binds Vite's default, 5173 (see
# .claude/CLAUDE.md `## Run commands` -> Frontend). frontend/src/api/
# client.js only ever fetches RELATIVE `/api/...` paths — there is no proxy
# configured in vite.config.js and no absolute-URL fallback anywhere in the
# frontend source — so this origin has no real production call path into the
# API today. Included anyway because the repo documents 5173 as a real,
# intentional UI port; a future dev-mode direct-fetch wiring must not be
# silently blocked by this guard the day someone adds it.
_VITE_DEV_PORT = 5173

# Comma-separated list of additional allowed Origins, following this repo's
# existing `NS_MEDIA_HUB_*` env-naming convention (see
# app.config.paths.NS_MEDIA_HUB_DATA_DIR / NS_MEDIA_HUB_DOWNLOAD_DIR,
# app.config.settings.NS_MEDIA_HUB_API). Each entry must be a concrete
# `scheme://host[:port]` with no path/query/fragment (or a concrete
# `chrome-extension://<32-char id>` — see below); an entry containing
# `*` is dropped with a WARNING rather than silently ignored or accepted —
# see `docs/blueprint/entries/BP-CORE-SECURITY-1.md` and `.env.example`.
_ENV_EXTRA_ORIGINS = "NS_MEDIA_HUB_EXTRA_ORIGINS"

# Chrome/Chromium extension IDs are exactly 32 characters drawn from the
# 16-letter alphabet a-p (each nibble of a 128-bit hash mapped to a-p rather
# than 0-9a-f) — see Chromium's `crx_id::HashedExtensionId` /
# `RandomId::IdFromHash`. This is deliberately NOT a blanket
# `chrome-extension://` allow (待回答 #47 review F1: that would admit every
# extension installed in the user's browser, not just the owner's own one);
# it accepts only one CONCRETE id per env entry, same strictness as the
# http(s) branch below (exact match, no port, no path/query/fragment).
_CHROME_EXTENSION_ORIGIN_RE = re.compile(r"^chrome-extension://[a-p]{32}$")


def _parse_extra_origins(raw: str) -> list[str]:
    origins: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "*" in item:
            print(
                f"[origin-guard] WARNING: ignoring wildcard origin entry {item!r} from "
                f"{_ENV_EXTRA_ORIGINS} — wildcard origins are never allowed."
            )
            continue
        if item.startswith("chrome-extension://"):
            if _CHROME_EXTENSION_ORIGIN_RE.match(item):
                origins.append(item)
            else:
                print(
                    f"[origin-guard] WARNING: ignoring malformed chrome-extension origin entry "
                    f"{item!r} from {_ENV_EXTRA_ORIGINS} — expected exactly "
                    f"chrome-extension://<32-char id> (id = a-p only, no path)."
                )
            continue
        split = urlsplit(item)
        if split.scheme not in {"http", "https"} or not split.hostname or split.path or split.query or split.fragment:
            print(
                f"[origin-guard] WARNING: ignoring malformed origin entry {item!r} from "
                f"{_ENV_EXTRA_ORIGINS} — expected exactly scheme://host[:port], no path."
            )
            continue
        origins.append(item.rstrip("/"))
    return origins


def resolve_allowed_origins() -> list[str]:
    """The single allow-list `Origin` is checked against. Computed fresh on
    every call (never cached at import time) so a test — or a future runtime
    config reload — can change `API_PORT` / the env var and see it take
    effect immediately, the same freshness guarantee `_check_same_origin`
    already has by virtue of reading `request.headers` live."""
    origins: list[str] = []
    for hostname in ("127.0.0.1", "localhost", "[::1]"):
        origins.append(f"http://{hostname}:{API_PORT}")
    for hostname in ("127.0.0.1", "localhost"):
        origins.append(f"http://{hostname}:{_VITE_DEV_PORT}")
    origins.extend(_parse_extra_origins(os.environ.get(_ENV_EXTRA_ORIGINS, "")))
    seen: set[str] = set()
    deduped: list[str] = []
    for origin in origins:
        if origin not in seen:
            seen.add(origin)
            deduped.append(origin)
    return deduped


def _host_header_matches(host_header: str) -> bool:
    """`host_header` is the raw `Host` value (`"127.0.0.1:7601"`,
    `"localhost"`, `"[::1]:7601"`, ...). Parsed via `urlsplit` on a synthetic
    `"//" + host_header` so IPv6 bracket syntax is handled for free. An
    absent port in the header resolves to `None` from `urlsplit`, normalized
    here UNCONDITIONALLY to the HTTP scheme default (80) — never skipped —
    so a bare `Host: 127.0.0.1` (no port) fails against a server bound to
    any port other than 80."""
    try:
        split = urlsplit(f"//{host_header}")
    except ValueError:
        return False
    hostname = (split.hostname or "").lower()
    try:
        port = split.port if split.port is not None else 80
    except ValueError:
        return False
    return hostname in _LOOPBACK_HOSTNAMES and port == API_PORT


def _reject(reason_zh: str):
    return jsonify({"error": reason_zh}), 403


# Distinct rejected `Origin` values already logged in THIS process — module-
# level so the dedupe survives across requests/tests within one run
# (待回答 #47 review F1b). Deliberately unbounded: an attacker who wants to
# blow this up would need to send a new distinct Origin value on every
# request, which does not change what gets through the guard (still 403
# either way) — it would only cost a little memory, not security.
_rejected_origins_logged: set[str] = set()


def _log_origin_rejection_once(origin_header: str) -> None:
    """Logs, at most once per distinct rejected `Origin` value per process, a
    WARNING telling the operator how to allow it — most commonly their own
    Chrome extension's `chrome-extension://<id>` Origin, which this guard
    rejects by default (see the module docstring's chrome-extension note).
    Never logs the request body — only the Origin header value itself.
    Uses the `logging` module (unlike this file's env-parsing warnings,
    which `print` — those run at import/startup before any request context;
    this one fires per-request and is what a test captures via `caplog`)."""
    if origin_header in _rejected_origins_logged:
        return
    _rejected_origins_logged.add(origin_header)
    _logger.warning(
        "拒絕請求，因為 Origin 不在允許清單內：%r。若這是你自己的 Chrome 擴充功能，"
        "把 `NS_MEDIA_HUB_EXTRA_ORIGINS=%s` 加進 .env 後重啟。",
        origin_header,
        origin_header,
    )


def register(app: Flask) -> None:
    """Registers the guard as a global `before_request` hook — applies to
    EVERY route this Flask app serves, present or future, with no per-route
    opt-in required."""

    @app.before_request
    def _origin_host_guard():
        if request.method.upper() not in STATE_CHANGING_METHODS:
            return None

        host_header = request.headers.get("Host")
        if host_header is not None and not _host_header_matches(host_header):
            return _reject("請求的 Host 不是本機服務位址，已拒絕。")

        origin_header = request.headers.get("Origin")
        if origin_header is not None:
            allowed = resolve_allowed_origins()
            if origin_header == "null" or origin_header not in allowed:
                _log_origin_rejection_once(origin_header)
                return _reject("請求的 Origin 不在允許清單內，已拒絕。")
        # else: no Origin header at all — see module docstring's third bullet.

        return None
