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
from app.services import doujin_meta_service, doujin_service


# ──────────────────────────────────────────────────────────
# Mode resolution (config-driven, not hardcoded)
# ──────────────────────────────────────────────────────────


class TestResolveMode:
    @pytest.mark.parametrize("source", ["wnacg", "nhentai", "18comic"])
    def test_doujinshi_sources(self, source):
        assert resolve_mode(source) == MODE_DOUJINSHI

    @pytest.mark.parametrize(
        "source",
        [
            "pixiv", "bahamut", "yandere", "facebook", "twitter", "discord", "gelbooru",
            "kemono.partyfanbox", "x", "some-future-site",
            # exhentai was removed from DOUJINSHI_SOURCES 2026-08-26 (needs a
            # site-specific cookie just to view a gallery) — it must resolve
            # to general mode like any other unconfigured source, and this
            # removal must not disturb the three that remain (asserted above).
            "exhentai",
        ],
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

    def test_needs_fetch_attention_false_when_never_fetched(self, tmp_doujin_download_dir, tmp_db):
        book = tmp_doujin_download_dir / "wnacg" / "book_never_fetched"
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        books = doujin_service.list_source_books("wnacg")
        assert books[0]["needs_fetch_attention"] is False

    def test_needs_fetch_attention_false_after_ok_fetch(self, tmp_doujin_download_dir, tmp_db, monkeypatch):
        book = tmp_doujin_download_dir / "wnacg" / "12345_book_ok"
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        monkeypatch.setattr(
            doujin_service.doujin_meta_service,
            "fetch_metadata",
            lambda source, gid: {"status": "ok", "title": "t", "artist": "", "circle": "", "page_count": 1, "source_url": "u"},
        )
        doujin_service.fetch_book_metadata("wnacg/12345_book_ok")
        books = doujin_service.list_source_books("wnacg")
        assert books[0]["needs_fetch_attention"] is False

    @pytest.mark.parametrize("status", ["blocked", "not_found", "network_error"])
    def test_needs_fetch_attention_true_for_actionable_failures(
        self, tmp_doujin_download_dir, tmp_db, monkeypatch, status
    ):
        book = tmp_doujin_download_dir / "wnacg" / "12345_book_fail"
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        monkeypatch.setattr(
            doujin_service.doujin_meta_service, "fetch_metadata", lambda source, gid: {"status": status}
        )
        doujin_service.fetch_book_metadata("wnacg/12345_book_fail")
        books = doujin_service.list_source_books("wnacg")
        assert books[0]["needs_fetch_attention"] is True

    def test_needs_fetch_attention_false_for_non_actionable_statuses(
        self, tmp_doujin_download_dir, tmp_db
    ):
        # no_gallery_id (folder has no leading numeric id) is a property of
        # the source/folder, not something a retry could ever fix — must not
        # be flagged.
        book = tmp_doujin_download_dir / "wnacg" / "[no id here] book"
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        doujin_service.fetch_book_metadata("wnacg/[no id here] book")
        books = doujin_service.list_source_books("wnacg")
        assert books[0]["needs_fetch_attention"] is False


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


# ──────────────────────────────────────────────────────────
# title/artist/circle precedence — manual override > fetched > default
# ──────────────────────────────────────────────────────────


class TestFieldPrecedence:
    def _make_book(self, root: Path, name: str = "book_e") -> Path:
        book = root / "wnacg" / name
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        return book

    def test_default_is_folder_name_when_untouched(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir)
        detail = doujin_service.get_book_detail("wnacg/book_e")
        assert detail["title"] == "book_e"
        assert detail["title_source"] == "default"
        assert detail["artist"] == ""
        assert detail["artist_source"] == "default"

    def test_fetched_value_wins_over_default(self, tmp_doujin_download_dir, tmp_db, monkeypatch):
        self._make_book(tmp_doujin_download_dir)
        monkeypatch.setattr(
            doujin_service.doujin_meta_service,
            "extract_gallery_id",
            lambda name: "1",
        )
        monkeypatch.setattr(
            doujin_service.doujin_meta_service,
            "fetch_metadata",
            lambda source, gid: {
                "status": "ok",
                "title": "站點標題",
                "artist": "站點作者",
                "circle": "站點社團",
                "page_count": 1,
                "source_url": "https://example.test/g/1/",
            },
        )
        detail = doujin_service.fetch_book_metadata("wnacg/book_e")
        assert detail["title"] == "站點標題"
        assert detail["title_source"] == "fetched"
        assert detail["artist"] == "站點作者"
        assert detail["circle"] == "站點社團"
        assert detail["meta_fetch_status"] == "ok"
        assert detail["meta_source_url"] == "https://example.test/g/1/"

    def test_manual_override_wins_over_fetched(self, tmp_doujin_download_dir, tmp_db, monkeypatch):
        self._make_book(tmp_doujin_download_dir)
        monkeypatch.setattr(doujin_service.doujin_meta_service, "extract_gallery_id", lambda name: "1")
        monkeypatch.setattr(
            doujin_service.doujin_meta_service,
            "fetch_metadata",
            lambda source, gid: {"status": "ok", "title": "站點標題", "artist": "", "circle": "", "page_count": None, "source_url": "u"},
        )
        doujin_service.fetch_book_metadata("wnacg/book_e")
        updated = doujin_service.update_book("wnacg/book_e", {"title": "使用者自訂"})
        assert updated["title"] == "使用者自訂"
        assert updated["title_source"] == "manual"

        # a SECOND fetch must not clobber the manual override
        doujin_service.fetch_book_metadata("wnacg/book_e")
        again = doujin_service.get_book_detail("wnacg/book_e")
        assert again["title"] == "使用者自訂"
        assert again["title_source"] == "manual"

    def test_clearing_override_falls_back_to_fetched(self, tmp_doujin_download_dir, tmp_db, monkeypatch):
        self._make_book(tmp_doujin_download_dir)
        monkeypatch.setattr(doujin_service.doujin_meta_service, "extract_gallery_id", lambda name: "1")
        monkeypatch.setattr(
            doujin_service.doujin_meta_service,
            "fetch_metadata",
            lambda source, gid: {"status": "ok", "title": "站點標題", "artist": "", "circle": "", "page_count": None, "source_url": "u"},
        )
        doujin_service.fetch_book_metadata("wnacg/book_e")
        doujin_service.update_book("wnacg/book_e", {"title": "使用者自訂"})
        cleared = doujin_service.update_book("wnacg/book_e", {"title": None})
        assert cleared["title"] == "站點標題"
        assert cleared["title_source"] == "fetched"


# ──────────────────────────────────────────────────────────
# Gallery id extraction
# ──────────────────────────────────────────────────────────


class TestExtractGalleryId:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("100873_[七色御伽草子 (宮瀬まひろ)] さなえの湯(泡)", "100873"),
            ("121697 [たかやKi] ドキドキ★コミュニティーライフ", "121697"),
            ("95999 [アットホーム酒家(たくのみ)] 援助交配1~6", "95999"),
            ("[モノ手紙 (かるたも)] えっちなおなかかんさつ。", None),
            ("no digits at the front at all", None),
        ],
    )
    def test_extract(self, name, expected):
        assert doujin_meta_service.extract_gallery_id(name) == expected


# ──────────────────────────────────────────────────────────
# fetch_book_metadata failure paths (network mocked, never live)
# ──────────────────────────────────────────────────────────


class TestFetchBookMetadataFailurePaths:
    def _make_book(self, root: Path, name: str) -> Path:
        book = root / "wnacg" / name
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        return book

    def test_no_gallery_id_recorded_and_visible(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, "[no id prefix here] title")
        detail = doujin_service.fetch_book_metadata("wnacg/[no id prefix here] title")
        assert detail["meta_fetch_status"] == "no_gallery_id"
        assert detail["gallery_id"] is None
        assert detail["title_source"] == "default"

    def test_unsupported_source_recorded(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, "12345_some title")
        detail = doujin_service.fetch_book_metadata("wnacg/12345_some title")
        assert detail["meta_fetch_status"] == "unsupported_source"

    def test_not_found_status(self, tmp_doujin_download_dir, tmp_db, monkeypatch):
        self._make_book(tmp_doujin_download_dir, "12345_some title")
        monkeypatch.setattr(doujin_service.doujin_meta_service, "extract_gallery_id", lambda name: "12345")
        monkeypatch.setattr(
            doujin_service.doujin_meta_service,
            "fetch_metadata",
            lambda source, gid: {"status": "not_found"},
        )
        detail = doujin_service.fetch_book_metadata("wnacg/12345_some title")
        assert detail["meta_fetch_status"] == "not_found"
        assert detail["title_source"] == "default"

    def test_blocked_status_via_missing_info_block(self, monkeypatch):
        class FakeResponse:
            status_code = 200
            text = "<html><body>just a captcha, no info block here</body></html>"

            def raise_for_status(self):
                return None

        class FakeScraper:
            def get(self, url, timeout=15):
                return FakeResponse()

        monkeypatch.setattr(doujin_meta_service, "_scraper_with_cookies", lambda domain: FakeScraper())
        monkeypatch.setattr(doujin_meta_service, "_throttle", lambda domain: None)
        result = doujin_meta_service.fetch_metadata("nhentai", "1")
        assert result["status"] == "blocked"

    def test_not_found_status_via_404(self, monkeypatch):
        class FakeResponse:
            status_code = 404
            text = ""

            def raise_for_status(self):
                return None

        class FakeScraper:
            def get(self, url, timeout=15):
                return FakeResponse()

        monkeypatch.setattr(doujin_meta_service, "_scraper_with_cookies", lambda domain: FakeScraper())
        monkeypatch.setattr(doujin_meta_service, "_throttle", lambda domain: None)
        result = doujin_meta_service.fetch_metadata("nhentai", "999999999")
        assert result["status"] == "not_found"

    def test_network_error_after_retries_exhausted(self, monkeypatch):
        class ExplodingScraper:
            def get(self, url, timeout=15):
                raise ConnectionError("boom")

        sleeps: list[float] = []
        monkeypatch.setattr(doujin_meta_service, "_scraper_with_cookies", lambda domain: ExplodingScraper())
        monkeypatch.setattr(doujin_meta_service, "_throttle", lambda domain: None)
        monkeypatch.setattr(doujin_meta_service.time, "sleep", lambda s: sleeps.append(s))
        result = doujin_meta_service.fetch_metadata("nhentai", "1")
        assert result["status"] == "network_error"
        assert len(sleeps) == doujin_meta_service.MAX_RETRIES

    def test_cookie_lookup_failure_does_not_abort_fetch(self, monkeypatch):
        """Regression test — live verification (2026-08-26) found that a
        cookie-lookup failure (e.g. cookie_entries table not yet ready) was
        unguarded in _scraper_with_cookies and propagated all the way up
        into the retry loop's generic except-Exception, getting
        misclassified as 'network_error' and burning 2 retries + backoff
        per book for a problem retrying could never fix. A cookie lookup is
        best-effort and must never block the fetch itself."""

        def _boom(domain):
            raise RuntimeError("cookie_entries table not ready")

        monkeypatch.setattr(doujin_meta_service.cookies_repo, "find_cookie", _boom)
        scraper = doujin_meta_service._scraper_with_cookies("nhentai.net")
        assert scraper is not None

    def test_ok_result_extracts_structured_fields(self, monkeypatch):
        html = (
            '<div id="info">'
            '<h1 class="title">'
            '<span class="before">[Circle (Artist)]</span>'
            '<span class="pretty">Clean Title</span>'
            '<span class="after">[Digital]</span>'
            "</h1>"
            '<div class="tag-container field-name">Artists:'
            '<span class="tags"><a><span class="name">artist name</span></a></span>'
            "</div>"
            '<div class="tag-container field-name">Groups:'
            '<span class="tags"><a><span class="name">circle name</span></a></span>'
            "</div>"
            '<div class="tag-container field-name">Pages:'
            '<span class="tags"><a><span class="name">28</span></a></span>'
            "</div>"
            "</div>"
        )

        class FakeResponse:
            status_code = 200
            text = html
            encoding = "utf-8"

            def raise_for_status(self):
                return None

        class FakeScraper:
            def get(self, url, timeout=15):
                return FakeResponse()

        monkeypatch.setattr(doujin_meta_service, "_scraper_with_cookies", lambda domain: FakeScraper())
        monkeypatch.setattr(doujin_meta_service, "_throttle", lambda domain: None)
        result = doujin_meta_service.fetch_metadata("nhentai", "118477")
        assert result["status"] == "ok"
        assert result["title"] == "Clean Title"
        assert result["artist"] == "artist name"
        assert result["circle"] == "circle name"
        assert result["page_count"] == 28
        assert result["source_url"] == "https://nhentai.net/g/118477/"


# ──────────────────────────────────────────────────────────
# Series (分類) -- normalization, near-duplicate, create-from-panel, delete
# ──────────────────────────────────────────────────────────


class TestNormalizeSeriesName:
    def test_trims_leading_and_trailing_space(self):
        assert doujin_service.normalize_series_name("  東方Project  ") == "東方Project"

    def test_collapses_internal_double_space(self):
        assert doujin_service.normalize_series_name("東方  Project") == "東方 Project"

    def test_collapses_multiple_internal_whitespace_runs(self):
        assert doujin_service.normalize_series_name("A   B\tC") == "A B C"

    def test_preserves_original_casing(self):
        assert doujin_service.normalize_series_name("BlueArchive") == "BlueArchive"

    def test_empty_after_trim_is_empty_string(self):
        assert doujin_service.normalize_series_name("   ") == ""


class TestResolveOrCreateSeries:
    def test_create_new_series(self, tmp_db):
        result = doujin_service.resolve_or_create_series("東方Project")
        assert result["status"] == "created"
        assert result["series"]["name"] == "東方Project"
        assert result["series"]["normalized_name"] == "東方project"

    def test_empty_name_rejected(self, tmp_db):
        with pytest.raises(doujin_service.ValidationError):
            doujin_service.resolve_or_create_series("   ")

    def test_exact_case_difference_reuses_existing(self, tmp_db):
        first = doujin_service.resolve_or_create_series("Blue Archive")
        second = doujin_service.resolve_or_create_series("blue archive")
        assert second["status"] == "reused"
        assert second["series"]["id"] == first["series"]["id"]

    def test_exact_whitespace_difference_reuses_existing(self, tmp_db):
        first = doujin_service.resolve_or_create_series("東方Project")
        second = doujin_service.resolve_or_create_series("  東方Project ")
        assert second["status"] == "reused"
        assert second["series"]["id"] == first["series"]["id"]

    def test_internal_double_space_reuses_existing(self, tmp_db):
        first = doujin_service.resolve_or_create_series("東方 Project")
        second = doujin_service.resolve_or_create_series("東方  Project")
        assert second["status"] == "reused"
        assert second["series"]["id"] == first["series"]["id"]

    def test_near_duplicate_raises_with_candidates(self, tmp_db):
        doujin_service.resolve_or_create_series("東方Project")
        with pytest.raises(doujin_service.NearDuplicateSeriesError) as exc_info:
            doujin_service.resolve_or_create_series("東方Proiect")  # typo: i instead of j
        candidates = exc_info.value.candidates
        assert len(candidates) >= 1
        assert candidates[0]["name"] == "東方Project"

    def test_near_duplicate_confirm_forces_create(self, tmp_db):
        first = doujin_service.resolve_or_create_series("東方Project")
        second = doujin_service.resolve_or_create_series("東方Proiect", confirm=True)
        assert second["status"] == "created"
        assert second["series"]["id"] != first["series"]["id"]

    def test_unrelated_name_no_near_duplicate(self, tmp_db):
        doujin_service.resolve_or_create_series("東方Project")
        result = doujin_service.resolve_or_create_series("Fate/Grand Order")
        assert result["status"] == "created"


class TestSearchSeries:
    def test_empty_query_lists_all(self, tmp_db):
        doujin_service.resolve_or_create_series("東方Project")
        doujin_service.resolve_or_create_series("Fate/Grand Order")
        results = doujin_service.search_series("")
        names = {s["name"] for s in results}
        assert names == {"東方Project", "Fate/Grand Order"}

    def test_substring_filter_case_insensitive(self, tmp_db):
        doujin_service.resolve_or_create_series("Blue Archive")
        doujin_service.resolve_or_create_series("Fate/Grand Order")
        results = doujin_service.search_series("blue")
        assert [s["name"] for s in results] == ["Blue Archive"]


class TestDeleteSeries:
    def _make_book(self, root: Path, name: str) -> Path:
        book = root / "wnacg" / name
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        return book

    def test_delete_nonexistent_returns_none(self, tmp_db):
        assert doujin_service.delete_series(999999) is None

    def test_delete_unreferenced_series(self, tmp_db):
        created = doujin_service.resolve_or_create_series("東方Project")["series"]
        result = doujin_service.delete_series(created["id"])
        assert result == {"deleted": True, "cleared_books": 0}
        assert doujin_service.search_series("") == []

    def test_delete_blocked_when_referenced(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, "book_f")
        series = doujin_service.resolve_or_create_series("東方Project")["series"]
        doujin_service.update_book("wnacg/book_f", {"series_id": series["id"]})

        with pytest.raises(doujin_service.SeriesInUseError) as exc_info:
            doujin_service.delete_series(series["id"])
        assert exc_info.value.book_count == 1

        detail = doujin_service.get_book_detail("wnacg/book_f")
        assert detail["series_id"] == series["id"]

    def test_delete_force_clears_referencing_books(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, "book_g")
        series = doujin_service.resolve_or_create_series("東方Project")["series"]
        doujin_service.update_book("wnacg/book_g", {"series_id": series["id"]})

        result = doujin_service.delete_series(series["id"], force=True)
        assert result == {"deleted": True, "cleared_books": 1}

        detail = doujin_service.get_book_detail("wnacg/book_g")
        assert detail["series_id"] is None
        assert detail["series_name"] is None


class TestUpdateBookSeriesId:
    def _make_book(self, root: Path, name: str) -> Path:
        book = root / "wnacg" / name
        book.mkdir(parents=True)
        (book / "001.png").write_bytes(b"x")
        return book

    def test_valid_series_id_attaches(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, "book_h")
        series = doujin_service.resolve_or_create_series("東方Project")["series"]
        updated = doujin_service.update_book("wnacg/book_h", {"series_id": series["id"]})
        assert updated["series_id"] == series["id"]
        assert updated["series_name"] == "東方Project"

    def test_invalid_series_id_rejected(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, "book_i")
        with pytest.raises(doujin_service.ValidationError):
            doujin_service.update_book("wnacg/book_i", {"series_id": 999999})

    def test_null_series_id_clears(self, tmp_doujin_download_dir, tmp_db):
        self._make_book(tmp_doujin_download_dir, "book_j")
        series = doujin_service.resolve_or_create_series("東方Project")["series"]
        doujin_service.update_book("wnacg/book_j", {"series_id": series["id"]})
        cleared = doujin_service.update_book("wnacg/book_j", {"series_id": None})
        assert cleared["series_id"] is None
