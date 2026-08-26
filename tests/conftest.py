"""
測試共用 fixtures。
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch


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
    """提供臨時 SQLite 檔案，隔離 schema/repo 測試，不碰真正的 data/app.db。"""
    from app.storage import db as db_module

    db_file = tmp_path / "test_app.db"
    with patch.object(db_module, "DATA_DIR", tmp_path), \
         patch.object(db_module, "DB_FILE", db_file):
        db_module._READY = False
        db_module.init_db()
        yield db_file
        db_module._READY = False
