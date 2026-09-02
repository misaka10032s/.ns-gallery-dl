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

    def test_config_success_false_with_no_fallback_reports_distinct_message(self, tmp_path: Path, monkeypatch):
        """Distinct from the `config_error` case above: here the worker POST does
        NOT raise — it returns HTTP 200 with `{"success": false}`, so `_config_link`
        returns `None` cleanly (no exception at all). This is a SEPARATE branch
        (`if config: ...` with no `config_error`) from
        `test_config_failure_plus_missing_fallback_reports_both_routes_exhausted`
        above, and must produce its own distinct message."""
        html_no_fallback_anchor = DOWNLOAD_INDEX_HTML.replace(
            '<a href="//dl1.wn01.download/down/123/abc.zip"><span>備用線路 (Server 2)</span></a>', ""
        )
        fake_scraper = _FakeScraper(
            get_responses=[_FakeResponse(text=GALLERY_HTML), _FakeResponse(text=html_no_fallback_anchor)],
            post_responses=[_FakeResponse(json_data={"success": False})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert error == "CONFIG API 未回傳有效下載連結，且備用線路（Server 2）也找不到下載連結"

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

    def test_archive_extraction_failure_reports_distinct_message(self, tmp_path: Path, monkeypatch):
        """The 9th and last `return "failed"` site in `download_wnacg`: the
        archive downloads fine but is not a valid zip, so `zipfile.ZipFile`
        raises during extraction."""
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=DOWNLOAD_INDEX_HTML),
                _FakeResponse(content=b"not actually a zip file", headers={"content-length": "24"}),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": "https://example.com/file.zip"})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "解壓縮失敗" in error

    def test_all_nine_failure_return_sites_never_share_a_message(self, tmp_path: Path, monkeypatch):
        """Every `return "failed", ...` site in `download_wnacg` (there are 9 —
        see the `grep` count backing this task) is exercised here and must
        produce a message distinct from every other site's: the user has to be
        able to tell every failure case apart from the history/jobs UI alone,
        so no two distinct failure sites may ever produce an identical error
        string. (Previously this test's name claimed "all five" while only
        actually exercising 3 of the 9 sites — renamed and extended rather than
        left overstating its own coverage.)"""
        cases: list[tuple[str, str]] = []

        # site 1 (line ~133): URL has no aid.
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/no-aid-here.html", tmp_path))

        # site 2 (line ~140): gallery page GET raises.
        fake_scraper = _FakeScraper(get_responses=[_FakeResponse(raise_exc=requests.exceptions.HTTPError("403"))])
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        # site 3 (line ~145): gallery page has no <title>.
        fake_scraper = _FakeScraper(get_responses=[_FakeResponse(text="<html><body>no title</body></html>")])
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        # site 4 (line ~156): download-index page GET raises.
        fake_scraper = _FakeScraper(
            get_responses=[_FakeResponse(text=GALLERY_HTML), _FakeResponse(raise_exc=requests.exceptions.HTTPError("500"))],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        # site 5 (line ~175): worker POST raises AND fallback anchor missing.
        html_no_fallback = DOWNLOAD_INDEX_HTML.replace(
            '<a href="//dl1.wn01.download/down/123/abc.zip"><span>備用線路 (Server 2)</span></a>', ""
        )
        fake_scraper = _FakeScraper(
            get_responses=[_FakeResponse(text=GALLERY_HTML), _FakeResponse(text=html_no_fallback)],
            post_responses=[_FakeResponse(raise_exc=requests.exceptions.HTTPError("403"))],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        # site 6 (line ~177): worker POST succeeds but success=false, AND fallback anchor missing.
        fake_scraper = _FakeScraper(
            get_responses=[_FakeResponse(text=GALLERY_HTML), _FakeResponse(text=html_no_fallback)],
            post_responses=[_FakeResponse(json_data={"success": False})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        # site 7 (line ~178): no CONFIG block at all, AND fallback anchor missing
        # (NO_CONFIG_HTML has neither a CONFIG script nor a Server-2 anchor).
        fake_scraper = _FakeScraper(get_responses=[_FakeResponse(text=GALLERY_HTML), _FakeResponse(text=NO_CONFIG_HTML)])
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        # site 8 (line ~194): archive stream download GET raises.
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=DOWNLOAD_INDEX_HTML),
                _FakeResponse(raise_exc=requests.exceptions.ConnectionError("timeout")),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": "https://example.com/file.zip"})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        # site 9 (line ~208): downloaded archive is not a valid zip.
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=DOWNLOAD_INDEX_HTML),
                _FakeResponse(content=b"not actually a zip file", headers={"content-length": "24"}),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": "https://example.com/file.zip"})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)
        cases.append(wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path))

        assert len(cases) == 9
        assert all(status == "failed" for status, _ in cases), cases
        errors = [error for _, error in cases]
        assert len(errors) == len(set(errors)), f"duplicate error messages across distinct failure sites: {errors}"


# ──────────────────────────────────────────────────────────
# _sanitize_error / _strip_url_query — neither a signed download-URL token
# nor a local absolute filesystem path may reach `jobs.error` /
# `history_entries.meta.error`, both of which the Web UI renders verbatim.
# ──────────────────────────────────────────────────────────


class TestSanitizeError:
    def test_strip_url_query_drops_query_and_fragment(self):
        assert wnacg._strip_url_query("https://host/path?token=SECRET&x=1#frag") == "https://host/path"

    def test_strip_url_query_leaves_url_without_query_unchanged(self):
        assert wnacg._strip_url_query("https://host/path") == "https://host/path"

    def test_sanitize_error_strips_full_url_with_token(self):
        url = "https://d1.wcdn.date/dl/abc?token=SECRETTOKEN"
        message = f"404 Client Error: Not Found for url: {url}"
        sanitized = wnacg._sanitize_error(message, urls=(url,))
        assert "SECRETTOKEN" not in sanitized
        assert "https://d1.wcdn.date/dl/abc" in sanitized

    def test_sanitize_error_strips_path_only_query_fragment(self):
        """urllib3's own connection-error messages often embed only the
        path+query (no scheme/host) — a plain full-URL substring match would
        miss this shape entirely."""
        url = "https://d1.wcdn.date/dl/abc?token=SECRETTOKEN"
        message = "Max retries exceeded with url: /dl/abc?token=SECRETTOKEN (Caused by ...)"
        sanitized = wnacg._sanitize_error(message, urls=(url,))
        assert "SECRETTOKEN" not in sanitized

    def test_sanitize_error_reduces_local_path_to_basename(self):
        path = Path("/home/someuser/.ns-media-hub/download/gallery-dl/wnacg.com/380688_Title/我的合集.zip")
        message = f"cannot open archive: {path}"
        sanitized = wnacg._sanitize_error(message, paths=(path,))
        assert str(path) not in sanitized
        assert "someuser" not in sanitized
        assert "我的合集.zip" in sanitized

    def test_sanitize_error_is_a_no_op_when_nothing_matches(self):
        assert wnacg._sanitize_error("plain message", urls=("https://x/y?token=z",), paths=(Path("/a/b"),)) == "plain message"

    def test_strip_url_query_strips_userinfo_credentials(self):
        """Defect 1b: `_strip_url_query` used to blank only query/fragment, never
        `netloc` — `user:pass@host` survived verbatim.

        Owner's rule (2026-09-02): a credential is REPLACED by a placeholder,
        never deleted — so the assertion is no longer "host survives alone",
        it is "the secret is gone AND host/path survive AND a placeholder
        marks where the credential was"."""
        result = wnacg._strip_url_query("https://user:SUPERPASS@host/path?token=X")
        assert result == "https://[@acc]:[@pw]@host/path"
        assert "SUPERPASS" not in result
        assert "host/path" in result

    def test_sanitize_error_strips_url_never_passed_via_urls_kwarg(self):
        """Defect 1a's core case, at the unit level: a URL the caller never
        named (no `urls=` entry at all) must still be redacted — this is what
        makes a post-redirect URL (which `download_wnacg` never sees as a
        string it can pass to `urls=`) safe."""
        message = "403 Client Error: Forbidden for url: https://cdn-mirror.example.com/abc.zip?token=REDIRECTEDSECRET&exp=1"
        sanitized = wnacg._sanitize_error(message)
        assert "REDIRECTEDSECRET" not in sanitized
        assert "https://cdn-mirror.example.com/abc.zip" in sanitized

    def test_sanitize_error_strips_userinfo_credentials_via_blanket_scan(self):
        """Owner's rule (2026-09-02): placeholder substitution, not deletion
        — host/path must survive alongside the `[@acc]`/`[@pw]` markers,
        not just "secret gone"."""
        message = "error fetching https://user:SUPERPASS@host/path?token=X for job"
        sanitized = wnacg._sanitize_error(message)
        assert "SUPERPASS" not in sanitized
        assert "https://[@acc]:[@pw]@host/path" in sanitized

    def test_sanitize_error_strips_multiple_urls_in_one_message(self):
        message = "primary https://a.example/x?token=SECRET1 failed, retrying https://b.example/y?token=SECRET2"
        sanitized = wnacg._sanitize_error(message)
        assert "SECRET1" not in sanitized
        assert "SECRET2" not in sanitized

    def test_sanitize_error_strips_token_in_fragment(self):
        message = "failed at https://host/path#token=FRAGSECRET"
        sanitized = wnacg._sanitize_error(message)
        assert "FRAGSECRET" not in sanitized

    # ── D4: case-insensitive scheme + loosened /path?query lookbehind ──

    def test_sanitize_error_redacts_uppercase_scheme(self):
        """`_ABSOLUTE_URL_RE` used to be case-sensitive — `HTTPS://` passed
        straight through unredacted.

        R3-2: the ORIGINAL fixture here (`HTTPS://host/a?token=...`) could
        not detect an `re.IGNORECASE` regression, because its `?query` gets
        stripped by the separately-loosened `_PATH_QUERY_RE` `:` lookbehind
        regardless of the scheme's case (`//host/a?token=...` follows a `:`,
        which that regex matches on its own). This fixture has NO `?query` —
        a userinfo credential is the only thing that can hide the secret,
        and only `_ABSOLUTE_URL_RE` (gated on `re.IGNORECASE`) ever reaches
        it, so deleting the flag makes this fail for the reason it names."""
        message = "retry failed HTTPS://user:UPPERSECRET@host/a"
        sanitized = wnacg._sanitize_error(message)
        assert "UPPERSECRET" not in sanitized
        assert "HTTPS://[@acc]:[@pw]@host/a" in sanitized  # host must survive redaction

    def test_sanitize_error_redacts_path_query_after_colon_no_space(self):
        """`(?<!\\S)` alone rejected a `/path?query` immediately after `:`
        with no preceding whitespace — the exact shape urllib3 sometimes
        produces (`...url:/dl/abc?token=...`)."""
        message = "url:/dl/abc?token=LOOKBEHINDSECRET"
        sanitized = wnacg._sanitize_error(message)
        assert "LOOKBEHINDSECRET" not in sanitized
        assert "url:/dl/abc" in sanitized  # path must survive, query only

    def test_sanitize_error_redacts_path_query_after_open_paren(self):
        message = "Max retries exceeded (/dl/abc?token=PARENPATHSECRET)"
        sanitized = wnacg._sanitize_error(message)
        assert "PARENPATHSECRET" not in sanitized
        # path must survive (the trailing ")" is separately swallowed by the
        # regex's own char class — R3-3, unchanged, non-blocking, out of
        # scope for this round — so this only pins the path text itself).
        assert "Max retries exceeded (/dl/abc" in sanitized

    def test_sanitize_error_path_query_regex_does_not_mangle_ordinary_prose(self):
        """Loosening the lookbehind must not make a slash preceded by an
        ORDINARY (non-trigger) character match — proves the loosening did
        not turn into a blanket match-any-slash-with-a-question-mark."""
        message = "see a/b?c=d for details"
        assert wnacg._sanitize_error(message) == message

    # ── D5: `_strip_userinfo` broke when the userinfo contained `/` ──

    def test_strip_url_query_handles_userinfo_containing_unencoded_slash(self):
        """`urlsplit`'s netloc parsing stops at the first `/`, so a userinfo
        with an unencoded slash used to make the whole credential — and the
        real host — pass through `_strip_url_query` completely unchanged.

        Under the owner's 2026-09-02 rule, an unencoded `/` inside the
        password truncates the RFC 3986 authority to `user:PASS` (the real
        `@host` is now past that boundary, in `remainder`). The non-port-
        shaped-colon fallback in `_redact_authority` still recognizes `PASS`
        as a credential and replaces it — this is the owner's OWN worked
        example, verbatim (`user:PASS/WORD@host...` -> `user:[@pw]/WORD@host...`):
        the text after the erroneous `/` is RFC path, not further redacted."""
        result = wnacg._strip_url_query("https://user:PASS/WORD@host/path")
        assert result == "https://user:[@pw]/WORD@host/path"
        assert "PASS" not in result
        assert "host/path" in result

    def test_strip_url_query_handles_userinfo_with_slash_and_embedded_at(self):
        """A DIFFERENT, more compound malformation than the row above: the
        password contains BOTH an unencoded '/' AND an unencoded '@' before
        the real host (`P@SS/WD@host`). The RFC-strict authority here is
        `user:P@SS` — which DOES contain an '@' (the credible/normal branch
        fires, not the fallback), so the last '@' inside it splits userinfo
        `user:P` from what `_redact_authority` treats as "host" (`SS`); the
        rest of the string (`/WD@host/path`) is RFC path and untouched.

        NOTE this is NOT the same shape as R4-2's reported case
        (`user:PW@host/down/AB@CD.zip`, no embedded slash in the password) —
        that one IS fully resolved by the RFC-scoped rule, see
        `test_archive_download_failure_with_userinfo_redacts_credential_and_keeps_at_filename`.
        This is the genuinely unresolved compound: review 4 proved its OWN
        candidate rule could not fix this exact shape without breaking a D5
        case, and this design does not either — neither `SS` nor `WD` is a
        real host or filename here (a synthetic unit-level string, not an
        end-to-end URL), so nothing REAL is destroyed, but this specific
        compound shape does not fully hide every character of the original
        malformed password. Recorded plainly, not silently — see the
        fix-round-4 report."""
        result = wnacg._strip_url_query("https://user:P@SS/WD@host/path?x=1")
        assert result == "https://[@acc]:[@pw]@SS/WD@host/path"
        assert "[@acc]" in result and "[@pw]" in result

    # ── R3-1: `_redact_authority`'s "last @ anywhere is the userinfo
    # boundary" rule over-corrected D5 — it fabricated a wrong host and
    # destroyed the real host AND the real filename whenever the URL PATH
    # itself contained an `@` (a site-supplied filename like `AB@CD.zip` is
    # legal: `_sanitize_archive_filename`'s blacklist does not exclude `@`).
    # A test that only asserts "the secret is gone" cannot detect this — it
    # must assert what has to SURVIVE. ──

    def test_strip_url_query_preserves_host_and_filename_when_at_is_in_the_path(self):
        """The reviewer's core R3-1 reproduction at the unit level: an `@`
        inside the path (no real userinfo at all) must leave the URL
        completely untouched — both the real host and the real filename
        must be present in the output, not just "no secret leaked"."""
        result = wnacg._strip_url_query("https://cdn.x/down/1/AB@CD.zip")
        assert result == "https://cdn.x/down/1/AB@CD.zip"
        assert "cdn.x" in result  # real host must survive
        assert "AB@CD.zip" in result  # real filename must survive

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            # D5 cases — userinfo IS credible: placeholder-substituted, host
            # survives (owner's rule, 2026-09-02 — no longer full deletion).
            ("https://user:PASSSECRET@host.example/dl/a.zip", "https://[@acc]:[@pw]@host.example/dl/a.zip"),
            ("https://USERSECRET@host.example/dl/a.zip", "https://[@acc]@host.example/dl/a.zip"),
            ("https://user:PA@SSSECRET@host.example/dl/a.zip", "https://[@acc]:[@pw]@host.example/dl/a.zip"),
            ("https://user:PASS/WORDSECRET@host.example/dl/a.zip", "https://user:[@pw]/WORDSECRET@host.example/dl/a.zip"),
            # path-`@` cases — no real userinfo; must stay completely intact.
            ("https://cdn.wcdn.date/down/1/AB@CD.zip", "https://cdn.wcdn.date/down/1/AB@CD.zip"),
            ("https://cdn.wcdn.date/down/1/@abc.zip", "https://cdn.wcdn.date/down/1/@abc.zip"),
            ("https://cdn.wcdn.date/down/user@1/MYARCHIVE.zip", "https://cdn.wcdn.date/down/user@1/MYARCHIVE.zip"),
            ("https://host.example/dl/a.zip;admin@evil.example", "https://host.example/dl/a.zip;admin@evil.example"),
            ("https://host.example/a:b/c@d.zip", "https://host.example/a:b/c@d.zip"),
            # controls — no `@` at all.
            ("https://host.example/dl/a.zip", "https://host.example/dl/a.zip"),
            ("https://host.example/dl/nested/path/a.zip", "https://host.example/dl/nested/path/a.zip"),
            # ── R4-1 / R4-2 rows (review 4): a port, an IPv6 literal, and a
            # userinfo + path-`@` combination — the exact three shapes the
            # 12-row table used to have NO coverage for. All three must
            # survive host+port+path+filename intact; the userinfo+path-`@`
            # row must ALSO have its credential placeholder-replaced. ──
            ("https://dl.example:8443/down/1/AB@CD.zip", "https://dl.example:8443/down/1/AB@CD.zip"),
            ("https://dl.example:443/down/1/AB@CD.zip", "https://dl.example:443/down/1/AB@CD.zip"),
            ("https://[2001:db8::1]:8443/down/1/AB@CD.zip", "https://[2001:db8::1]:8443/down/1/AB@CD.zip"),
            ("https://user:PWSECRET@host.example/down/AB@CD.zip", "https://[@acc]:[@pw]@host.example/down/AB@CD.zip"),
            ("https://user:PWSECRET@dl.example:8443/down/a.zip", "https://[@acc]:[@pw]@dl.example:8443/down/a.zip"),
            ("https://user:PWSECRET@[::1]:8080/down/a.zip", "https://[@acc]:[@pw]@[::1]:8080/down/a.zip"),
            # bare IPv6 host, no port, no userinfo -- exercises the bracket
            # exclusion itself: without it, the fallback's colon-scan would
            # find a colon INSIDE the address (not a port separator) and
            # wrongly mangle the literal.
            ("https://[::1]/down/1/AB@CD.zip", "https://[::1]/down/1/AB@CD.zip"),
        ],
    )
    def test_redact_authority_boundary_table(self, url: str, expected: str):
        """R3-1's original 12-case boundary table (owner's 2026-09-02 rule
        updated the D5 rows' expected values from full deletion to
        placeholder substitution — same secrets, different remedy), PLUS
        6 rows added by review 4 / the fix-round-4 dispatch (R4-1: port,
        `:443`, IPv6 literal; R4-2: userinfo + path-`@`; two port/IPv6 +
        userinfo combinations) — the exact shapes the table previously had
        zero coverage for, which is precisely where R4-1 and R4-2 lived."""
        assert wnacg._strip_url_query(url) == expected

    def test_redact_authority_drops_empty_userinfo_entirely(self):
        """A bare `@` with nothing before it (`https://@host/path`) carries
        no username or password VALUE — there is nothing to hide, so
        `[@acc]` would fabricate a credential that never existed. Documented
        decision (not inferred): the empty userinfo AND its `@` are BOTH
        dropped, leaving just the host — never a stray leading `@`."""
        result = wnacg._strip_url_query("https://@host.example/down/a.zip")
        assert result == "https://host.example/down/a.zip"
        assert "@" not in result


class TestDownloadWnacgSanitizesFailureMessages:
    def test_archive_download_failure_never_leaks_the_signed_token(self, tmp_path: Path, monkeypatch):
        """End-to-end: the archive GET raises an HTTPError whose own str()
        embeds the presigned download URL (with its signed token) verbatim —
        exactly what `requests`' `raise_for_status()` produces. The stored
        `error` string must never contain that token."""
        signed_url = "https://dl1.wn01.download/down/123/abc.zip?token=SUPERSECRETTOKEN"
        download_index_signed = DOWNLOAD_INDEX_HTML.replace(
            '<a href="//dl1.wn01.download/down/123/abc.zip"><span>備用線路 (Server 2)</span></a>',
            f'<a href="{signed_url}"><span>備用線路 (Server 2)</span></a>',
        )
        # no CONFIG block, so the worker API is never called — the fallback
        # Server-2 link (the signed URL) is used directly.
        download_index_signed_no_config = download_index_signed.replace(
            'const CONFIG = {\n  WORKER_API: "https://d1.wcdn.date/api/generate-link",\n  FILE_KEY: "abc123",\n  FILE_NAME: "我的合集.zip"\n};',
            "",
        )
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=download_index_signed_no_config),
                _FakeResponse(raise_exc=requests.exceptions.HTTPError(f"404 Client Error: Not Found for url: {signed_url}")),
            ],
            post_responses=[],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "檔案下載失敗" in error
        assert "SUPERSECRETTOKEN" not in error
        assert "token=" not in error

    def test_archive_download_failure_never_leaks_a_redirected_urls_token(self, tmp_path: Path, monkeypatch):
        """Defect 1a, exercised end-to-end exactly as the reviewer reproduced it:
        Server-2's link 302s to a CDN mirror carrying its OWN signed token.
        `requests.exceptions.HTTPError.__str__()` embeds `response.url` — the
        FINAL, post-redirect URL — never the `download_link` string
        `download_wnacg` passed to `.get()`. So the caller-supplied
        `urls=(download_link,)` allowlist can never name this URL; the stored
        error must still never contain the redirected URL's token."""
        original_link = "https://dl1.wn01.download/down/123/abc.zip?token=ORIGINALSECRET"
        redirected_url = "https://cdn-mirror.example.com/abc.zip?token=REDIRECTEDSECRET&exp=1"
        download_index_signed = DOWNLOAD_INDEX_HTML.replace(
            '<a href="//dl1.wn01.download/down/123/abc.zip"><span>備用線路 (Server 2)</span></a>',
            f'<a href="{original_link}"><span>備用線路 (Server 2)</span></a>',
        )
        # no CONFIG block, so the worker API is never called — the fallback
        # Server-2 link (`original_link`) is used directly for the archive GET.
        download_index_signed_no_config = download_index_signed.replace(
            'const CONFIG = {\n  WORKER_API: "https://d1.wcdn.date/api/generate-link",\n  FILE_KEY: "abc123",\n  FILE_NAME: "我的合集.zip"\n};',
            "",
        )
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=download_index_signed_no_config),
                _FakeResponse(
                    raise_exc=requests.exceptions.HTTPError(
                        f"403 Client Error: Forbidden for url: {redirected_url}"
                    )
                ),
            ],
            post_responses=[],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "檔案下載失敗" in error
        assert "REDIRECTEDSECRET" not in error
        assert "ORIGINALSECRET" not in error
        assert "token=" not in error

    def test_download_write_failure_never_leaks_the_local_archive_path(self, tmp_path: Path, monkeypatch):
        """D1: the download `try` block's own `archive_path.open("wb")` can
        raise `OSError` (disk full, permission, read-only dir, long path) —
        exactly the shape the reviewer reproduced: `OSError(28, "No space
        left on device", str(archive_path))`. The stored `error` string must
        reduce the embedded local absolute path to its basename only, the
        same treatment the extraction site 14 lines below already gets.

        Assert on `tmp_path.name` (the generated temp-dir SEGMENT, e.g.
        `tmpx1ex1oit`), never on `str(tmp_path)` verbatim: `OSError.__str__()`
        formats its `filename` argument via `%r`, which on Windows doubles
        every backslash in the message text, so a plain-string check against
        the single-backslash `str(tmp_path)` would be `True` (i.e. "not
        leaked") whether or not the path was actually redacted — proven by
        running this exact assertion shape against the unmodified upstream
        `_sanitize_error` and finding it passes vacuously either way. A
        path-separator-free segment name has no such escaping ambiguity."""
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=DOWNLOAD_INDEX_HTML),
                _FakeResponse(content=b"data", headers={"content-length": "4"}),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": "https://example.com/file.zip"})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        def _raise_oserror(self, *args, **kwargs):
            raise OSError(28, "No space left on device", str(self))

        monkeypatch.setattr(Path, "open", _raise_oserror)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "檔案下載失敗" in error
        assert tmp_path.name not in error
        assert "我的合集.zip" in error  # basename must remain for diagnosis
        # R4-6: the download_dir SEGMENT name ("1_Test Title" — gallery_id
        # "1" from GALLERY_HTML's aid, title "Test Title" from its <title>)
        # must not survive either — it only would if `paths=` at the real
        # call site were reversed to (download_dir, archive_path), which
        # leaves a stale "<dirname>\<filename>" fragment instead of the
        # clean basename (see `_sanitize_error`'s own docstring). This
        # assertion is what makes this end-to-end test sensitive to that
        # reversal — review 4 measured that without it, the whole 61-test
        # suite passed even with both real call sites reversed.
        assert "1_Test Title" not in error

    def test_sanitize_error_paths_order_file_before_directory_produces_clean_basename(self):
        """R4-6: `_sanitize_error`'s `paths=` docstring states the file must
        be listed BEFORE its directory, but nothing guarded that ordering —
        review 4 measured that reversing the tuple at BOTH real call sites
        in `download_wnacg()` still left the whole 61-test suite green.

        Pins the mechanism directly, at the unit level, by comparing the
        CORRECT order against the reversed one and asserting they differ:
        the correct order collapses the message to the clean basename only;
        the reversed order leaves a stale `<dirname>\\<filename>` fragment
        (the directory got replaced with its own name FIRST, so the later
        full-path replacement for `archive_path` can no longer find an
        exact match — see the docstring for the mechanism)."""
        download_dir = Path("C:/dl/1_Test Title")
        archive_path = download_dir / "我的合集.zip"
        message = f"disk error: {archive_path}"

        correct_order = wnacg._sanitize_error(message, paths=(archive_path, download_dir))
        assert correct_order == "disk error: 我的合集.zip"

        reversed_order = wnacg._sanitize_error(message, paths=(download_dir, archive_path))
        assert reversed_order != correct_order
        assert "1_Test Title" in reversed_order  # the stale directory fragment survives

    def test_extraction_failure_never_leaks_the_local_archive_path(self, tmp_path: Path, monkeypatch):
        """End-to-end: a fake `zipfile.ZipFile` raises with the local absolute
        archive path embedded in its own str() — the stored `error` string
        must reduce it to the basename only."""
        zip_bytes = b"not actually a zip file"
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=DOWNLOAD_INDEX_HTML),
                _FakeResponse(content=zip_bytes, headers={"content-length": str(len(zip_bytes))}),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": "https://example.com/file.zip"})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        def _raise_with_path(path, mode):
            raise RuntimeError(f"cannot open archive: {path}")

        monkeypatch.setattr(wnacg.zipfile, "ZipFile", _raise_with_path)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "解壓縮失敗" in error
        assert str(tmp_path) not in error
        assert "我的合集.zip" in error

    def test_archive_download_failure_preserves_host_and_at_containing_filename(self, tmp_path: Path, monkeypatch):
        """R3-1 end-to-end, through the real `download_wnacg()`: a site-
        supplied `FILE_NAME` containing `@` (legal — `_sanitize_archive_
        filename`'s blacklist does not exclude `@`) used to make
        `_redact_authority` take that `@` as the userinfo/host boundary,
        fabricating a wrong host (`https://CD.zip`) and destroying both the
        real host and the real filename. Both must now survive."""
        signed_download_url = "https://dl2.example/down/1/AB@CD.zip"
        download_index_at_filename = DOWNLOAD_INDEX_HTML.replace('FILE_NAME: "我的合集.zip"', 'FILE_NAME: "AB@CD.zip"')
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=download_index_at_filename),
                _FakeResponse(raise_exc=requests.exceptions.HTTPError(f"404 Client Error: Not Found for url: {signed_download_url}")),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": signed_download_url})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "檔案下載失敗" in error
        assert "dl2.example" in error  # real host must survive
        assert "AB@CD.zip" in error  # real filename must survive
        assert "https://CD.zip" not in error  # no fabricated host

    def test_archive_download_failure_with_port_preserves_host_port_and_at_filename(self, tmp_path: Path, monkeypatch):
        """R4-1 end-to-end: an explicit port in the authority used to
        re-enable the R3-1 regression (`pre.find(":")` found the PORT colon,
        not a user:pass separator, so the path `@` was wrongly accepted as a
        userinfo boundary). Under the RFC-scoped rule, a port never has an
        `@` in the authority at all, so nothing is touched — host, port,
        path and the `@`-containing filename all survive, and no `[@acc]`/
        `[@pw]` placeholder appears (there was never a credential here)."""
        signed_download_url = "https://dl2.example:8443/down/1/AB@CD.zip"
        download_index_at_filename = DOWNLOAD_INDEX_HTML.replace('FILE_NAME: "我的合集.zip"', 'FILE_NAME: "AB@CD.zip"')
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=download_index_at_filename),
                _FakeResponse(raise_exc=requests.exceptions.HTTPError(f"404 Client Error: Not Found for url: {signed_download_url}")),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": signed_download_url})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "檔案下載失敗" in error
        assert "dl2.example:8443" in error  # real host AND port must survive
        assert "AB@CD.zip" in error  # real filename must survive
        assert "https://CD.zip" not in error  # no fabricated host
        assert "[@acc]" not in error and "[@pw]" not in error  # no credential ever existed here

    def test_archive_download_failure_with_userinfo_redacts_credential_and_keeps_at_filename(self, tmp_path: Path, monkeypatch):
        """R4-2 end-to-end: a GENUINE userinfo followed later by an `@` in
        the filename (`user:PWSECRET@dl2.example/down/1/AB@CD.zip`). The
        RFC-strict authority ends at the FIRST `/` after `dl2.example` — so
        the filename's `@` sits safely in `remainder`, never inspected, and
        this shape is fully resolved: unlike the OLD "scan the whole string
        for the last `@`" heuristics (R3-1/R4-1's `rfind`), the new
        authority-scoped rule finds the userinfo's own `@` (the FIRST one)
        without ever reaching the second. Credential replaced, host AND
        filename both survive intact — this is the genuine fix for R4-2's
        reported shape (the review-4-proven-unresolvable case is a
        DIFFERENT, more compound shape — an unencoded '/' INSIDE the
        password itself, pinned separately by
        `test_strip_url_query_handles_userinfo_with_slash_and_embedded_at`)."""
        signed_download_url = "https://user:PWSECRET@dl2.example/down/1/AB@CD.zip"
        download_index_at_filename = DOWNLOAD_INDEX_HTML.replace('FILE_NAME: "我的合集.zip"', 'FILE_NAME: "AB@CD.zip"')
        fake_scraper = _FakeScraper(
            get_responses=[
                _FakeResponse(text=GALLERY_HTML),
                _FakeResponse(text=download_index_at_filename),
                _FakeResponse(raise_exc=requests.exceptions.HTTPError(f"404 Client Error: Not Found for url: {signed_download_url}")),
            ],
            post_responses=[_FakeResponse(json_data={"success": True, "url": signed_download_url})],
        )
        monkeypatch.setattr(wnacg.cloudscraper, "create_scraper", lambda: fake_scraper)

        status, error = wnacg.download_wnacg("https://www.wnacg.com/photos-index-aid-1.html", tmp_path)

        assert status == "failed"
        assert "檔案下載失敗" in error
        assert "PWSECRET" not in error  # credential must be gone
        assert "[@acc]" in error and "[@pw]" in error  # placeholder markers present
        assert "dl2.example" in error  # real host must survive
        assert "AB@CD.zip" in error  # real filename must survive
        assert "https://CD.zip" not in error  # no fabricated host
