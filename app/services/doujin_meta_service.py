from __future__ import annotations

import re
import threading
import time
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path

import cloudscraper

from app.storage.repositories import cookies_repo

# ──────────────────────────────────────────────────────────────────────────────
# Gallery id extraction — reading an IDENTIFIER off the folder name, not
# interpreting the title. Real folder names put it as a leading run of
# digits separated by "_" or a space ("100873_[...]", "121697 [...]").
# exhentai folders observed in this library carry NO such prefix at all —
# see get_gallery_id_coverage(); there is deliberately no fallback (e.g. a
# title search) for that case. The user rejected using the title for
# anything, so "no id" means "no id", not "guess one".
# ──────────────────────────────────────────────────────────────────────────────

_GALLERY_ID_RE = re.compile(r"^(\d+)[_ ]")


def extract_gallery_id(folder_name: str) -> str | None:
    m = _GALLERY_ID_RE.match(folder_name)
    return m.group(1) if m else None


# ──────────────────────────────────────────────────────────────────────────────
# Fetch outcomes — a fetch attempt ALWAYS resolves to exactly one of these,
# recorded on the book row (meta_fetch_status) even when it doesn't yield
# usable fields, so a failure is visible instead of looking like "never
# tried". See doujin_service.fetch_book_metadata.
# ──────────────────────────────────────────────────────────────────────────────

FETCH_STATUS_OK = "ok"
FETCH_STATUS_BLOCKED = "blocked"
FETCH_STATUS_NOT_FOUND = "not_found"
FETCH_STATUS_NETWORK_ERROR = "network_error"
FETCH_STATUS_NO_GALLERY_ID = "no_gallery_id"
FETCH_STATUS_UNSUPPORTED = "unsupported_source"

# Which doujinshi sources currently have a working metadata fetcher, and
# their cookie-lookup domain (app.storage.repositories.cookies_repo keys
# cookies by domain — this reuses whatever cookie the user has already
# registered for that domain via the existing cookie scan/UI, never a
# hardcoded credential).
#
# Only "nhentai" is wired up. Why the other three are not (checked live,
# 2026-08-26 — not guessed):
#   - wnacg: its gallery page's own <title> is the SAME bracket-wrapped
#     string as the folder name ("[circle (artist)] title (parody) [tags]"),
#     with no separate structured artist/circle field. Fetching it would
#     just reintroduce title-guessing through a different door — the thing
#     the user explicitly rejected — so it is deliberately left unsupported
#     rather than worked around.
#   - 18comic: no existing provider module in this repo (app/providers/sites/
#     has no 18comic.py) and the site is known to gate behind additional
#     anti-bot/mobile-API requirements — out of scope for this pass.
#   - exhentai: needs a gid+token PAIR to fetch a gallery, not a bare numeric
#     id, and (see get_gallery_id_coverage) its folders in this library
#     carry no id prefix at all — nothing to fetch even if a client existed.
_COOKIE_DOMAIN_BY_SOURCE = {
    "nhentai": "nhentai.net",
}

SUPPORTED_META_SOURCES: frozenset[str] = frozenset(_COOKIE_DOMAIN_BY_SOURCE)


# ──────────────────────────────────────────────────────────────────────────────
# Rate limiting + backoff — process-wide, per site. 750 books across all four
# sources means a naive per-book loop would be 750 requests; this is what
# keeps a future bulk backfill (not built in this pass — fetch is per-book,
# on demand only) from hammering a site and getting the user's IP blocked.
# ──────────────────────────────────────────────────────────────────────────────

MIN_INTERVAL_SECONDS = 3.0  # minimum gap between requests to the SAME site
MAX_RETRIES = 2  # additional attempts beyond the first — network/5xx only
BACKOFF_SECONDS = (5.0, 15.0)  # per retry, capped at the last entry

_rate_lock = threading.Lock()
_last_request_at: dict[str, float] = {}


def _throttle(domain: str) -> None:
    with _rate_lock:
        last = _last_request_at.get(domain, 0.0)
        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        _last_request_at[domain] = time.monotonic()


def _scraper_with_cookies(domain: str) -> "cloudscraper.CloudScraper":
    """Build a scraper session, attaching whatever cookie the user has
    already registered for this domain via the repo's existing cookie
    mechanism (cookies_repo / the Cookie 管理 page) — never a hardcoded
    credential. A missing, malformed, or expired cookie file must never
    break a fetch: it just proceeds without cookies."""
    scraper = cloudscraper.create_scraper()
    try:
        cookie_path = cookies_repo.find_cookie(domain)
    except Exception:
        # A cookie LOOKUP failure (e.g. DB not yet initialized in some
        # calling context) must never abort the fetch itself — a fetch
        # attempted with no cookie is still a real attempt. Caught broadly
        # on purpose: this is a best-effort enrichment, not a required step,
        # and letting it raise here previously got misclassified as
        # "network_error" by the retry loop (bug found during live
        # verification 2026-08-26 — 3 wasted retries + backoff per book for
        # a problem retrying could never fix).
        cookie_path = None
    if cookie_path and Path(cookie_path).exists():
        jar = MozillaCookieJar(cookie_path)
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            scraper.cookies.update(jar)
        except (LoadError, OSError):
            pass
    return scraper


def fetch_metadata(source: str, gallery_id: str) -> dict:
    """Fetch one book's metadata from its source site. NEVER raises —
    returns a dict always carrying `status`; on FETCH_STATUS_OK it also
    carries title/artist/circle/page_count/source_url (any of
    title/artist/circle may be '' if the site simply doesn't have that
    field for this gallery)."""
    if source not in SUPPORTED_META_SOURCES:
        return {"status": FETCH_STATUS_UNSUPPORTED}
    if source == "nhentai":
        return _fetch_nhentai_with_retry(gallery_id)
    return {"status": FETCH_STATUS_UNSUPPORTED}  # pragma: no cover — SUPPORTED_META_SOURCES guards this


def _fetch_nhentai_with_retry(gallery_id: str) -> dict:
    from app.providers.sites import nhentai as nhentai_provider

    domain = _COOKIE_DOMAIN_BY_SOURCE["nhentai"]
    attempt = 0
    while True:
        _throttle(domain)
        try:
            scraper = _scraper_with_cookies(domain)
            result = nhentai_provider.fetch_gallery_metadata(gallery_id, scraper=scraper)
            return {"status": FETCH_STATUS_OK, **result}
        except LookupError:
            return {"status": FETCH_STATUS_NOT_FOUND}
        except RuntimeError:
            return {"status": FETCH_STATUS_BLOCKED}
        except Exception:
            if attempt >= MAX_RETRIES:
                return {"status": FETCH_STATUS_NETWORK_ERROR}
            time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
            attempt += 1
