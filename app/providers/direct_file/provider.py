from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.config.settings import normalize_domain
from app.domain.enums import JobStatus, Provider
from app.domain.jobs import DownloadResult
from app.services.path_service import discord_root, file_name_from_url, provider_root, unique_file_path


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
    request = Request(url, headers={"User-Agent": "NS Media Hub/2.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
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
