from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from shutil import which
from urllib.parse import urlparse

from app.config.paths import ROOT_DIR
from app.config.settings import normalize_domain
from app.domain.enums import JobStatus, Provider
from app.domain.jobs import DownloadResult
from app.providers.cookies.resolver import resolve_cookie_file
from app.services.path_service import provider_root, sanitize_component


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


def _user_print_command(executable: str, url: str, cookie_path: str | None) -> list[str]:
    command = [
        executable,
        "--print",
        "%(uploader_id,uploader,channel_id,channel,creator,playlist_uploader|)s",
        "--no-playlist",
        "--skip-download",
        "--no-warnings",
    ]
    if cookie_path:
        command.extend(["--cookies", cookie_path])
    command.append(url)
    return command


def _probe_user_root(executable: str, url: str, root: Path, cookie_path: str | None) -> Path:
    try:
        result = subprocess.run(
            _user_print_command(executable, url, cookie_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return root
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return root
    user = sanitize_component(lines[-1], "")
    return root / user if user else root


def _resolve_executable(name: str) -> str | None:
    # yt-dlp is pip-managed (see app/config/downloaders.py) and installed into the
    # venv, so it's on PATH like any other console script — prefer that. A
    # repo-root override (e.g. a manually dropped yt-dlp.exe) still wins if present,
    # for local troubleshooting. The old ".ns-yt-dlp" sibling-repo fallback is
    # removed: that path pointed at a repo that no longer exists.
    local = ROOT_DIR / f"{name}.exe"
    if local.exists():
        return str(local)

    return which(name)


def download(url: str) -> DownloadResult:
    url = _normalize_url(url)
    domain = normalize_domain(urlparse(url).hostname)
    executable = _resolve_executable("yt-dlp")
    root = provider_root(Provider.YTDLP, domain)
    if not executable:
        return DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.YTDLP,
            domain=domain,
            download_path=str(root),
            error="yt-dlp executable not found (repo-root override or PATH/venv Scripts) — check `pip install yt-dlp` ran",
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
    root = _probe_user_root(executable, url, root, cookie_path)
    command[command.index("--output") + 1] = _output_template(root)
    if cookie_path:
        command.extend(["--cookies", cookie_path])
    ffmpeg = _resolve_executable("ffmpeg")
    if ffmpeg:
        command.extend(["--ffmpeg-location", str(Path(ffmpeg).parent)])
    command.append(url)

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output_lines: list[str] = []
    for line in iter(process.stdout.readline, ""):
        output_lines.append(line.rstrip())
        sys.stdout.write(line)
    process.wait()
    status = JobStatus.SUCCESS if process.returncode == 0 else JobStatus.FAILED
    error = ""
    if status == JobStatus.FAILED:
        lines = [line.strip() for line in output_lines if line.strip()]
        error = lines[-1] if lines else "yt-dlp failed"
    return DownloadResult(status=status, provider=Provider.YTDLP, domain=domain, download_path=str(root), error=error)
