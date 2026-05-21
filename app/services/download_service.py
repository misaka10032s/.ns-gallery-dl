from __future__ import annotations

import json
from urllib.parse import urlparse

from app.config.settings import GALLERY_DL_DOMAINS, YTDLP_DOMAINS, host_matches, normalize_domain
from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import DownloadResult, JobRequest
from app.providers.gallery_dl import provider as gallery_provider
from app.providers.ytdlp import provider as ytdlp_provider


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


def classify_provider(url: str) -> Provider:
    host = normalize_domain(urlparse(normalize_url(url)).hostname)
    if host_matches(host, YTDLP_DOMAINS):
        return Provider.YTDLP
    return Provider.GALLERY_DL


def download_request(request: JobRequest, tokens: dict) -> DownloadResult:
    provider = request.provider or classify_provider(request.url)
    if provider == Provider.YTDLP:
        return ytdlp_provider.download(request.url)
    return gallery_provider.download(request.url, tokens=tokens)


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
