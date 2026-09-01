"""
測試共用 fixtures。
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

from app.config import paths as _paths_module

# Captured ONCE at collection time, before any fixture ever patches anything —
# the repo's REAL, live production paths. assert_db_paths_isolated() compares
# against these fixed values, never against app.storage.db's own (patchable)
# module globals, so the check stays meaningful even while a test has them
# patched.
_REAL_DATA_DIR = _paths_module.DATA_DIR
_REAL_DB_FILE = _paths_module.DB_FILE
_REAL_LEGACY_HISTORY_FILE = _paths_module.LEGACY_HISTORY_FILE


def assert_db_paths_isolated(db_module) -> None:
    """Fail loudly if any of db_module's currently-active DB-related path
    constants resolve to this repo's real, live production files.

    2026-09-01 incident: tmp_db patched DATA_DIR/DB_FILE but NOT
    LEGACY_HISTORY_FILE. app/storage/db.py:11 binds its own module-level copy
    of LEGACY_HISTORY_FILE at db.py's own import time (`from
    app.config.paths import ... LEGACY_HISTORY_FILE`) — a separate name from
    the two patched ones, never re-derived from the patched DATA_DIR.
    init_db() -> migrate_legacy_history() (app/storage/db.py:301-306) reads
    LEGACY_HISTORY_FILE unconditionally whenever history_entries is empty —
    true for every "fresh" tmp_db-backed test — so every one of them silently
    reseeded its supposedly isolated temp db from the real data/history.json
    (4669 grouped / ~4642 row entries) whenever that file happened to exist.
    On a fresh worktree data/history.json is gitignored and absent, so the
    migration is a no-op and tests pass vacuously; on the main tree, where
    the real file exists, the two new test files (test_queue_service.py,
    test_history_service.py) failed against real user download history.
    `data/app.db` itself was never touched — DATA_DIR/DB_FILE patching was
    always correct for that file; the leak was read-only and specific to
    LEGACY_HISTORY_FILE. This guard makes reintroducing that class of leak
    (or ever pointing DB_FILE itself at the real app.db) structurally
    impossible: any DB-related path that resolves back to a real file raises
    immediately instead of quietly letting production data into test state.
    """
    checks = {
        "DATA_DIR": (getattr(db_module, "DATA_DIR", None), _REAL_DATA_DIR),
        "DB_FILE": (getattr(db_module, "DB_FILE", None), _REAL_DB_FILE),
        "LEGACY_HISTORY_FILE": (getattr(db_module, "LEGACY_HISTORY_FILE", None), _REAL_LEGACY_HISTORY_FILE),
    }
    for name, (current, real) in checks.items():
        if current is None:
            continue
        if Path(current).resolve() == Path(real).resolve():
            raise RuntimeError(
                f"tmp_db isolation guard: db_module.{name} resolves to the REAL "
                f"production path {real} — refusing to let a test run against "
                "live data. Patch it to a tmp_path-based location before use."
            )


@pytest.fixture
def tmp_download_dir(tmp_path: Path):
    """提供臨時的下載目錄，隔離 gallery_service 的檔案系統操作。"""
    d = tmp_path / "download"
    d.mkdir()
    with patch("app.services.gallery_service.DOWNLOAD_DIR", d):
        yield d


@pytest.fixture
def tmp_cookie_dir(tmp_path: Path):
    """提供臨時的 cookie 目錄，隔離 cookie_service 的檔案系統操作。"""
    c = tmp_path / "cookies"
    c.mkdir()
    with patch("app.services.cookie_service.COOKIE_DIR", c), \
         patch("app.services.path_service.DOWNLOAD_DIR", tmp_path / "download"):
        yield c


@pytest.fixture
def tmp_doujin_download_dir(tmp_path: Path):
    """提供臨時的下載目錄，隔離 doujin_service 的檔案系統操作。"""
    d = tmp_path / "download"
    d.mkdir()
    with patch("app.services.doujin_service.DOWNLOAD_DIR", d):
        yield d


@pytest.fixture
def tmp_db(tmp_path: Path):
    """提供臨時 SQLite 檔案，隔離 schema/repo 測試，不碰真正的 data/app.db /
    data/history.json。三個路徑常數都要 patch —— LEGACY_HISTORY_FILE 是
    app.storage.db 在自己 import 時從 app.config.paths 另外綁定的一份，不會
    因為只 patch DATA_DIR 而跟著變（2026-09-01 事故：init_db() 的 legacy 遷
    移步驟因此讀了真正的 data/history.json，灌進看似「乾淨」的暫存 db）。
    assert_db_paths_isolated() 是結構性防線：往後任何一個路徑常數又意外指回
    真正的正式檔案，這裡會立刻大聲失敗，而不是安靜讀到正式資料。"""
    from app.storage import db as db_module

    db_file = tmp_path / "test_app.db"
    legacy_history_file = tmp_path / "unused_legacy_history.json"  # deliberately absent
    with patch.object(db_module, "DATA_DIR", tmp_path), \
         patch.object(db_module, "DB_FILE", db_file), \
         patch.object(db_module, "LEGACY_HISTORY_FILE", legacy_history_file):
        assert_db_paths_isolated(db_module)
        db_module._READY = False
        db_module.init_db()
        yield db_file
        db_module._READY = False
