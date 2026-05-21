from __future__ import annotations

import json

from app.config.paths import DATA_DIR, TOKENS_FILE


def load_tokens() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if TOKENS_FILE.exists():
        try:
            return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_tokens(tokens: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
