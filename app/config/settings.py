from __future__ import annotations

import os
from typing import Iterable

from dotenv import load_dotenv

from .paths import ENV_FILE


load_dotenv(ENV_FILE)

APP_NAME = "NS Media Hub"
APP_SLUG = "ns-media-hub"
APP_VERSION = "2.0.0"
LOCAL_API_BASE = os.environ.get("NS_MEDIA_HUB_API", "http://127.0.0.1:7601")


def _csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _csv_int_set(raw: str) -> set[int]:
    values: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            values.add(int(item))
    return values


def normalize_domain(host: str | None) -> str:
    host = (host or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m.") and host.count(".") >= 2:
        host = host[2:]
    if host.startswith("mobile.") and host.count(".") >= 2:
        host = host[7:]
    return host


GALLERY_DL_DOMAINS = {
    "art.ngfiles.com",
    "artstation.com",
    "bsky.app",
    "civitai.com",
    "coomer.st",
    "danbooru.donmai.us",
    "deviantart.com",
    "fanbox.cc",
    "flickr.com",
    "gelbooru.com",
    "imgur.com",
    "instagram.com",
    "kemono.cr",
    "konachan.com",
    "nhentai.net",
    "patreon.com",
    "pinterest.com",
    "pinterest.co.uk",
    "pin.it",
    "pixiv.net",
    "reddit.com",
    "sankaku.app",
    "skeb.jp",
    "tumblr.com",
    "wnacg.com",
    "yande.re",
}
GALLERY_DL_DOMAINS.update(_csv_set(os.environ.get("BOT_EXTRA_GALLERYDL_DOMAINS", "")))

MULTI_PROVIDER_DOMAINS = {
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
}

# Rebrand/alias pairs WITHIN MULTI_PROVIDER_DOMAINS that are the SAME site
# under two spellings, not two different sites — twitter.com was renamed to
# x.com; fb.watch is Facebook's own short-link domain for the same account.
# normalize_domain() deliberately does NOT collapse these: cookie file
# naming (app.services.cookie_service._cookie_file_name) and the
# cookie_entries registry stay keyed on the caller's literal, un-aliased
# domain, unaffected by this map. Only the auth-failure cooldown
# (app.domain.auth_cooldown) needs the two spellings folded into one
# identity — see cooldown_domain_key() below for why.
DOMAIN_COOLDOWN_ALIASES: dict[str, str] = {
    "twitter.com": "x.com",
    "fb.watch": "facebook.com",
}


def cooldown_domain_key(domain: str) -> str:
    """Canonical auth-failure-cooldown key for `domain` (already
    normalize_domain()'d by the caller): collapses a known rebrand alias
    (DOMAIN_COOLDOWN_ALIASES) onto one spelling.

    Without this, app.domain.auth_cooldown.in_cooldown() /
    record_auth_failure() / clear_cooldown() each key their SQLite row on
    whatever spelling the caller happened to pass — a job URL's literal
    hostname for in_cooldown()/record_auth_failure(), the owner's UI/API
    domain field for clear_cooldown() (via cookie_service.save_cookie() /
    delete_cookie()). Those two are not guaranteed to agree: a cooldown
    armed while a job hit a "twitter.com" URL would then survive the owner
    re-seeding a cookie under "x.com" (or vice versa), because
    clear_cooldown("x.com") and the stored row keyed "twitter.com" are, by
    SQLite's PRIMARY KEY, two unrelated rows. Used ONLY by
    app.domain.auth_cooldown — nowhere else needs this collapse."""
    return DOMAIN_COOLDOWN_ALIASES.get(domain, domain)

YTDLP_DOMAINS = {
    "facebook.com",
    "fb.watch",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
}
YTDLP_DOMAINS.update(_csv_set(os.environ.get("BOT_EXTRA_YTDLP_DOMAINS", "")))

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_IDS = _csv_int_set(os.environ.get("DISCORD_CHANNEL_IDS", ""))
DISCORD_EMOJI_QUEUED = os.environ.get("DISCORD_EMOJI_QUEUED", "⏳")
DISCORD_EMOJI_DONE = os.environ.get("DISCORD_EMOJI_DONE", "✅")
DISCORD_EMOJI_FAILED = os.environ.get("DISCORD_EMOJI_FAILED", "❌")

# Consecutive wnacg-provider failures (across ALL entry points — web UI, queue,
# bot) before app.providers.sites.wnacg_health fires ONE Discord alert for the
# current outage episode. A single transient failure must never alert, so the
# default is intentionally > 1.
WNACG_ALERT_THRESHOLD = int(os.environ.get("WNACG_ALERT_THRESHOLD", "3") or "3")

BOT_DOMAIN_ALLOWLIST = {normalize_domain(item) for item in _csv_set(os.environ.get("BOT_DOMAIN_ALLOWLIST", ""))}
BOT_DOMAIN_DENYLIST = {normalize_domain(item) for item in _csv_set(os.environ.get("BOT_DOMAIN_DENYLIST", ""))}


def is_domain_allowed(host: str) -> bool:
    host = normalize_domain(host)
    if BOT_DOMAIN_DENYLIST and host in BOT_DOMAIN_DENYLIST:
        return False
    if BOT_DOMAIN_ALLOWLIST:
        return host in BOT_DOMAIN_ALLOWLIST
    return True


def host_matches(host: str, candidates: Iterable[str]) -> bool:
    host = normalize_domain(host)
    for candidate in candidates:
        candidate = normalize_domain(candidate)
        if host == candidate or host.endswith(f".{candidate}"):
            return True
    return False
