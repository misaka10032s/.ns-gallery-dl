from __future__ import annotations

import json
import subprocess
from pathlib import Path


def get_pixiv_refresh_token(tokens: dict) -> str | None:
    token = tokens.get("pixiv_refresh_token", "")
    if token:
        return token

    print("[Pixiv] refresh token missing, starting gallery-dl oauth flow...")
    try:
        subprocess.run(["gallery-dl", "oauth:pixiv"], check=True)
    except subprocess.CalledProcessError:
        print("[Pixiv] oauth flow failed.")
        return None

    config_path = Path.home() / ".config" / "gallery-dl" / "config.json"
    if not config_path.exists():
        print("[Pixiv] gallery-dl config.json not found after auth.")
        return None

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("[Pixiv] could not parse gallery-dl config.json")
        return None

    token = config.get("extractor", {}).get("pixiv", {}).get("refresh-token", "")
    if token:
        tokens["pixiv_refresh_token"] = token
    return token or None
