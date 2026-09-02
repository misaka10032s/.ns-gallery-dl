from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from shutil import which
from urllib.parse import urlparse

from app.config.paths import ROOT_DIR
from app.config.settings import normalize_domain
from app.domain import auth_cooldown, auth_failure
from app.domain.enums import JobStatus, Provider
from app.domain.error_sanitizer import sanitize_error
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

    # Resolved BEFORE the cooldown check (fix-round-2 — previously this ran
    # after, so in_cooldown() had no cookie_path to self-heal against and
    # yt-dlp alone lacked the mtime self-heal gallery-dl already had — see
    # in_cooldown()'s docstring in app/domain/auth_cooldown.py).
    cookie_path = resolve_cookie_file(url, Provider.YTDLP.value)

    # Auth-failure cooldown (item 1) — same domain-scoped cooldown gallery-dl
    # checks (app/domain/auth_cooldown.py): youtube.com/youtu.be are
    # yt-dlp-only, and facebook.com/fb.watch/twitter.com/x.com are tried by
    # BOTH engines against the same cookie file, so this must be checked
    # here too, not just in app/providers/gallery_dl/provider.py. Passing
    # cookie_path lets in_cooldown() self-heal an OUT-OF-BAND jar rewrite —
    # the engines' own cookies-update/save_cookies() write-back, a manual
    # file replace, or a MULTI_PROVIDER_DOMAINS alias sibling — the same
    # protection gallery-dl's provider already had; a re-seed through
    # cookie_service.save_cookie()/delete_cookie() was ALREADY
    # engine-agnostic before this change (it clears the cooldown directly),
    # so this closes the narrower out-of-band gap, not the primary path.
    cooling_down, cooldown_until = auth_cooldown.in_cooldown(domain, cookie_path)
    if cooling_down:
        assert cooldown_until is not None  # in_cooldown() always pairs True with a timestamp
        return DownloadResult(
            status=JobStatus.FAILED,
            provider=Provider.YTDLP,
            domain=domain,
            download_path=str(root),
            error=auth_cooldown.cooldown_message(domain, cooldown_until),
            metadata={"auth_classification": auth_failure.AUTH, "auth_cooldown": True},
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
    if status == JobStatus.SUCCESS:
        return DownloadResult(status=status, provider=Provider.YTDLP, domain=domain, download_path=str(root))

    lines = [line.strip() for line in output_lines if line.strip()]
    raw_error = lines[-1] if lines else "yt-dlp failed"
    # item 2: classify + record on every failure (no retry loop exists here
    # to cut short — a single yt-dlp invocation is already "one attempt" —
    # but an AUTH classification still arms the cross-engine cooldown
    # (app/domain/auth_cooldown.py) so the NEXT job for this domain, via
    # either engine, doesn't immediately retry with the same rejected
    # cookie). The error text is routed through the sanitizer before it
    # reaches jobs.error / history_entries.meta.error.
    classification = auth_failure.classify(raw_error)
    if classification == auth_failure.AUTH:
        auth_cooldown.record_auth_failure(domain, raw_error)
    return DownloadResult(
        status=status,
        provider=Provider.YTDLP,
        domain=domain,
        download_path=str(root),
        error=sanitize_error(raw_error),
        metadata={"auth_classification": classification},
    )
