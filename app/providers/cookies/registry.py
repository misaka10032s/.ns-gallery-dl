from __future__ import annotations

import shutil
from pathlib import Path

from app.config.paths import COOKIE_DIR, LEGACY_COOKIE_DIRS
from app.storage.db import init_db
from app.storage.repositories import cookies_repo

from .metadata import infer_cookie_metadata


def cookie_search_dirs() -> list[Path]:
    return [COOKIE_DIR]


def migrate_legacy_cookie_files() -> list[Path]:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for legacy_dir in LEGACY_COOKIE_DIRS:
        if not legacy_dir.exists():
            continue
        for cookie_file in sorted(legacy_dir.glob("*.txt")):
            target = COOKIE_DIR / cookie_file.name
            if target.exists():
                continue
            shutil.move(str(cookie_file), str(target))
            moved.append(target)
    return moved


def scan_cookie_files() -> list[dict]:
    init_db()
    migrate_legacy_cookie_files()
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    cookies_repo.clear_scanned_entries()
    found: list[dict] = []
    for base in cookie_search_dirs():
        if not base.exists():
            continue
        for cookie_file in sorted(base.glob("*.txt")):
            domain, provider = infer_cookie_metadata(cookie_file)
            if not domain:
                continue
            cookies_repo.upsert_cookie(
                domain=domain,
                provider=provider,
                file_name=cookie_file.name,
                file_path=str(cookie_file.resolve()),
                source="scan",
            )
            found.append(
                {
                    "domain": domain,
                    "provider": provider,
                    "file_name": cookie_file.name,
                    "file_path": str(cookie_file.resolve()),
                }
            )
    return found
