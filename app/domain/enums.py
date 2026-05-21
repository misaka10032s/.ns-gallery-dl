from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    GALLERY_DL = "gallery-dl"
    YTDLP = "ytdlp"
    DIRECT_FILE = "direct-file"


class JobSource(StrEnum):
    API = "api"
    BOT = "discord"
    EXTENSION = "extension"
    MANUAL = "manual"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
