from __future__ import annotations

import re
from pathlib import Path

from app.config.paths import DOWNLOAD_DIR
from app.config.settings import normalize_domain
from app.domain.enums import Provider


def sanitize_component(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (value or "").strip())
    cleaned = cleaned.strip(" ._")
    return cleaned[:120] or fallback


def provider_root(provider: Provider, domain: str) -> Path:
    domain = sanitize_component(normalize_domain(domain) or "unknown")
    if provider == Provider.YTDLP:
        root = DOWNLOAD_DIR / "ytdlp" / domain
    elif provider == Provider.DIRECT_FILE:
        root = DOWNLOAD_DIR / "discord"
    else:
        root = DOWNLOAD_DIR / "gallery-dl" / domain
    root.mkdir(parents=True, exist_ok=True)
    return root


def pixiv_root(domain: str, author: str | None = None) -> Path:
    root = provider_root(Provider.GALLERY_DL, domain)
    if author:
        root = root / sanitize_component(author)
        root.mkdir(parents=True, exist_ok=True)
    return root


def discord_root(guild_name: str | None, kind: str) -> Path:
    guild = sanitize_component(guild_name or "unknown-guild")
    root = DOWNLOAD_DIR / "discord" / guild / sanitize_component(kind)
    root.mkdir(parents=True, exist_ok=True)
    return root


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
