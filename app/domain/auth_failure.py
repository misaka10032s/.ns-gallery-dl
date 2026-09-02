from __future__ import annotations

import re

from app.config.downloaders import is_stale_extractor_error

# Three-way classifier for a download failure's error text: does it signal a
# missing/invalid/insufficient AUTHENTICATION credential, does it CONFIDENTLY
# signal something else (network/5xx/genuinely-missing-content/bot-challenge —
# doesn't matter WHAT, just that it is definitely not a credential problem), or
# is it genuinely AMBIGUOUS between the two? Forcing every failure into a
# binary auth/not-auth guess would be dishonest — some strings really cannot be
# told apart from a plain 404 (see `AUTH_INDETERMINATE` cases below, each cited
# against the real error text this app produced, per the dispatch brief).
#
# Deliberately NOT keyed on any site/domain name (no allowlist to rot). Every
# signature is a signal both download engines emit from a SHARED base class —
# gallery-dl's exception hierarchy (venv/Lib/site-packages/gallery_dl/
# exception.py) and yt-dlp's InfoExtractor.raise_login_required() /
# ._login_hint() (yt_dlp/extractor/common.py) — so a newly-added site inherits
# the same signal for free the moment its extractor calls the shared helper;
# no per-site maintenance is needed when a new site is wired up.
AUTH = "auth"
NOT_AUTH = "not_auth"
INDETERMINATE = "indeterminate"


# ---------------------------------------------------------------------------
# gallery-dl signals
# ---------------------------------------------------------------------------
#
# gallery-dl's job.py logs its own exceptions in one of two shapes (verified
# directly against the installed package, venv/Lib/site-packages/gallery_dl/
# job.py:163-176):
#   - `exception.AbortExtraction` -> logged as the BARE `exc.message`, no class
#     name prefix (`log.error(exc.message)`).
#   - every OTHER `exception.GalleryDLException` subclass (HttpError,
#     AuthRequired, AuthenticationError, AuthorizationError, NotFoundError, ...)
#     -> logged as `"{ClassName}: {message}"` (`log.error("%s: %s",
#     exc.__class__.__name__, exc)`).
# Both land in the `[<extractor>][error] ...` line this app's
# `_last_error_line()` extracts (see app/providers/gallery_dl/provider.py).

# AuthRequired / AuthenticationError / AuthorizationError (exception.py:89-119)
# exist ONLY to signal "credentials required or insufficient" — gallery-dl
# never raises any of these three for a not-found/network/bot-challenge case.
# Real example: `[twitter][error] AuthRequired: Protected Tweet`.
_GALLERY_DL_AUTH_CLASS_RE = re.compile(
    r"\b(AuthRequired|AuthenticationError|AuthorizationError)\b"
)

# `HttpError.__init__` (exception.py:63-77) formats an HTTP failure as
# `'{status} {reason}' for '{url}'`. 401 Unauthorized is unambiguous per HTTP
# semantics (RFC 7235) — the server IS asking for authentication. 403 is
# deliberately NOT included here: gallery-dl's own Cloudflare/bot-block paths
# also surface as a bare 403 (no Auth* class), so a 403 alone cannot be told
# apart from an interactive-challenge block (see AUTH_INDETERMINATE below).
_HTTP_401_RE = re.compile(r"'401\s")
_HTTP_403_RE = re.compile(r"'403\s")
_HTTP_404_RE = re.compile(r"'404\s")
_HTTP_5XX_RE = re.compile(r"'5\d\d\s")

# `NotFoundError` (exception.py:121-127) is gallery-dl's generic
# "gallery/image could not be found" — genuinely ambiguous: deleted content and
# "exists but hidden without login" (e.g. pixiv R-18 without an authenticated
# session) both raise this SAME class. Real example: `[pixiv][error]
# NotFoundError: Requested resource (gallery/image) could not be found`
# (11 occurrences in this app's real job history, tallied directly against
# this app's jobs table).
_GALLERY_DL_NOT_FOUND_RE = re.compile(r"\bNotFoundError\b")

# `ChallengeError` (exception.py:79-87, a HttpError subclass) is gallery-dl's
# OWN name for a Cloudflare/bot-detection interactive challenge — confidently
# NOT a missing-credential problem (supplying a cookie does not solve a
# CAPTCHA), so this is NOT_AUTH rather than AUTH or INDETERMINATE.
_GALLERY_DL_CHALLENGE_RE = re.compile(r"\bChallengeError\b")

# Multiple gallery-dl site extractors (deviantart.py, postmill.py, seiga.py,
# tiktok.py, weibo.py — grep-verified against the installed package; each
# implements this independently, so it is a recurring gallery-dl IDIOM rather
# than one shared function, but the text is identical) raise
# `AbortExtraction(f"HTTP redirect to {page} page (...)")`. Instagram's own
# base Extractor.request() (extractor/instagram.py:174-186) uses the SAME
# `page` values: "login", "challenge", "home". "login" is unambiguous — the
# site itself redirected an unauthenticated request to its login page. Real
# example: `[instagram][error] HTTP redirect to login page
# (https://www.instagram.com/accounts/login/)` (4 occurrences in this app's
# real job history, tallied directly against this app's jobs table).
_REDIRECT_TO_LOGIN_RE = re.compile(r"redirect to login page", re.IGNORECASE)
# "redirect to challenge page" is instagram's own bot-challenge redirect (same
# call site as above, `page = "challenge"`) — a CAPTCHA/challenge wall, not a
# plain missing-credential state, so classified NOT_AUTH like ChallengeError.
_REDIRECT_TO_CHALLENGE_RE = re.compile(r"redirect to challenge page", re.IGNORECASE)


# ---------------------------------------------------------------------------
# yt-dlp signals
# ---------------------------------------------------------------------------
#
# EVERY yt-dlp extractor that needs to say "you must be logged in" calls the
# shared `InfoExtractor.raise_login_required()` / `._login_hint()`
# (yt_dlp/extractor/common.py:596-605, grep-verified against the installed
# package) — never its own ad hoc wording. `_login_hint()`'s four variants all
# differ in exact phrasing, but grepping the ENTIRE installed yt_dlp package
# for `--cookies-from-browser` shows it is used ONLY inside `_login_hint()`
# itself plus three site-specific messages that are THEMSELVES about a stale/
# invalid login session (medici.py, nfl.py, sharepoint.py) — no unrelated
# yt-dlp message anywhere mentions this flag. So its presence is a safe,
# provider-agnostic AUTH signal covering every yt-dlp site that calls the
# shared helper, with zero site-specific maintenance. Real example (this
# app's own real job history): "...Use --cookies, --cookies-from-browser,
# --username and --password, --netrc-cmd, or --netrc (twitter) to provid[e
# account credentials]..." (`raise_login_required()` called from
# yt_dlp/extractor/twitter.py:1092 on a Protected-tweet result).
_YTDLP_LOGIN_HINT_RE = re.compile(r"--cookies-from-browser", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Cross-engine NOT_AUTH signals — reused from the existing, already-reviewed
# stale-extractor classifier (app/services/updater_service.py), plus plain
# network/timeout shapes. These are confidently NOT a credential problem —
# retrying with the SAME or DIFFERENT credentials would never fix an extractor
# bug or a dropped connection, so misclassifying one of these as "auth" would
# wrongly arm the cooldown (app/domain/auth_cooldown.py) and block a
# legitimate retry that has nothing to do with login state.
# ---------------------------------------------------------------------------
#
# LIVES IN app/domain (not app/services): its only app.* dependency is
# app.config.downloaders.is_stale_extractor_error (a pure predicate over a
# constant tuple — moved there from app.services.updater_service alongside
# this module, 2026-09-02, so this classifier's only import is to the BOTTOM
# layer). app.providers (which classifies every download failure) sits above
# app.domain in the layers contract, so app.providers -> app.domain is legal;
# the old app.providers -> app.services placement was not.
_NETWORK_SIGNATURES: tuple[str, ...] = (
    "connection",
    "timed out",
    "timeout",
    "max retries exceeded",
    "name or service not known",
    "temporary failure in name resolution",
    "errno",
)


def classify(error: str | None) -> str:
    """Classify a download failure's error text as AUTH / NOT_AUTH /
    INDETERMINATE. `error` is the raw text this app already captures into
    `DownloadResult.error` (gallery-dl's `_last_error_line()` /
    `app.providers.gallery_dl.provider`; yt-dlp's last output line /
    `app.providers.ytdlp.provider`) — NOT yet sanitized. Callers that persist
    or display the classified error text (rather than just branching on the
    returned label) MUST still route that text through
    `app.domain.error_sanitizer.sanitize_error()` first — this function only
    classifies, it never redacts.

    Order matters: definite signals are checked before the ambiguous ones, so
    an error string that happens to ALSO contain an ambiguous marker (e.g. a
    404-shaped HttpError that also mentions "NotFoundError" in a nested repr)
    is still resolved by whichever signal fires first in this list — currently
    none of the signals below can co-occur in a single real gallery-dl/yt-dlp
    message (each engine only ever emits ONE top-level exception per failure),
    so this ordering is a defensive default rather than a load-bearing rule
    today.
    """
    if not error:
        return INDETERMINATE

    # Reuse the existing, already-reviewed stale-extractor classifier — an
    # extractor bug is confidently NOT a credential problem.
    if is_stale_extractor_error(error):
        return NOT_AUTH

    if _GALLERY_DL_AUTH_CLASS_RE.search(error):
        return AUTH
    if _REDIRECT_TO_LOGIN_RE.search(error):
        return AUTH
    if _HTTP_401_RE.search(error):
        return AUTH
    if _YTDLP_LOGIN_HINT_RE.search(error):
        return AUTH

    if _GALLERY_DL_CHALLENGE_RE.search(error):
        return NOT_AUTH
    if _REDIRECT_TO_CHALLENGE_RE.search(error):
        return NOT_AUTH
    if _HTTP_404_RE.search(error):
        return NOT_AUTH
    if _HTTP_5XX_RE.search(error):
        return NOT_AUTH
    lowered = error.lower()
    if any(signature in lowered for signature in _NETWORK_SIGNATURES):
        return NOT_AUTH

    if _GALLERY_DL_NOT_FOUND_RE.search(error):
        return INDETERMINATE
    if _HTTP_403_RE.search(error):
        return INDETERMINATE

    # No known signal matched at all — genuinely unclassifiable rather than a
    # forced guess. This is the bucket a never-seen-before error message (a
    # brand-new site, a changed engine version) falls into by default; it is
    # deliberately the SAFE default (never silently treated as "auth" and
    # never silently treated as "definitely fine either") — see dispatch
    # brief: "An indeterminate that says so is more useful than a confident
    # wrong label."
    return INDETERMINATE
