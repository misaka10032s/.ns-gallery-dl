"""
tests/test_cookie_service.py

覆蓋 cookie_service 的安全關鍵路徑：
- sanitize_component（path_service）：路徑汙染字元過濾
- _cookie_file_path：目錄逸出防護
- _normalize_cookie_text：格式驗證
"""
from __future__ import annotations

import pytest

from app.services.path_service import sanitize_component


# ──────────────────────────────────────────────────────────
# sanitize_component（path_service 安全函式）
# ──────────────────────────────────────────────────────────


class TestSanitizeComponent:
    """sanitize_component 負責過濾非法檔名字元，是多處路徑組合的安全閘門。"""

    def test_normal_string_unchanged(self):
        assert sanitize_component("pixiv") == "pixiv"

    def test_dots_stripped_from_edges(self):
        # 前後 . 必須被去除（避免隱藏檔/目錄）
        result = sanitize_component("..secret..")
        assert not result.startswith(".")
        assert not result.endswith(".")

    def test_slash_replaced(self):
        result = sanitize_component("path/traversal")
        assert "/" not in result

    def test_backslash_replaced(self):
        result = sanitize_component("path\\traversal")
        assert "\\" not in result

    def test_dotdot_replaced(self):
        # ".." 本身在去除邊緣 . 後只剩空字串或 fallback
        result = sanitize_component("..")
        assert result not in ("..", ".")
        assert "/" not in result and "\\" not in result

    def test_colon_replaced(self):
        result = sanitize_component("C:windows")
        assert ":" not in result

    def test_null_byte_replaced(self):
        result = sanitize_component("evil\x00name")
        assert "\x00" not in result

    def test_empty_string_uses_fallback(self):
        assert sanitize_component("", fallback="unknown") == "unknown"

    def test_only_special_chars_uses_fallback(self):
        result = sanitize_component("//\\\\", fallback="default")
        assert result == "default"

    def test_truncation_at_120(self):
        long_name = "a" * 200
        result = sanitize_component(long_name)
        assert len(result) <= 120


# ──────────────────────────────────────────────────────────
# _cookie_file_path 目錄逸出防護
# ──────────────────────────────────────────────────────────


class TestCookieFilePath:
    """_cookie_file_path 不得允許任何可能逸出 COOKIE_DIR 的輸入。"""

    def test_valid_domain_within_dir(self, tmp_cookie_dir):
        from unittest.mock import patch
        with patch("app.services.cookie_service.COOKIE_DIR", tmp_cookie_dir):
            from app.services.cookie_service import _cookie_file_path
            path = _cookie_file_path("pixiv.net")
            assert str(path).startswith(str(tmp_cookie_dir))

    def test_dotdot_domain_raises(self, tmp_cookie_dir):
        from unittest.mock import patch
        with patch("app.services.cookie_service.COOKIE_DIR", tmp_cookie_dir):
            from app.services.cookie_service import _cookie_file_path
            # 即使傳入含 .. 的 domain，sanitize 後路徑仍須在目錄內
            # 若 sanitize 後還是逸出，應 raise ValueError
            try:
                path = _cookie_file_path("../../etc/passwd")
                # 若不 raise，路徑必須仍在 COOKIE_DIR 內
                assert str(path.resolve()).startswith(str(tmp_cookie_dir.resolve()))
            except ValueError:
                pass  # 正確行為：直接拒絕


# ──────────────────────────────────────────────────────────
# _normalize_cookie_text 格式驗證
# ──────────────────────────────────────────────────────────


class TestNormalizeCookieText:
    def _call(self, domain, value):
        from app.services.cookie_service import _normalize_cookie_text
        return _normalize_cookie_text(domain, value)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="required"):
            self._call("pixiv.net", "")

    def test_netscape_passthrough(self):
        netscape = "# Netscape HTTP Cookie File\n.pixiv.net\tTRUE\t/\tTRUE\t0\tname\tvalue\n"
        result = self._call("pixiv.net", netscape)
        assert result.startswith("# Netscape HTTP Cookie File")

    def test_cookie_header_converted(self):
        result = self._call("pixiv.net", "session=abc123; token=xyz")
        assert "# Netscape HTTP Cookie File" in result
        assert "session" in result
        assert "abc123" in result

    def test_cookie_prefix_stripped(self):
        result = self._call("pixiv.net", "Cookie: session=hello")
        assert "hello" in result

    def test_whitespace_only_raises(self):
        """空白字串等同空值，應 raise ValueError。"""
        with pytest.raises(ValueError, match="required"):
            self._call("pixiv.net", "   ")
