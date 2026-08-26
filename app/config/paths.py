from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"
# NS_MEDIA_HUB_DATA_DIR / NS_MEDIA_HUB_DOWNLOAD_DIR: optional overrides so a
# verification/staging run can point at a private data dir (never the live
# data/app.db a running instance has open) while still reading the real,
# read-only download/ tree. Unset in normal operation — behavior is unchanged.
DATA_DIR = Path(os.environ.get("NS_MEDIA_HUB_DATA_DIR") or (ROOT_DIR / "data"))
DOWNLOAD_DIR = Path(os.environ.get("NS_MEDIA_HUB_DOWNLOAD_DIR") or (ROOT_DIR / "download"))
UI_DIR = APP_DIR / "ui"

DB_FILE = DATA_DIR / "app.db"
TOKENS_FILE = DATA_DIR / "tokens.json"
LEGACY_HISTORY_FILE = DATA_DIR / "history.json"

COOKIE_DIR = ROOT_DIR / "cookies"
LEGACY_COOKIE_DIRS = (
    DATA_DIR / "cookies",
    ROOT_DIR / "module" / "cookies",
)

ENV_FILE = ROOT_DIR / ".env"
