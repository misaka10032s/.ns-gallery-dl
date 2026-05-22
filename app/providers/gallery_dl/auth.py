from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.token_service import save_tokens


def _gallery_dl_config_path() -> Path:
    return Path.home() / ".config" / "gallery-dl" / "config.json"


def _read_gallery_dl_refresh_token() -> str:
    config_path = _gallery_dl_config_path()
    if not config_path.exists():
        return ""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("[Pixiv] could not parse gallery-dl config.json")
        return ""
    return config.get("extractor", {}).get("pixiv", {}).get("refresh-token", "")


def get_pixiv_refresh_token(tokens: dict) -> str | None:
    token = tokens.get("pixiv_refresh_token", "")
    if token:
        return token

    token = _read_gallery_dl_refresh_token()
    if token:
        tokens["pixiv_refresh_token"] = token
        save_tokens(tokens)
        return token

    print("[Pixiv] refresh token missing, starting gallery-dl oauth flow...")
    try:
        subprocess.run(["gallery-dl", "oauth:pixiv"], check=True)
    except subprocess.CalledProcessError:
        print("[Pixiv] oauth flow failed.")
        return None

    config_path = _gallery_dl_config_path()
    if not config_path.exists():
        print("[Pixiv] gallery-dl config.json not found after auth.")
        return None

    token = _read_gallery_dl_refresh_token()
    if token:
        tokens["pixiv_refresh_token"] = token
        save_tokens(tokens)
    return token or None
