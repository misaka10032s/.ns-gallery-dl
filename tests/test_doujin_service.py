"""
tests/test_doujin_service.py

覆蓋 doujin_service（本子 cover wall / reader / edit panel 的服務層）：
- app.config.gallery_modes.resolve_mode：source -> mode 的設定驅動解析
- natural_sort_key：頁面自然排序（"10.jpg" 不能排在 "2.jpg" 前面）
- resolve_book_dir：沿用 gallery_service 同款的路徑穿越防護
- list_source_books / get_book_detail：頁數推導、封面選擇、DB 覆蓋值
- update_book / add_link / delete_link：欄位驗證 + 讀寫往返
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config.gallery_modes import MODE_DOUJINSHI, MODE_GENERAL, resolve_mode
from app.services import doujin_service


# ──────────────────────────────────────────────────────────
# Mode resolution (config-driven, not hardcoded)
# ──────────────────────────────────────────────────────────


class TestResolveMode:
    @pytest.mark.parametrize("source", ["wnacg", "nhentai", "18comic", "exhentai"])
    def test_doujinshi_sources(self, source):
        assert resolve_mode(source) == MODE_DOUJINSHI

    @pytest.mark.parametrize(
        "source",
        ["pixiv", "bahamut", "yandere", "facebook", "twitter", "discord", "gelbooru", "kemono.partyfanbox", "x", "some-future-site"],
    )
    def test_general_sources(self, source):
        assert resolve_mode(source) == MODE_GENERAL


# ──────────────────────────────────────────────────────────
# Natural sort
# ──────────────────────────────────────────────────────────


class TestNaturalSortKey:
    def test_numeric_order_not_lexicographic(self):
        names = ["10.jpg", "2.jpg", "1.jpg"]
        assert sorted(names, key=doujin_service.natural_sort_key) == ["1.jpg", "2.jpg", "10.jpg"]

    def test_zero_padded_still_correct(self):
        names = ["010.png", "002.png", "001.png"]
        assert sorted(names, key=doujin_service.natural_sort_key) == ["001.png", "002.png", "010.png"]

    def test_mixed_text_and_numeric_does_not_raise(self):
        # cover.png has no digit token; 003.png does — different tuple shapes
        # must still compare without TypeError.
        names = ["003.png", "cover.png", "001.png", "002.png"]
        result = sorted(names, key=doujin_service.natural_sort_key)
        assert result.index("001.png") < result.index("002.png") < result.index("003.png")


# ──────────────────────────────────────────────────────────
# resolve_book_dir — path traversal guard
# ──────────────────────────────────────────────────────────


class TestResolveBookDir:
    def test_valid_book_dir(self, tmp_doujin_download_dir: Path):
        book = tmp_doujin_download_dir / "wnacg" / "12345_title"
        book.mkdir(parents=True)
        result = doujin_service.resolve_book_dir("wnacg/12345_title")
        assert result == book.resolve()

    def test_general_source_rejected(self, tmp_doujin_download_dir: Path):
        (tmp_doujin_download_dir / "pixiv" / "artist").mkdir(parents=True)
        assert doujin_service.resolve_book_dir("pixiv/artist") is None

    def test_nested_path_rejected_not_a_direct_book(self, tmp_doujin_download_dir: Path):
        deep = tmp_doujin_download_dir / "wnacg" / "book" / "sub"
        deep.mkdir(parents=True)
        assert doujin_service.resolve_book_dir("wnacg/book/sub") is None

    def test_dotdot_traversal_rejected(self, tmp_doujin_download_dir: Path):
        assert doujin_service.resolve_book_dir("wnacg/../../etc") is None

    def test_absolute_path_traversal_rejected(self, tmp_doujin_download_dir: Path):
        assert doujin_service.resolve_book_dir("/etc/passwd") is None

    def test_nonexistent_dir_rejected(self, tmp_doujin_download_dir: Path):
        assert doujin_service.resolve_book_dir("wnacg/does-not-exist") is None


# ──────────────────────────────────────────────────────────
# list_source_books — page-count derivation + cover selection
# ──────────────────────────────────────────────────────────


class TestListSourceBooks:
    def test_unconfigured_source_returns_none(self, tmp_doujin_download_dir: Path, tmp_db):
        assert doujin_service.list_source_books("pixiv") is None

    def test_derives_page_count_from_files(self, tmp_doujin_download_dir: Path, tmp_db):
        book = tmp_doujin_download_dir / "wnacg" / "book_a"
        book.mkdir(parents=True)
        for name in ("001.png", "002.png", "003.png"):
            (book / name).write_bytes(b"x")
        (book / "readme.txt").write_bytes(b"not a page")  # non-image ignored

        books = doujin_service.list_source_books("wnacg")
        assert len(books) == 1
        assert books[0]["page_count"] == 3
        assert books[0]["cover"] == "wnacg/book_a/001.png"

    def test_never_writes_a_db_row_on_plain_listing(self, tmp_doujin_download_dir: Path, tmp_db):
        from app.storage.repositories import doujin_repo

        book = tmp_doujin_download_dir / "wnacg" / "book_b"
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")

        doujin_service.list_source_books("wnacg")
        assert doujin_repo.get_book("wnacg/book_b") is None


# ──────────────────────────────────────────────────────────
# get_book_detail / update_book — read/update roundtrip
# ──────────────────────────────────────────────────────────


class TestBookDetailAndUpdate:
    def _make_book(self, root: Path, n_pages: int = 5) -> Path:
        book = root / "wnacg" / "book_c"
        book.mkdir(parents=True)
        for i in range(1, n_pages + 1):
            (book / f"{i:03d}.png").write_bytes(b"x")
        return book

    def test_detail_lazily_creates_row_with_derived_page_count(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, n_pages=5)
        detail = doujin_service.get_book_detail("wnacg/book_c")
        assert detail is not None
        assert detail["page_count"] == 5
        assert detail["title"] == "book_c"
        assert len(detail["pages"]) == 5
        assert detail["pages"][0]["name"] == "001.png"

    def test_update_title_and_purchase_state(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir)
        updated = doujin_service.update_book(
            "wnacg/book_c", {"title": "自訂標題", "purchase_state": "purchased"}
        )
        assert updated["title"] == "自訂標題"
        assert updated["purchase_state"] == "purchased"

        # persisted — a fresh read sees it too
        again = doujin_service.get_book_detail("wnacg/book_c")
        assert again["title"] == "自訂標題"
        assert again["purchase_state"] == "purchased"

    def test_invalid_purchase_state_rejected(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir)
        with pytest.raises(doujin_service.ValidationError):
            doujin_service.update_book("wnacg/book_c", {"purchase_state": "wishlist"})

    def test_page_count_override_wins_over_derived(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, n_pages=5)
        updated = doujin_service.update_book("wnacg/book_c", {"page_count_override": 999})
        assert updated["page_count"] == 999
        assert updated["page_count_override"] == 999

    def test_page_count_override_cleared_falls_back_to_derived(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, n_pages=5)
        doujin_service.update_book("wnacg/book_c", {"page_count_override": 999})
        cleared = doujin_service.update_book("wnacg/book_c", {"page_count_override": None})
        assert cleared["page_count"] == 5
        assert cleared["page_count_override"] is None

    def test_cover_page_must_be_a_real_page(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, n_pages=3)
        with pytest.raises(doujin_service.ValidationError):
            doujin_service.update_book("wnacg/book_c", {"cover_page": "999.png"})

    def test_cover_page_override_reflected_in_cover(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, n_pages=3)
        updated = doujin_service.update_book("wnacg/book_c", {"cover_page": "002.png"})
        assert updated["cover"] == "wnacg/book_c/002.png"

    def test_unknown_book_returns_none(self, tmp_doujin_download_dir, tmp_db):
        assert doujin_service.update_book("wnacg/nope", {"title": "x"}) is None
        assert doujin_service.get_book_detail("wnacg/nope") is None


# ──────────────────────────────────────────────────────────
# Links — add / remove
# ──────────────────────────────────────────────────────────


class TestLinks:
    def _make_book(self, root: Path) -> Path:
        book = root / "wnacg" / "book_d"
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        return book

    def test_add_and_list_links(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir)
        doujin_service.add_link("wnacg/book_d", "N網", "https://nhentai.example/1")
        doujin_service.add_link("wnacg/book_d", "購買網", "https://shop.example/1")

        detail = doujin_service.get_book_detail("wnacg/book_d")
        urls = {link["url"] for link in detail["links"]}
        assert urls == {"https://nhentai.example/1", "https://shop.example/1"}

    def test_duplicate_link_rejected(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir)
        doujin_service.add_link("wnacg/book_d", "N網", "https://nhentai.example/1")
        with pytest.raises(ValueError):
            doujin_service.add_link("wnacg/book_d", "N網", "https://nhentai.example/1")

    def test_empty_url_rejected(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir)
        with pytest.raises(doujin_service.ValidationError):
            doujin_service.add_link("wnacg/book_d", "N網", "")

    def test_delete_link(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir)
        link = doujin_service.add_link("wnacg/book_d", "N網", "https://nhentai.example/1")
        assert doujin_service.delete_link("wnacg/book_d", link["id"]) is True

        detail = doujin_service.get_book_detail("wnacg/book_d")
        assert detail["links"] == []

    def test_delete_nonexistent_link_returns_false(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir)
        assert doujin_service.delete_link("wnacg/book_d", 999999) is False

    def test_add_link_unknown_book_returns_none(self, tmp_doujin_download_dir, tmp_db):
        assert doujin_service.add_link("wnacg/nope", "N網", "https://x.example") is None
