from __future__ import annotations

import os
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from app.config.settings import normalize_domain
from app.domain.enums import JobStatus, Provider
from app.domain.jobs import DownloadResult
from app.providers.cookies.resolver import resolve_cookie_file
from app.providers.sites.bahamut import download_bahamut
from app.providers.sites.nhentai import download_nhentai
from app.providers.sites.pixiv import get_pixiv_refresh_token
from app.providers.sites.wnacg import download_wnacg
from app.services.path_service import pixiv_root, provider_root, sanitize_component


def _cookies_args(cookie_path: str | None) -> list[str]:
    return ["-C", cookie_path] if cookie_path else []


def _cookie_candidates(url: str, domain: str) -> list[str | None]:
    cookie_path = resolve_cookie_file(url, Provider.GALLERY_DL.value)
    if not cookie_path:
        return [None]
    if domain in {"x.com", "twitter.com"}:
        return [None, cookie_path]
    if domain in {"facebook.com", "fb.watch"}:
        return [cookie_path, None]
    return [cookie_path]


def _simulate(url: str, env: dict[str, str], cookie_path: str | None = None) -> tuple[int, int]:
    command = ["gallery-dl", "--simulate", url, *_cookies_args(cookie_path)]
    result = subprocess.run(command, capture_output=True, text=True, env=env, encoding="utf-8")
    count = len(
        [
            line
            for line in (item.strip() for item in result.stdout.splitlines())
            if line and not line.startswith("[") and not line.upper().startswith("ERROR:")
        ]
    )
    return result.returncode, count


def _gallery_download(url: str, env: dict[str, str], download_root: Path, cookie_path: str | None = None) -> str:
    command = ["gallery-dl", url, "-D", str(download_root), *_cookies_args(cookie_path)]
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


def _probe_pixiv_user_root(url: str, root: Path) -> Path:
    match = re.search(r"/artworks/(\d+)", url)
    if not match:
        return root
    artwork_id = match.group(1)
    request = Request(
        f"https://www.pixiv.net/ajax/illust/{artwork_id}",
        headers={"User-Agent": "NS Media Hub/2.0"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return root
    user = sanitize_component((payload.get("body") or {}).get("userName"), "")
    return root / user if user else root


def _probe_user_root(url: str, env: dict[str, str], domain: str, root: Path, cookie_candidates: list[str | None]) -> Path:
    if domain == "pixiv.net":
        return _probe_pixiv_user_root(url, root)
    if domain not in {"facebook.com", "fb.watch", "x.com", "twitter.com"}:
        return root
    for cookie_path in cookie_candidates:
        command = ["gallery-dl", "-j", url, *_cookies_args(cookie_path)]
        result = subprocess.run(command, capture_output=True, text=True, env=env, encoding="utf-8", errors="replace", check=False)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        if not payload:
            continue
        metadata = payload[0][1] if isinstance(payload[0], list) and len(payload[0]) > 1 else {}
        user = (
            metadata.get("user", {}).get("name")
            or metadata.get("author", {}).get("name")
            or metadata.get("user", {}).get("nick")
            or metadata.get("author", {}).get("nick")
            or metadata.get("owner", {}).get("name")
            or metadata.get("page", {}).get("name")
        )
        user = sanitize_component(user, "")
        if user:
            return root / user
    return root


def download(url: str, tokens: dict, max_retries: int = 5, retry_delay: int = 5) -> DownloadResult:
    domain = normalize_domain(urlparse(url).hostname)
    if domain in {"nhentai.net"}:
        root = provider_root(Provider.GALLERY_DL, domain)
        status = download_nhentai(url, root)
        return DownloadResult(status=JobStatus(status), provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))

    if domain == "wnacg.com":
        root = provider_root(Provider.GALLERY_DL, domain)
        status = download_wnacg(url, root)
        return DownloadResult(status=JobStatus(status), provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))

    if domain in {"forum.gamer.com.tw", "gamer.com.tw"}:
        root = provider_root(Provider.GALLERY_DL, domain)
        status = download_bahamut(url, root)
        return DownloadResult(status=JobStatus(status), provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))

    env = os.environ.copy()
    root = provider_root(Provider.GALLERY_DL, domain)
    if domain == "pixiv.net":
        token = get_pixiv_refresh_token(tokens)
        if token:
            env["GALLERYDL_PIXIV_REFRESH_TOKEN"] = token

    cookie_candidates = _cookie_candidates(url, domain)
    root = _probe_user_root(url, env, domain, root, cookie_candidates)
    if domain == "pixiv.net" and root == provider_root(Provider.GALLERY_DL, domain) and tokens.get("pixiv_author_hint"):
        root = pixiv_root(domain, tokens.get("pixiv_author_hint"))
    saw_zero_results = False
    for attempt in range(1, max_retries + 1):
        attempt_failed = False
        for cookie_path in cookie_candidates:
            code, total = _simulate(url, env, cookie_path)
            if code != 0:
                attempt_failed = True
                continue
            if total == 0:
                saw_zero_results = True
                continue
            saw_zero_results = False
            status = _gallery_download(url, env, root, cookie_path)
            if status == "success":
                return DownloadResult(status=JobStatus.SUCCESS, provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))
            attempt_failed = True
        if domain == "pixiv.net" and attempt_failed:
            token = get_pixiv_refresh_token(tokens)
            if token:
                env["GALLERYDL_PIXIV_REFRESH_TOKEN"] = token
                continue
        if attempt < max_retries:
            time.sleep(retry_delay)

    if saw_zero_results:
        return DownloadResult(status=JobStatus.SKIPPED, provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))
    return DownloadResult(status=JobStatus.FAILED, provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))
