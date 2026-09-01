"""
tests/test_wnacg_provider.py

覆蓋 app/providers/sites/wnacg.py 的核心退化路徑：
- CONFIG API（Cloudflare Worker）失敗 -> 自動退化到 Server 2 備用線路，且檔名仍取自
  CONFIG 的 FILE_NAME（不是已經在真實頁面上消失的 p.download_filename）。
- _remove_illegal_chars 截斷時保留副檔名（下載器靠副檔名決定解壓分支）。
- _parse_config 對缺失/不符預期的 CONFIG 區塊回傳 None。

不打真實網路（wnacg.com / worker API），全部用假的 scraper/response 物件。
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import requests
from bs4 import BeautifulSoup

from app.providers.sites import wnacg

GALLERY_HTML = "<html><head><title>Test Title - wnacg</title></head><body></body></html>"

DOWNLOAD_INDEX_HTML = """
<html><body>
<script>
const CONFIG = {
  WORKER_API: "https://d1.wcdn.date/api/generate-link",
  FILE_KEY: "abc123",
  FILE_NAME: "我的合集.zip"
};
</script>
<a href="//dl1.wn01.download/down/123/abc.zip"><span>備用線路 (Server 2)</span></a>
</body></html>
"""

NO_CONFIG_HTML = "<html><body><p>nothing here</p></body></html>"


class _FakeResponse:
    def __init__(self, text: str = "", json_data=None, content: bytes = b"", headers=None, raise_exc: Exception | None = None):
        self.text = text
        self._json = json_data
        self.content = content
        self.headers = headers or {}
        self._raise_exc = raise_exc

    def raise_for_status(self) -> None:
        if self._raise_exc:
            raise self._raise_exc

    def json(self):
        return self._json

    def iter_content(self, chunk_size: int = 1024):
        if self.content:
            yield self.content


class _FakeScraper:
    """Records call order; `.get()` responses are consumed in sequence, `.post()`
    likewise — mirrors download_wnacg's actual call order (gallery page, download-index
    page, worker API, archive stream)."""

    def __init__(self, get_responses: list[_FakeResponse], post_responses: list[_FakeResponse] | None = None):
        self.headers: dict = {}
        self._get_responses = list(get_responses)
        self._post_responses = list(post_responses or [])
        self.post_calls: list[tuple] = []

    def get(self, url, headers=None, stream=False, timeout=None):
        return self._get_responses.pop(0)

    def post(self, url, json=None, headers=None):
        self.post_calls.append((url, json))
        return self._post_responses.pop(0)


def _make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("dummy.txt", "hello")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────
# _parse_config
# ──────────────────────────────────────────────────────────


class TestParseConfig:
    def test_extracts_worker_api_file_key_file_name(self):
        soup = BeautifulSoup(DOWNLOAD_INDEX_HTML, "lxml")
        result = wnacg._parse_config(soup)
        assert result == ("https://d1.wcdn.date/api/generate-link", "abc123", "我的合集.zip")

    def test_returns_none_when_config_block_absent(self):
        soup = BeautifulSoup(NO_CONFIG_HTML, "lxml")
        assert wnacg._parse_config(soup) is None


# ──────────────────────────────────────────────────────────
# _config_link — must propagate failure, never swallow it
# ──────────────────────────────────────────────────────────


class TestConfigLink:
    def test_raises_on_non_2xx_worker_response(self):
        """A Cloudflare-challenged worker endpoint returns non-2xx; _config_link must
        let that propagate so the caller can degrade to the fallback link."""
        scraper = _FakeScraper(
            get_responses=[],
            post_responses=[_FakeResponse(raise_exc=requests.exceptions.HTTPError("403 Client Error"))],
        )
        with pytest.raises(requests.exceptions.HTTPError):
            wnacg._config_link("https://d1.wcdn.date/api/generate-link", "abc123", "我的合集.zip", scraper)

    def test_returns_url_on_success(self):
        scraper = _FakeScraper(
            get_responses=[],
            post_responses=[_FakeResponse(json_data={"success": True, "url": "https://example.com/file.zip"})],
        )
        result = wnacg._config_link("https://worker", "key", "name.zip", scraper)
        assert result == "https://example.com/file.zip"

    def test_returns_none_when_success_false(self):
        scraper = _FakeScraper(get_responses=[], post_responses=[_FakeResponse(json_data={"success": False})])
        assert wnacg._config_link("https://worker", "key", "name.zip", scraper) is None


# ──────────────────────────────────────────────────────────
# _fallback_link
# ──────────────────────────────────────────────────────────


class TestFallbackLink:
    def test_uses_provided_file_name(self):
        soup = BeautifulSoup(DOWNLOAD_INDEX_HTML, "lxml")
        link, filename = wnacg._fallback_link(soup, "我的合集.zip")
        assert link == "https://dl1.wn01.download/down/123/abc.zip"
        assert filename == "我的合集.zip"

    def test_defaults_filename_when_none_given(self):
        soup = BeautifulSoup(DOWNLOAD_INDEX_HTML, "lxml")
        _, filename = wnacg._fallback_link(soup, None)
        assert filename == "wnacg_archive.zip"

    def test_returns_none_when_server2_anchor_missing(self):
        soup = BeautifulSoup(NO_CONFIG_HTML, "lxml")
        link, filename = wnacg._fallback_link(soup, "name.zip")
        assert link is None
        assert filename is None


# ──────────────────────────────────────────────────────────
# _remove_illegal_chars — gallery TITLE sanitizer, plain-slice truncation only.
# Extension-preserving truncation lives in a SEPARATE function
# (_sanitize_archive_filename, tested below) so it can never silently change
# this one's behaviour.
# ──────────────────────────────────────────────────────────


class TestRemoveIllegalChars:
    def test_short_name_unchanged_besides_illegal_chars(self):
        assert wnacg._remove_illegal_chars('a:b*c?.zip') == "abc.zip"

    def test_title_like_string_truncates_to_max_length_no_extension_logic(self):
        long_title = "a" * 200
        result = wnacg._remove_illegal_chars(long_title)
        assert result == "a" * 150
        assert len(result) == 150

    def test_title_ending_in_dot_suffix_still_uses_plain_slice(self):
        """Regression pin: a title whose tail happens to LOOK like a short
        extension (e.g. `.abcde`) must still get a plain `[:150]` slice from
        `_remove_illegal_chars` — never the archive filename's
        extension-preserving treatment. A 151-char title, tail `.abcde` (a
        plausible <=10-char "extension"), where the two helpers would diverge
        if they shared logic."""
        title = "a" * 145 + ".abcde"
        assert len(title) == 151
        expected_plain_slice = title[:150]

        result = wnacg._remove_illegal_chars(title)

        assert result == expected_plain_slice
        assert not result.endswith(".abcde")  # the extension-preserving branch never fires here
        # sanity: prove this really is the divergent case the extension-preserving
        # helper handles differently, so the pin is not vacuous
        assert wnacg._sanitize_archive_filename(title) != expected_plain_slice


# ──────────────────────────────────────────────────────────
# _sanitize_archive_filename — extension-preserving truncation, used ONLY for
# the archive filename (never the gallery title).
# ──────────────────────────────────────────────────────────


class TestSanitizeArchiveFilename:
    def test_short_name_unchanged_besides_illegal_chars(self):
        assert wnacg._sanitize_archive_filename('a:b*c?.zip') == "abc.zip"

    def test_long_archive_filename_preserves_extension(self):
        long_name = "x" * 200 + ".zip"
        result = wnacg._sanitize_archive_filename(long_name)
        assert result.endswith(".zip")
        assert len(result) <= 150

    def test_preserves_extension_for_each_supported_archive_type(self):
        for ext in (".zip", ".7z", ".rar"):
            long_name = "y" * 200 + ext
            result = wnacg._sanitize_archive_filename(long_name)
            assert result.endswith(ext), f"expected {ext} preserved, got {result!r}"


# ──────────────────────────────────────────────────────────
# download_wnacg — end-to-end degradation path
# ──────────────────────────────────────────────────────────


class TestDownloadWnacgDegradation:
    def test_worker_api_failure_degrades_to_fallback_with_config_filename(self, tmp_path: Path, monkeypatch):
        """Reproduces the diagnosed live failure: gallery + download-index pages load
        fine, CONFIG parses fine, but the worker POST 403s (Cloudflare challenge).
        download_wnacg must still succeed via the Server 2 link, using the CONFIG
        FILE_NAME rather than the dead p.download_filename selector's
        "wnacg_archive.zip" default."""
        zip_bytes = _make_zip_bytes()
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=DOWNLOAD_INDEX_HTML),
                _FakeResponse(content=zip_bytes, headers={"content-length": str(len(zip_bytes))}),
            ],
            post_responses=[_FakeResponse(raise_exc=requests.exceptions.HTTPError("403 Client Error"))],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-380688.html", tmp_path)

        assert status == "success"
        assert error == ""
        assert len(fake_scraper.post_calls) == 1  # the worker API was actually attempted

        gallery_dirs = list(tmp_path.iterdir())
        assert len(gallery_dirs) == 1
        download_dir = gallery_dirs[0]
        assert download_dir.name.startswith("380688_")

        archive_path = download_dir / "我的合集.zip"
        assert archive_path.exists(), f"expected CONFIG FILE_NAME as archive name, found: {list(download_dir.iterdir())}"
        assert (download_dir / "dummy.txt").exists(), "zip should have been extracted"

    def test_no_config_block_goes_straight_to_fallback(self, tmp_path: Path, monkeypatch):
        """If the page has no CONFIG script at all, the worker API must never be
        called — fallback is used directly."""
        zip_bytes = _make_zip_bytes()
        download_index_no_config = DOWNLOAD_INDEX_HTML.replace(
            'const CONFIG = {\n  WORKER_API: "https://d1.wcdn.date/api/generate-link",\n  FILE_KEY: "abc123",\n  FILE_NAME: "我的合集.zip"\n};',
            "",
        )
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=download_index_no_config),
                _FakeResponse(content=zip_bytes, headers={"content-length": str(len(zip_bytes))}),
            ],
            post_responses=[],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-380688.html", tmp_path)

        assert status == "success"
        assert error == ""
        assert fake_scraper.post_calls == []  # worker API never attempted

        download_dir = next(tmp_path.iterdir())
        assert (download_dir / "wnacg_archive.zip").exists()


# ──────────────────────────────────────────────────────────
# download_wnacg — failure legibility (Task 1): every distinct failure site
# must return a DIFFERENT, non-empty error string, not just "failed".
# ──────────────────────────────────────────────────────────


class TestDownloadWnacgFailureReasons:
    def test_url_without_aid_reports_no_download_and_reraises_nothing(self, tmp_path: Path):
        status, error = wnacg.download_wnacg("https://www.wnacg.com/not-a-gallery-url.html", tmp_path)
        assert status == "failed"
        assert "aid" in error

    def test_work_page_fetch_failure_is_distinguishable_from_download_page_failure(self, tmp_path: Path, monkeypatch):
        fake_scraper = _FakeScraper(
            get_responses=[_FakeResponse(raise_exc=requests.exceptions.HTTPError("403 Client Error"))],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "作品頁面" in error
        assert "403" in error

    def test_download_page_fetch_failure_has_its_own_distinct_message(self, tmp_path: Path, monkeypatch):
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(raise_exc=requests.exceptions.HTTPError("500 Server Error")),
            ],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "下載頁面" in error
        assert "500" in error

    def test_missing_title_element_reports_page_structure_message(self, tmp_path: Path, monkeypatch):
        fake_scraper = _FakeScraper(get_responses=[_FakeResponse(text="<html><body>no title here</body></html>")])
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "標題" in error

    def test_config_failure_plus_missing_fallback_reports_both_routes_exhausted(self, tmp_path: Path, monkeypatch):
        """Cloudflare 403 on the worker API AND no Server 2 anchor on the page —
        the worst case: BOTH routes are gone. The error must name the CONFIG
        API failure reason, not just say "failed"."""
        fake_scraper = _FakeScraper(
            get_responses=[_FakeResponse(text=GALLERY_HTML), _FakeResponse(text=DOWNLOAD_INDEX_HTML)],
            post_responses=[_FakeResponse(raise_exc=requests.exceptions.HTTPError("403 Client Error"))],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        monkeypatch.setattr(wnacg, "_fallback_link", lambda soup, file_name: (None, None))

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "CONFIG API" in error
        assert "備用線路" in error

    def test_no_config_and_no_fallback_reports_page_missing_config_message(self, tmp_path: Path, monkeypatch):
        no_config_html = DOWNLOAD_INDEX_HTML.replace(
            'const CONFIG = {\n  WORKER_API: "https://d1.wcdn.date/api/generate-link",\n  FILE_KEY: "abc123",\n  FILE_NAME: "我的合集.zip"\n};',
            "",
        ).replace('<a href="//dl1.wn01.download/down/123/abc.zip"><span>備用線路 (Server 2)</span></a>', "")
        fake_scraper = _FakeScraper(get_responses=[_FakeResponse(text=GALLERY_HTML), _FakeResponse(text=no_config_html)])
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "CONFIG" in error
        assert "備用線路" in error

    def test_archive_download_failure_reports_distinct_message(self, tmp_path: Path, monkeypatch):
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=DOWNLOAD_INDEX_HTML),
                _FakeResponse(raise_exc=requests.exceptions.ConnectionError("timeout")),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": "https://example.com/file.zip"})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "檔案下載失敗" in error

    def test_all_five_distinct_failure_sites_never_share_a_message(self, tmp_path: Path, monkeypatch):
        """Sanity pin for the task's core requirement: the user must be able to
        tell every failure case apart from the history alone — so no two
        distinct failure sites may ever produce an identical error string."""
        cases: list[tuple[str, str]] = []

        status, error = wnacg.download_wnacg("https://www.wnacg.com/no-aid-here.html", tmp_path)
        cases.append((status, error))

        fake_scraper = _FakeScraper(get_responses=[_FakeResponse(raise_exc=requests.exceptions.HTTPError("x"))])
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        fake_scraper = _FakeScraper(get_responses=[_FakeResponse(text="<html><body>x</body></html>")])
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        errors = [error for _, error in cases]
        assert len(errors) == len(set(errors)), f"duplicate error messages across distinct failure sites: {errors}"
