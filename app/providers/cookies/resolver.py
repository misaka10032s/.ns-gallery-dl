from __future__ import annotations

from urllib.parse import urlparse

from app.config.settings import MULTI_PROVIDER_DOMAINS, host_matches, normalize_domain
from app.storage.db import init_db
from app.storage.repositories import cookies_repo


def resolve_cookie_file(url: str, provider: str | None = None) -> str | None:
    init_db()
    host = normalize_domain(urlparse(url).hostname)
    if not host:
        return None
    cookie_path = cookies_repo.find_cookie(host, provider)
    if cookie_path or not provider or not host_matches(host, MULTI_PROVIDER_DOMAINS):
        return cookie_path
    return cookies_repo.find_cookie(host)
