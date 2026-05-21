from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"
DATA_DIR = ROOT_DIR / "data"
DOWNLOAD_DIR = ROOT_DIR / "download"
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
