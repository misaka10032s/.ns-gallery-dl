"""
tests/test_gallery_service.py

覆蓋 gallery_service 的安全關鍵路徑：
- resolve_file：path traversal 防護（is_relative_to 邊界）
- list_items / list_files：正常功能
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import gallery_service


# ──────────────────────────────────────────────────────────
# resolve_file — path traversal 防護
# ──────────────────────────────────────────────────────────


class TestResolveFile:
    """resolve_file 必須把所有路徑限制在 DOWNLOAD_DIR 內。"""

    def test_valid_file_returns_path(self, tmp_download_dir: Path):
        target = tmp_download_dir / "img.jpg"
        target.write_bytes(b"fake image")
        result = gallery_service.resolve_file("img.jpg")
        assert result == target.resolve()

    def test_nonexistent_file_returns_none(self, tmp_download_dir: Path):
        result = gallery_service.resolve_file("nonexistent.jpg")
        assert result is None

    def test_directory_returns_none(self, tmp_download_dir: Path):
        (tmp_download_dir / "subdir").mkdir()
        result = gallery_service.resolve_file("subdir")
        assert result is None

    def test_path_traversal_dotdot_returns_none(self, tmp_download_dir: Path):
        """../../etc/passwd 不能逃出 DOWNLOAD_DIR。"""
        result = gallery_service.resolve_file("../../etc/passwd")
        assert result is None

    def test_path_traversal_encoded_returns_none(self, tmp_download_dir: Path):
        """多層 .. 組合仍不能逃出目錄。"""
        result = gallery_service.resolve_file("subdir/../../../etc/shadow")
        assert result is None

    def test_absolute_path_traversal_returns_none(self, tmp_download_dir: Path):
        """傳入絕對路徑也必須被擋住（除非它本來就在 DOWNLOAD_DIR 內）。"""
        result = gallery_service.resolve_file("/etc/passwd")
        assert result is None

    def test_nested_valid_file_returns_path(self, tmp_download_dir: Path):
        sub = tmp_download_dir / "pixiv" / "artist"
        sub.mkdir(parents=True)
        f = sub / "image.png"
        f.write_bytes(b"data")
        result = gallery_service.resolve_file("pixiv/artist/image.png")
        assert result == f.resolve()


# ──────────────────────────────────────────────────────────
# list_categories / list_items / list_files
# ──────────────────────────────────────────────────────────


class TestListCategories:
    def test_empty_dir_returns_empty(self, tmp_download_dir: Path):
        assert gallery_service.list_categories() == []

    def test_returns_category_names(self, tmp_download_dir: Path):
        (tmp_download_dir / "discord").mkdir()
        (tmp_download_dir / "pixiv").mkdir()
        cats = gallery_service.list_categories()
        names = [c["name"] for c in cats]
        assert "discord" in names
        assert "pixiv" in names

    def test_hidden_dirs_excluded(self, tmp_download_dir: Path):
        (tmp_download_dir / ".hidden").mkdir()
        cats = gallery_service.list_categories()
        assert all(c["name"] != ".hidden" for c in cats)


class TestListItems:
    def test_unknown_category_returns_empty(self, tmp_download_dir: Path):
        assert gallery_service.list_items("nonexistent") == []

    def test_leaf_dir_returned_as_dir_item(self, tmp_download_dir: Path):
        leaf = tmp_download_dir / "gallery" / "work1"
        leaf.mkdir(parents=True)
        (leaf / "a.jpg").write_bytes(b"img")
        items = gallery_service.list_items("gallery")
        assert any(i["name"] == "work1" and i["type"] == "dir" for i in items)

    def test_standalone_media_file_returned(self, tmp_download_dir: Path):
        cat = tmp_download_dir / "ytdlp"
        cat.mkdir()
        (cat / "video.mp4").write_bytes(b"v")
        items = gallery_service.list_items("ytdlp")
        assert any(i["name"] == "video.mp4" and i["type"] == "file" for i in items)


class TestListFiles:
    def test_single_file_item(self, tmp_download_dir: Path):
        f = tmp_download_dir / "solo.jpg"
        f.write_bytes(b"img")
        files = gallery_service.list_files("solo.jpg")
        assert len(files) == 1
        assert files[0]["name"] == "solo.jpg"

    def test_dir_item_lists_contents(self, tmp_download_dir: Path):
        folder = tmp_download_dir / "album"
        folder.mkdir()
        (folder / "1.jpg").write_bytes(b"a")
        (folder / "2.png").write_bytes(b"b")
        files = gallery_service.list_files("album")
        names = [f["name"] for f in files]
        assert "1.jpg" in names
        assert "2.png" in names
