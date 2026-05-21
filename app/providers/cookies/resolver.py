from __future__ import annotations

from urllib.parse import urlparse

from app.config.settings import normalize_domain
from app.storage.db import init_db
from app.storage.repositories import cookies_repo


def resolve_cookie_file(url: str, provider: str | None = None) -> str | None:
    init_db()
    host = normalize_domain(urlparse(url).hostname)
    if not host:
        return None
    return cookies_repo.find_cookie(host, provider)
