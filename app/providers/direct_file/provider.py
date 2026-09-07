from __future__ import annotations

import contextlib
import mimetypes
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.config.settings import normalize_domain
from app.domain.enums import JobStatus, Provider
from app.domain.jobs import DownloadResult
from app.domain.network_safety import MAX_REDIRECT_HOPS, UnsafeUrlError, is_safe_url
from app.services.path_service import discord_root, file_name_from_url, provider_root, unique_file_path

# 待回答 #48: `urlopen()` follows redirects automatically by default, which
# let an initially-safe URL 302 straight to a private/loopback address
# AFTER is_safe_url() already passed on the original URL — the exact bypass
# this module now closes. `_NoRedirectHandler` disables that automatic
# following so `_open_with_redirect_guard` below can manually re-validate
# every hop's `Location` target before it is ever requested.
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_REDIRECT_GUARDED_OPENER = build_opener(_NoRedirectHandler)


def _open_with_redirect_guard(url: str, headers: dict[str, str], timeout: int):
    """Open `url`, manually following at most `MAX_REDIRECT_HOPS` redirects
    and re-validating EVERY hop (including the very first) via
    `is_safe_url()` before it is requested. Raises `UnsafeUrlError` naming
    the exact reason on an unsafe hop or too many redirects; otherwise
    propagates the underlying `HTTPError`/`URLError` unchanged so the
    existing exception handling in `download()` below is untouched."""
    current_url = url
    for hop in range(MAX_REDIRECT_HOPS + 1):
        safe, reason = is_safe_url(current_url)
        if not safe:
            raise UnsafeUrlError(reason)
        request = Request(current_url, headers=headers)
        try:
            return _REDIRECT_GUARDED_OPENER.open(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code not in _REDIRECT_STATUS_CODES:
                raise
            location = exc.headers.get("Location") if exc.headers else None
            if not location or hop == MAX_REDIRECT_HOPS:
                raise UnsafeUrlError(f"Too many redirects (> {MAX_REDIRECT_HOPS}) following {url}") from exc
            current_url = urljoin(current_url, location)
    raise UnsafeUrlError(f"Too many redirects (> {MAX_REDIRECT_HOPS}) following {url}")


def _target_root(url: str, metadata: dict | None) -> Path:
    metadata = metadata or {}
    guild = metadata.get("guild")
    if guild:
        return discord_root(str(guild))
    domain = normalize_domain(urlparse(url).hostname)
    return provider_root(Provider.DIRECT_FILE, domain)


def _target_file_name(url: str, metadata: dict | None, content_type: str | None = None) -> str:
    metadata = metadata or {}
    raw_name = str(metadata.get("filename") or file_name_from_url(url, "file"))
    suffix = Path(raw_name).suffix
    if suffix:
        return raw_name
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ".bin"
    return f"{raw_name}{guessed}"


def download(url: str, metadata: dict | None = None, timeout: int = 60) -> DownloadResult:
    domain = normalize_domain(urlparse(url).hostname)
    root = _target_root(url, metadata)
    try:
        # 待回答 #48: validates `url` itself AND every redirect hop (up to
        # MAX_REDIRECT_HOPS) before requesting it — see
        # _open_with_redirect_guard's docstring above. A rejection here
        # raises UnsafeUrlError (a ValueError subclass), caught by the
        # generic `except Exception` below like any other download failure.
        with contextlib.closing(
            _open_with_redirect_guard(url, {"User-Agent": "NS Media Hub/2.0"}, timeout)
        ) as response:
            target = unique_file_path(
                root,
                _target_file_name(url, metadata, response.headers.get("Content-Type")),
            )
            with target.open("wb") as handle:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    handle.write(chunk)
    except HTTPError as exc:
        return DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.DIRECT_FILE,
            domain=domain,
            download_path=str(root),
            error=f"HTTP {exc.code}: {exc.reason}",
        )
    except URLError as exc:
        return DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.DIRECT_FILE,
            domain=domain,
            download_path=str(root),
            error=str(exc.reason),
        )
    except Exception as exc:
        return DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.DIRECT_FILE,
            domain=domain,
            download_path=str(root),
            error=str(exc),
        )

    result_metadata = dict(metadata or {})
    result_metadata["filename"] = target.name
    return DownloadResult(
        status=JobStatus.SUCCESS,
        provider=Provider.DIRECT_FILE,
        domain=domain,
        download_path=str(target),
        metadata=result_metadata,
    )
