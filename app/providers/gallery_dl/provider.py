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
from app.domain import auth_cooldown, auth_failure
from app.domain.enums import JobStatus, Provider
from app.domain.error_sanitizer import sanitize_error
from app.domain.jobs import DownloadResult
from app.providers.cookies.resolver import resolve_cookie_file
from app.providers.sites import wnacg_health
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


def _last_error_line(text: str) -> str:
    """
    gallery-dl logs via Python `logging` with LOG_FORMAT = "[{name}][{levelname}]
    {message}" (gallery_dl/output.py) to STDERR by default — e.g.
    `[gallery-dl][error] Unsupported URL '...'` or
    `[danbooru][error] HttpError: '404 Not Found' for '...'` (verified live against
    the installed gallery-dl CLI). Return the last such "[...][error]" line, or —
    if none matched — the last non-empty line as a fallback so *some* diagnostic
    text always reaches the job's error field instead of being silently dropped.
    """
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    error_lines = [line for line in lines if "][error]" in line.lower()]
    if error_lines:
        return error_lines[-1]
    return lines[-1] if lines else ""


def _simulate(url: str, env: dict[str, str], cookie_path: str | None = None) -> tuple[int, int, str]:
    command = ["gallery-dl", "--simulate", url, *_cookies_args(cookie_path)]
    result = subprocess.run(command, capture_output=True, text=True, env=env, encoding="utf-8", errors="replace")
    count = len(
        [
            line
            for line in (item.strip() for item in result.stdout.splitlines())
            if line and not line.startswith("[") and not line.upper().startswith("ERROR:")
        ]
    )
    # gallery-dl's own errors land on stderr (see _last_error_line); stdout is
    # checked too as a fallback in case something logs there instead. Only
    # extract on a non-zero exit — on success, stdout is legitimate path output,
    # not diagnostic text, and must never be mistaken for an "error".
    error = ""
    if result.returncode != 0:
        error = _last_error_line(result.stderr) or _last_error_line(result.stdout)
    return result.returncode, count, error


def _gallery_download(url: str, env: dict[str, str], download_root: Path, cookie_path: str | None = None) -> tuple[str, int, int, str]:
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
    downloaded = 0
    skipped = 0
    output_lines: list[str] = []
    for line in iter(process.stdout.readline, ""):
        text = line.rstrip("\r\n")
        output_lines.append(text)
        # why: gallery-dl 對已存在檔案輸出 '# <path>'，新檔輸出純路徑、log 行以 '[' 開頭
        if text.startswith("# "):
            skipped += 1
            sys.stdout.write(f"[略過] {text[2:]}\n")
            continue
        if text and not text.startswith("[") and not text.upper().startswith("ERROR"):
            downloaded += 1
        sys.stdout.write(line)
    process.wait()
    if downloaded or skipped:
        sys.stdout.write(f"[gallery-dl ] 本次：下載 {downloaded} 張、略過 {skipped} 張\n")
    status = "success" if process.returncode == 0 else "failed"
    # stderr was merged into stdout above (stderr=subprocess.STDOUT), so the
    # "[name][error] ..." line (if any) is already among output_lines.
    error = _last_error_line("\n".join(output_lines)) if status == "failed" else ""
    return status, downloaded, skipped, error


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


def download(url: str, tokens: dict, max_retries: int = 5, retry_delay: int = 5, metadata: dict | None = None) -> DownloadResult:
    domain = normalize_domain(urlparse(url).hostname)
    if domain in {"nhentai.net"}:
        root = provider_root(Provider.GALLERY_DL, domain)
        status = download_nhentai(url, root)
        return DownloadResult(status=JobStatus(status), provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))

    if domain == "wnacg.com":
        root = provider_root(Provider.GALLERY_DL, domain)
        status, error = download_wnacg(url, root)
        result = DownloadResult(status=JobStatus(status), provider=Provider.GALLERY_DL, domain=domain, download_path=str(root), error=error)
        wnacg_health.record_result(success=result.status in (JobStatus.SUCCESS, JobStatus.SKIPPED))
        return result

    if domain in {"forum.gamer.com.tw", "gamer.com.tw"}:
        root = provider_root(Provider.GALLERY_DL, domain)
        selected_urls = (metadata or {}).get("selected_urls") or None
        status = download_bahamut(url, root, selected_urls=selected_urls)
        return DownloadResult(status=JobStatus(status), provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))

    env = os.environ.copy()
    root = provider_root(Provider.GALLERY_DL, domain)
    if domain == "pixiv.net":
        # why: still bootstraps the OAuth flow on first use and caches the
        # resulting token into data/tokens.json (consumed by GET
        # /api/auth/pixiv's status check) — but no longer writes it into
        # `env`. `GALLERYDL_PIXIV_REFRESH_TOKEN` is a no-op: a grep across the
        # installed gallery-dl package (1.32.1) finds no code anywhere that
        # reads this name. gallery-dl authenticates pixiv purely from its OWN
        # config file (~/.config/gallery-dl/config.json ->
        # extractor.pixiv.refresh-token, written by `gallery-dl oauth:pixiv`
        # itself — see app/providers/gallery_dl/auth.py), which every
        # gallery-dl subprocess call below already reads on its own, with no
        # help needed from this process's environment.
        # docs/blueprint/entries/BP-PROV-PIXIV-1.md currently documents the
        # env var as functional — needs correcting (see this phase's
        # implement.md; blueprint edits are the orchestrator's, not this
        # dispatch's, to make).
        get_pixiv_refresh_token(tokens)

    cookie_candidates = _cookie_candidates(url, domain)

    # Auth-failure cooldown (item 1): checked BEFORE any credentialed request
    # is made for this domain (gallery-dl and yt-dlp share one cooldown per
    # domain — see app/domain/auth_cooldown.py). A prior job already proved
    # this domain's cookie/token is rejected; don't hammer it again with more
    # credential-bearing requests until the cooldown elapses.
    # Pass the resolved cookie file (if any) so in_cooldown() can self-heal a
    # stale cooldown that a jar rewrite (this app's own save_cookie(), or a
    # MULTI_PROVIDER_DOMAINS sibling domain sharing the same physical file)
    # already resolved — see app/domain/auth_cooldown.py's `_cookie_changed_since`.
    current_cookie_path = next((c for c in cookie_candidates if c), None)
    cooling_down, cooldown_until = auth_cooldown.in_cooldown(domain, current_cookie_path)
    if cooling_down:
        assert cooldown_until is not None  # in_cooldown() always pairs True with a timestamp
        return DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.GALLERY_DL,
            domain=domain,
            download_path=str(root),
            error=auth_cooldown.cooldown_message(domain, cooldown_until),
            metadata={"auth_classification": auth_failure.AUTH, "auth_cooldown": True},
        )

    root = _probe_user_root(url, env, domain, root, cookie_candidates)
    if domain == "pixiv.net" and root == provider_root(Provider.GALLERY_DL, domain) and tokens.get("pixiv_author_hint"):
        root = pixiv_root(domain, tokens.get("pixiv_author_hint"))
    saw_zero_results = False
    last_error = ""
    for attempt in range(1, max_retries + 1):
        attempt_failed = False
        for cookie_path in cookie_candidates:
            code, total, sim_error = _simulate(url, env, cookie_path)
            if code != 0:
                attempt_failed = True
                if sim_error:
                    last_error = sim_error
                # why (item 1): an AUTH-classified failure stops here — ONE
                # attempt, not the usual up-to-`max_retries` x
                # len(cookie_candidates) (previously up to 5*2=10
                # credential-bearing requests per job). A network error,
                # timeout, or non-auth HTTP failure keeps the EXISTING retry
                # behaviour untouched (falls through to `continue` below,
                # same as before this change).
                if auth_failure.classify(sim_error) == auth_failure.AUTH:
                    auth_cooldown.record_auth_failure(domain, sim_error)
                    return DownloadResult(
                        status=JobStatus.FAILED,
                        provider=Provider.GALLERY_DL,
                        domain=domain,
                        download_path=str(root),
                        error=sanitize_error(sim_error),
                        metadata={"auth_classification": auth_failure.AUTH},
                    )
                continue
            if total == 0:
                saw_zero_results = True
                continue
            saw_zero_results = False
            status, downloaded, skipped, dl_error = _gallery_download(url, env, root, cookie_path)
            if status == "success":
                # why: 整個 user 連結全部已存在 → 視為略過而非下載成功
                job_status = JobStatus.SKIPPED if downloaded == 0 and skipped > 0 else JobStatus.SUCCESS
                return DownloadResult(
                    status=job_status,
                    provider=Provider.GALLERY_DL,
                    domain=domain,
                    download_path=str(root),
                    metadata={"downloaded": downloaded, "skipped": skipped},
                )
            attempt_failed = True
            if dl_error:
                last_error = dl_error
            # Same one-attempt-and-stop rule as the simulate branch above.
            if auth_failure.classify(dl_error) == auth_failure.AUTH:
                auth_cooldown.record_auth_failure(domain, dl_error)
                return DownloadResult(
                    status=JobStatus.FAILED,
                    provider=Provider.GALLERY_DL,
                    domain=domain,
                    download_path=str(root),
                    error=sanitize_error(dl_error),
                    metadata={"auth_classification": auth_failure.AUTH},
                )
        if domain == "pixiv.net" and attempt_failed:
            token = get_pixiv_refresh_token(tokens)
            if token:
                continue
        if attempt < max_retries:
            time.sleep(retry_delay)

    if saw_zero_results:
        return DownloadResult(status=JobStatus.SKIPPED, provider=Provider.GALLERY_DL, domain=domain, download_path=str(root))
    # item 2: classify + record on EVERY failed result reaching this generic
    # path (not just the early-stop AUTH case above) so phase 1b has a
    # signal to render even for a not-auth / indeterminate failure. The error
    # text is routed through the sanitizer here for the same reason the
    # early-stop branches above do it — this is now a "classified message"
    # about to reach jobs.error / history_entries.meta.error.
    return DownloadResult(
        status=JobStatus.FAILED,
        provider=Provider.GALLERY_DL,
        domain=domain,
        download_path=str(root),
        error=sanitize_error(last_error) if last_error else "gallery-dl failed",
        metadata={"auth_classification": auth_failure.classify(last_error)},
    )
