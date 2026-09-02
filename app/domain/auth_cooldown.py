from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from app.config.settings import cooldown_domain_key
from app.domain.error_sanitizer import sanitize_error
from app.storage.db import init_db
from app.storage.repositories import auth_cooldown_repo

# LIVES IN app/domain (not app/services): its only app.* dependencies are
# app.domain.error_sanitizer (same layer) and app.storage.{db,repositories}
# (below app.domain in the layers contract, pyproject.toml
# [tool.importlinter]). app.providers (which arms/checks this cooldown on
# every credentialed request) sits ABOVE app.domain, so app.providers ->
# app.domain is a legal downward import; the old app.providers ->
# app.services placement was not (2026-09-02 G4 layer-violation fix — see
# the layers contract in pyproject.toml [tool.importlinter]).
#
# Duration + scope, decided (dispatch brief, item 1):
#
# - SCOPE: per DOMAIN, never per-account or per-provider. This app has no
#   concept of "account" anywhere in its schema (cookie_entries is keyed by
#   domain+provider, not by which logged-in identity a cookie belongs to), so
#   "per-account" is not a distinction this codebase can currently make — the
#   only thing degrading is "the one jar this app has for domain X". Not
#   per-provider either: gallery-dl and yt-dlp are both tried for the SAME
#   domain on some sites (app.config.settings.MULTI_PROVIDER_DOMAINS —
#   facebook.com/fb.watch/twitter.com/x.com) against the SAME cookie file, so
#   letting provider B immediately hammer the same doomed cookie right after
#   provider A got auth-rejected would defeat the whole point.
# - DURATION: 6 hours — now a CEILING, not the only way out (revised
#   2026-09-02 round 2, following a reviewer's fix-round-1 write-up). The original
#   justification ("matches UPDATE_COOLDOWN_SECONDS") was an analogy to an
#   unrelated guard (a pip-update throttle), not a derivation, and — more
#   importantly — a fixed wait with NO escape hatch could strand the owner for
#   up to 6h after they had already fixed the problem by re-seeding a cookie.
#   Two escape hatches now exist, so 6h only ever applies when the owner does
#   nothing:
#     1. `clear_cooldown()` below fires the instant the cookie jar for that
#        domain changes — hooked into app.services.cookie_service.save_cookie()
#        / delete_cookie(), the write path every UI/API cookie edit goes
#        through (see that module).
#     2. `in_cooldown()` also self-heals if the cookie FILE on disk was
#        modified more recently than the cooldown was last armed/refreshed
#        (`_cookie_changed_since()` below) — this catches a jar rewritten by a
#        path OTHER than save_cookie() (e.g. a MULTI_PROVIDER_DOMAINS sibling
#        domain string sharing the same physical cookie file, or a manual
#        out-of-band file replace) without needing a snapshot/diff subsystem.
#   As a ceiling, 6h is sized against what these engines' own auth/rate-limit
#   walls actually look like: gallery-dl/yt-dlp surface a REJECTED request
#   immediately (no engine-side backoff to wait out), and the sites this app
#   talks to that soft-lock an account after repeated failed authenticated
#   requests (this app's own real job history shows this on twitter/x.com
#   and instagram — 60 and 4 occurrences respectively, tallied directly
#   against this app's jobs table) typically clear such a block within minutes
#   to a low number of hours, not days; 6h sits comfortably above that band so
#   this app never itself becomes the SECOND thing hammering a site that just
#   soft-locked it, while never blocking the owner from ending it early via
#   either hatch above. No platform publishes an exact figure for these
#   anti-abuse windows, so this remains a deliberately generous, bounded
#   default rather than a literal SLA number — recorded honestly as that.
# - BOUND: a single fixed TTL, NOT an exponential backoff. Every cooldown
#   write sets the SAME 6h offset from "now" regardless of how many prior
#   auth failures happened for this domain — this cannot grow unbounded.
#   Phase 1b's cookie-name-set snapshot (dispatch brief "Do NOT do these") is
#   still deferred — the two hatches above are deliberately simpler than that
#   machinery and do not replace it; they close the "the owner already fixed
#   it but has to wait anyway" gap this phase's own brief called out.
AUTH_COOLDOWN_SECONDS = 6 * 60 * 60


def _cookie_changed_since(state: dict, cookie_path: str | Path) -> bool:
    """True if the file at `cookie_path` was modified more recently than
    `state['updated_at']` (the last time this domain's cooldown was armed or
    refreshed). Uses the cooldown row's EXISTING `updated_at` column as the
    baseline — no schema change, no new column, no snapshot machinery: any
    write to the jar (this app's own atomic `cookie_service.save_cookie()`,
    or gallery-dl's/yt-dlp's own cookie-jar write-back after a run) bumps the
    file's mtime, and a bump past `updated_at` means the jar this cooldown
    was armed against is no longer the jar on disk today."""
    try:
        mtime = Path(cookie_path).stat().st_mtime
    except OSError:
        return False
    try:
        recorded = datetime.fromisoformat(state["updated_at"])
    except (KeyError, ValueError):
        return False
    # `updated_at` is stored with WHOLE-SECOND precision
    # (record_auth_failure uses isoformat(timespec="seconds")), but a file's
    # mtime carries sub-second precision. Comparing them directly would treat
    # a cookie written in the SAME wall-clock second the cooldown was armed
    # as "changed" purely from microsecond noise — a real, likely case, since
    # the failed request that triggers record_auth_failure() already touched
    # this same jar moments earlier. Flooring mtime to whole seconds before
    # comparing means only a write in a LATER second counts (at most a 1s
    # detection delay, irrelevant against a multi-hour cooldown) — without
    # this floor, the cooldown could self-clear the instant it's armed.
    mtime_floor = datetime.fromtimestamp(int(mtime))
    return mtime_floor > recorded


def in_cooldown(domain: str, cookie_path: str | Path | None = None) -> tuple[bool, str | None]:
    """Returns (True, cooldown_until_iso) if `domain` is still within its
    auth-failure cooldown window, else (False, None). Checked BEFORE a
    credentialed request is attempted — the whole point is that a job never
    even makes the request while the domain is cooling down.

    `cookie_path`, if given, is the cookie file THIS caller is about to use
    for `domain` — if it was modified more recently than the cooldown was
    last armed, the cooldown is treated as stale, cleared, and (False, None)
    is returned immediately (no TTL check needed — a changed cookie always
    wins). Optional and backward-compatible: omitting it (the default)
    reproduces the exact prior TTL-only behaviour.

    `domain` is collapsed through cooldown_domain_key() before every lookup
    (see app.config.settings.cooldown_domain_key docstring) so a
    twitter.com/x.com or facebook.com/fb.watch cooldown is found regardless
    of which alias THIS caller's job URL happened to use."""
    if not domain:
        return False, None
    domain = cooldown_domain_key(domain)
    init_db()
    state = auth_cooldown_repo.get_state(domain)
    if not state or not state.get("cooldown_until"):
        return False, None
    if cookie_path and _cookie_changed_since(state, cookie_path):
        auth_cooldown_repo.delete_state(domain)
        return False, None
    try:
        until = datetime.fromisoformat(state["cooldown_until"])
    except ValueError:
        return False, None
    if datetime.now() < until:
        return True, state["cooldown_until"]
    return False, None


def record_auth_failure(domain: str, error: str | None = None) -> str:
    """Arm/refresh the cooldown for `domain` after a download failure was
    classified AUTH (app.domain.auth_failure.classify). Returns the new
    cooldown_until ISO timestamp. `error`, if given, is routed through
    app.domain.error_sanitizer.sanitize_error() before being persisted —
    the dispatch brief's hard rule that every classified message reaching the
    DB must pass through the existing sanitizer first. `domain` is collapsed
    through cooldown_domain_key() first, same as in_cooldown()/
    clear_cooldown(), so all three agree on identity for an aliased pair."""
    if not domain:
        raise ValueError("A domain is required to record an auth-failure cooldown.")
    domain = cooldown_domain_key(domain)
    init_db()
    now = datetime.now()
    until = now + timedelta(seconds=AUTH_COOLDOWN_SECONDS)
    until_iso = until.isoformat(timespec="seconds")
    sanitized_error = sanitize_error(error) if error else ""
    auth_cooldown_repo.set_state(domain, until_iso, sanitized_error, now.isoformat(timespec="seconds"))
    return until_iso


def clear_cooldown(domain: str) -> bool:
    """Manually end `domain`'s cooldown immediately, regardless of the TTL.
    Two callers, both legitimate ends to a cooldown that would otherwise wait
    out the fixed AUTH_COOLDOWN_SECONDS window:

    1. `app.services.cookie_service.save_cookie()` / `delete_cookie()` — every
       time the owner re-seeds or removes a cookie jar via the UI/API, on the
       theory that a cookie change IS the fix the cooldown was waiting for.
    2. The manual override endpoint (`DELETE /api/cookies/<domain>/cooldown`,
       app/api/routes/misc.py) — for when the owner wants to force a retry
       right now without touching the cookie file at all (e.g. they believe
       the site's own block already lifted).

    Idempotent: returns True if a cooldown row existed and was removed, False
    if there was nothing to clear — callers never need to check first.
    `domain` is collapsed through cooldown_domain_key() first: re-seeding a
    cookie saved under EITHER alias of a MULTI_PROVIDER_DOMAINS rebrand pair
    (twitter.com/x.com, fb.watch/facebook.com) clears the shared cooldown
    row regardless of which spelling armed it."""
    if not domain:
        return False
    domain = cooldown_domain_key(domain)
    init_db()
    return auth_cooldown_repo.delete_state(domain)


def cooldown_message(domain: str, until_iso: str) -> str:
    """zh-TW message surfaced on DownloadResult.error for a job that was
    skipped entirely because its domain is still cooling down — distinct from
    the ORIGINAL auth-failure message (which triggered the cooldown), so an
    operator can tell "this job actually failed auth" from "this job never
    even tried, because a PRIOR job already did"."""
    return f"{domain} 目前處於認證失敗冷卻期（至 {until_iso} 為止），本次未帶憑證重試，避免鎖帳號/rate-limit"
