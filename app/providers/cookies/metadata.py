from __future__ import annotations

from pathlib import Path

from app.config.settings import normalize_domain


def infer_cookie_metadata(cookie_file: Path) -> tuple[str, str]:
    name = cookie_file.name.lower()
    domain = name
    provider = "shared"

    if name.startswith("cookies-") and name.endswith(".txt"):
        domain = name[len("cookies-") : -len(".txt")].replace("-", ".")
    elif name.endswith("_cookies.txt"):
        domain = name[: -len("_cookies.txt")]

    domain = normalize_domain(domain)

    if domain in {"youtube.com", "youtu.be", "x.com", "twitter.com", "facebook.com", "fb.watch"}:
        provider = "ytdlp"
    return domain, provider
