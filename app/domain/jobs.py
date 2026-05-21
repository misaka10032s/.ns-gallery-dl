from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import JobSource, JobStatus, Provider


@dataclass(slots=True)
class JobRequest:
    url: str
    provider: Provider | None = None
    source: JobSource = JobSource.API
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DownloadResult:
    status: JobStatus
    provider: Provider
    domain: str
    download_path: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QueueState:
    current: str | None
    pending: list[str]
    total: int
