from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from app.config.settings import normalize_domain
from app.domain.enums import JobStatus, Provider
from app.domain.jobs import DownloadResult
from app.providers.cookies.resolver import resolve_cookie_file
from app.providers.sites.nhentai import download_nhentai
from app.providers.sites.pixiv import get_pixiv_refresh_token
from app.providers.sites.wnacg import download_wnacg
from app.services.path_service import pixiv_root, provider_root


def _cookies_args(url: str) -> list[str]:
    cookie_path = resolve_cookie_file(url, Provider.GALLERY_DL.value)
    return ["-C", cookie_path] if cookie_path else []


def _simulate(url: str, env: dict[str, str]) -> tuple[int, int]:
    command = ["gallery-dl", "--simulate", url, *_cookies_args(url)]
    result = subprocess.run(command, capture_output=True, text=True, env=env, encoding="utf-8")
    count = len([line for line in result.stdout.splitlines() if line.startswith("# ")])
    return result.returncode, count


def _gallery_download(url: str, env: dict[str, str], download_root: Path) -> str:
    command = ["gallery-dl", url, "-d", str(download_root), *_cookies_args(url)]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )
    for line in iter(process.stdout.readline, ""):
        sys.stdout.write(line)
    process.wait()
    return "success" if process.returncode == 0 else "failed"


def download(url: str, tokens: dict, max_retries: int = 5, retry_delay: int = 5) -> DownloadResult:
    domain = normalize_domain(urlparse(url).hostname)
    if domain == "nhentai.net":
        root = provider_root(Provider.GALLERY_DL, domain)
        status = download_nhentai(url, root)
        return DownloadResult(status=JobStatus(status), provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))

    if domain == "wnacg.com":
        root = provider_root(Provider.GALLERY_DL, domain)
        status = download_wnacg(url, root)
        return DownloadResult(status=JobStatus(status), provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))

    env = os.environ.copy()
    if domain == "pixiv.net":
        token = get_pixiv_refresh_token(tokens)
        if token:
            env["GALLERYDL_PIXIV_REFRESH_TOKEN"] = token
        root = pixiv_root(domain, tokens.get("pixiv_author_hint"))
    else:
        root = provider_root(Provider.GALLERY_DL, domain)

    for attempt in range(1, max_retries + 1):
        code, total = _simulate(url, env)
        if code != 0:
            if domain == "pixiv.net":
                token = get_pixiv_refresh_token(tokens)
                if token:
                    env["GALLERYDL_PIXIV_REFRESH_TOKEN"] = token
                    continue
            if attempt < max_retries:
                time.sleep(retry_delay)
                continue
            return DownloadResult(status=JobStatus.FAILED, provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))
        if total == 0:
            return DownloadResult(status=JobStatus.SKIPPED, provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))

        status = _gallery_download(url, env, root)
        if status == "success":
            return DownloadResult(status=JobStatus.SUCCESS, provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))
        if attempt < max_retries:
            time.sleep(retry_delay)

    return DownloadResult(status=JobStatus.FAILED, provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))
