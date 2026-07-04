from __future__ import annotations

import json
import re
from collections.abc import Callable
from urllib.parse import urlparse

from app.config.settings import MULTI_PROVIDER_DOMAINS, YTDLP_DOMAINS, host_matches, normalize_domain
from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import DownloadResult, JobRequest
from app.providers.direct_file import provider as direct_file_provider
from app.providers.gallery_dl import provider as gallery_provider
from app.providers.ytdlp import provider as ytdlp_provider

SHORTCUT_PATTERNS: tuple[tuple[re.Pattern[str], Callable[[str], str]], ...]


def _build_shortcuts() -> tuple[tuple[re.Pattern[str], callable], ...]:
    return (
        (re.compile(r"^pw(\d+)$", re.IGNORECASE), lambda ident: f"https://www.pixiv.net/artworks/{ident}"),
        (re.compile(r"^pu(\d+)$", re.IGNORECASE), lambda ident: f"https://www.pixiv.net/users/{ident}"),
        (re.compile(r"^p(\d+)$", re.IGNORECASE), lambda ident: f"https://www.pixiv.net/artworks/{ident}"),
        (re.compile(r"^n(\d+)$", re.IGNORECASE), lambda ident: f"https://nhentai.net/g/{ident}/"),
        (re.compile(r"^w(\d+)$", re.IGNORECASE), lambda ident: f"https://www.wnacg.com/photos-index-aid-{ident}.html"),
    )


SHORTCUT_PATTERNS = _build_shortcuts()


def expand_url_shortcut(raw_value: str) -> str | None:
    value = (raw_value or "").strip().replace(" ", "")
    if not value:
        return None
    for pattern, builder in SHORTCUT_PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            return builder(match.group(1))
    return None


def normalize_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url:
        raise ValueError("Empty URL")
    if url.startswith("ytdlp://"):
        url = url[len("ytdlp://") :]
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def is_forced_ytdlp(url: str) -> bool:
    return url.strip().startswith("ytdlp://")


def provider_candidates(url: str, provider: Provider | None = None) -> list[Provider]:
    if provider:
        return [provider]
    if is_forced_ytdlp(url):
        return [Provider.YTDLP]
    host = normalize_domain(urlparse(normalize_url(url)).hostname)
    if host_matches(host, MULTI_PROVIDER_DOMAINS):
        return [Provider.GALLERY_DL, Provider.YTDLP]
    if host_matches(host, YTDLP_DOMAINS):
        return [Provider.YTDLP]
    return [Provider.GALLERY_DL]


def classify_provider(url: str) -> Provider:
    return provider_candidates(url)[0]


def _download_with_provider(provider: Provider, url: str, tokens: dict, metadata: dict | None = None) -> DownloadResult:
    if provider == Provider.YTDLP:
        return ytdlp_provider.download(url)
    if provider == Provider.DIRECT_FILE:
        return direct_file_provider.download(url, metadata=metadata)
    return gallery_provider.download(url, tokens=tokens, metadata=metadata)


def _with_attempt_metadata(
    result: DownloadResult,
    attempts: list[dict],
    forced_provider: Provider | None,
    original_meta: dict | None = None,
) -> DownloadResult:
    # Start from original request meta so keys like selected_urls survive in the
    # stored job record.  Result-level keys (e.g. downloaded/skipped) overwrite
    # originals; attempt tracking keys are then set unconditionally.
    metadata = dict(original_meta or {})
    metadata.update(result.metadata or {})
    metadata["attempted_providers"] = [attempt["provider"] for attempt in attempts]
    metadata["provider_mode"] = "forced" if forced_provider else "auto"
    metadata["selected_provider"] = result.provider.value
    if attempts:
        metadata["attempts"] = attempts
    result.metadata = metadata
    return result


def _tag(provider: Provider) -> str:
    return f"[{provider.value:<11}]"


def _counts_suffix(result: DownloadResult) -> str:
    meta = result.metadata or {}
    if "downloaded" not in meta and "skipped" not in meta:
        return ""
    return f"  (下載 {meta.get('downloaded', 0)} 張、略過 {meta.get('skipped', 0)} 張)"


def download_request(request: JobRequest, tokens: dict) -> DownloadResult:
    attempts: list[dict] = []
    result: DownloadResult | None = None
    providers = provider_candidates(request.url, request.provider)
    print(f"{_tag(providers[0])} 接收到網址: {request.url}")
    for provider in providers:
        print(f"{_tag(provider)} 正在下載: {request.url}")
        result = _download_with_provider(provider, request.url, tokens=tokens, metadata=request.metadata)
        attempts.append(
            {
                "provider": provider.value,
                "status": result.status.value,
                "error": result.error,
            }
        )
        # why: SKIPPED 代表此 provider 已有全部檔案，與 SUCCESS 同樣是終態，不再試下一個 provider
        if result.status in (JobStatus.SUCCESS, JobStatus.SKIPPED):
            if result.status == JobStatus.SUCCESS:
                print(f"{_tag(result.provider)} 下載成功: {request.url}  →  {result.download_path}{_counts_suffix(result)}")
            else:
                print(f"{_tag(result.provider)} 已跳過: {request.url}{_counts_suffix(result)}")
            return _with_attempt_metadata(result, attempts, request.provider, request.metadata)
    if result is None:
        result = DownloadResult(
            status=JobStatus.FAILED,
            provider=classify_provider(request.url),
            domain=normalize_domain(urlparse(normalize_url(request.url)).hostname),
            error="No provider candidates available",
        )
    err_suffix = f"  —  {result.error}" if result.error else ""
    print(f"{_tag(result.provider)} 下載失敗: {request.url}{err_suffix}")
    return _with_attempt_metadata(result, attempts, request.provider, request.metadata)


def history_payload(url: str, source: JobSource, result: DownloadResult) -> dict:
    return {
        "url": normalize_url(url),
        "result": result.status.value if isinstance(result.status, JobStatus) else str(result.status),
        "source": source.value,
        "provider": result.provider.value if isinstance(result.provider, Provider) else str(result.provider),
        "download_path": result.download_path,
        "meta": result.metadata,
    }


def recent_jobs_payload(rows: list[dict]) -> list[dict]:
    payload: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["meta"] = json.loads(item.get("meta_json", "{}"))
        except json.JSONDecodeError:
            item["meta"] = {}
        payload.append(item)
    return payload
