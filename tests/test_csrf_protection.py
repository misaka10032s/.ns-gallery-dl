"""
tests/test_csrf_protection.py

驗證 misc.py 的 same-origin 保護：
- 無 Origin/Referer → 允許（本機工具呼叫）
- Origin=127.0.0.1 → 允許
- Origin=evil.example.com → 拒絕 403
"""
from __future__ import annotations

import pytest

# 注意：_check_same_origin 是 module-level 函式，測試以 Flask test client 驗證端點行為
# 這裡直接測試 helper 函式本身（不需啟動完整 Flask app）


class TestCheckSameOrigin:
    def _get_fn(self):
        from app.api.routes.misc import _check_same_origin
        return _check_same_origin

    def test_no_headers_allowed(self):
        """無 Origin/Referer 的請求（如 curl）允許通過。"""
        from unittest.mock import patch, MagicMock
        mock_request = MagicMock()
        mock_request.headers.get = lambda k, d="": {"Origin": "", "Referer": ""}.get(k, d)
        with patch("app.api.routes.misc.request", mock_request):
            fn = self._get_fn()
            ok, _ = fn()
            assert ok is True

    def test_localhost_origin_allowed(self):
        from unittest.mock import patch, MagicMock
        mock_request = MagicMock()
        mock_request.headers.get = lambda k, d="": {
            "Origin": "http://127.0.0.1:7601",
            "Referer": "",
        }.get(k, d)
        with patch("app.api.routes.misc.request", mock_request):
            fn = self._get_fn()
            ok, _ = fn()
            assert ok is True

    def test_localhost_named_allowed(self):
        from unittest.mock import patch, MagicMock
        mock_request = MagicMock()
        mock_request.headers.get = lambda k, d="": {
            "Origin": "http://localhost:7601",
            "Referer": "",
        }.get(k, d)
        with patch("app.api.routes.misc.request", mock_request):
            fn = self._get_fn()
            ok, _ = fn()
            assert ok is True

    def test_external_origin_blocked(self):
        from unittest.mock import patch, MagicMock
        mock_request = MagicMock()
        mock_request.headers.get = lambda k, d="": {
            "Origin": "https://evil.example.com",
            "Referer": "",
        }.get(k, d)
        with patch("app.api.routes.misc.request", mock_request):
            fn = self._get_fn()
            ok, reason = fn()
            assert ok is False
            assert reason  # 錯誤訊息不應為空

    def test_external_referer_blocked(self):
        from unittest.mock import patch, MagicMock
        mock_request = MagicMock()
        mock_request.headers.get = lambda k, d="": {
            "Origin": "",
            "Referer": "https://attacker.example.com/csrf.html",
        }.get(k, d)
        with patch("app.api.routes.misc.request", mock_request):
            fn = self._get_fn()
            ok, reason = fn()
            assert ok is False

    def test_referer_from_localhost_allowed(self):
        from unittest.mock import patch, MagicMock
        mock_request = MagicMock()
        mock_request.headers.get = lambda k, d="": {
            "Origin": "",
            "Referer": "http://127.0.0.1:7601/cookies",
        }.get(k, d)
        with patch("app.api.routes.misc.request", mock_request):
            fn = self._get_fn()
            ok, _ = fn()
            assert ok is True
