from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.config.paths import DOWNLOAD_DIR
from app.config.settings import normalize_domain
from app.domain.enums import Provider

CATEGORY_ALIASES = {
    "facebook.com": "facebook",
    "fb.watch": "facebook",
    "forum.gamer.com.tw": "bahamut",
    "gamer.com.tw": "bahamut",
    "nhentai.net": "nhentai",
    "pixiv.net": "pixiv",
    "twitter.com": "x",
    "x.com": "x",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "wnacg.com": "wnacg",
}


def sanitize_component(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (value or "").strip())
    cleaned = cleaned.strip(" ._")
    return cleaned[:120] or fallback


def storage_category(domain: str | None) -> str:
    domain = normalize_domain(domain)
    return sanitize_component(CATEGORY_ALIASES.get(domain, domain) or "unknown")


def category_root(domain: str | None, subcategory: str | None = None) -> Path:
    root = DOWNLOAD_DIR / storage_category(domain)
    if subcategory:
        root = root / sanitize_component(subcategory)
    root.mkdir(parents=True, exist_ok=True)
    return root


def provider_root(provider: Provider, domain: str) -> Path:
    return category_root(domain)


def pixiv_root(domain: str, author: str | None = None) -> Path:
    return category_root(domain, author)


def discord_root(guild_name: str | None, kind: str | None = None) -> Path:
    guild = sanitize_component(guild_name or "unknown-guild")
    root = DOWNLOAD_DIR / "discord" / guild
    root.mkdir(parents=True, exist_ok=True)
    return root


def file_name_from_url(url: str, fallback: str = "file.bin") -> str:
    path_name = unquote(Path(urlparse(url).path).name)
    return path_name if path_name and "." in path_name else fallback


def unique_file_path(root: Path, filename: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / sanitize_component(filename, "file")
    if not candidate.suffix:
        candidate = candidate.with_suffix(".bin")
    counter = 1
    while candidate.exists():
        candidate = candidate.with_name(f"{candidate.stem}_{counter}{candidate.suffix}")
        counter += 1
    return candidate
