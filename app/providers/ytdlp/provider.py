from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which
from urllib.parse import urlparse

from app.config.paths import ROOT_DIR
from app.config.settings import normalize_domain
from app.domain.enums import JobStatus, Provider
from app.domain.jobs import DownloadResult
from app.providers.cookies.resolver import resolve_cookie_file
from app.services.path_service import provider_root


def _normalize_url(raw_url: str) -> str:
    url = raw_url.strip()
    if url.startswith("ytdlp://"):
        url = url[len("ytdlp://") :]
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
    return url


def _format_for_domain(domain: str) -> str:
    if domain in {"facebook.com", "fb.watch"}:
        return "best"
    return "bestvideo*+bestaudio/best"


def _output_template(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "[%(id)s] %(title).120s.%(ext)s")


def _resolve_executable(name: str) -> str | None:
    local = ROOT_DIR / f"{name}.exe"
    if local.exists():
        return str(local)

    sibling = ROOT_DIR.parent / ".ns-yt-dlp" / f"{name}.exe"
    if sibling.exists():
        return str(sibling)

    return which(name)


def download(url: str) -> DownloadResult:
    url = _normalize_url(url)
    domain = normalize_domain(urlparse(url).hostname)
    root = provider_root(Provider.YTDLP, domain)
    executable = _resolve_executable("yt-dlp")
    if not executable:
        return DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.YTDLP,
            domain=domain,
            download_path=str(root),
            error="yt-dlp executable not found in repo, sibling .ns-yt-dlp repo, or PATH",
        )

    command = [
        executable,
        "--windows-filenames",
        "--trim-filenames",
        "120",
        "--no-playlist",
        "--format",
        _format_for_domain(domain),
        "--output",
        _output_template(root),
    ]
    cookie_path = resolve_cookie_file(url, Provider.YTDLP.value)
    if cookie_path:
        command.extend(["--cookies", cookie_path])
    ffmpeg = _resolve_executable("ffmpeg")
    if ffmpeg:
        command.extend(["--ffmpeg-location", str(Path(ffmpeg).parent)])
    command.append(url)

    result = subprocess.run(command, check=False)
    status = JobStatus.SUCCESS if result.returncode == 0 else JobStatus.FAILED
    return DownloadResult(status=status, provider=Provider.YTDLP, domain=domain, download_path=str(root))
