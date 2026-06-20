"""
tests/test_download_service.py

覆蓋 download_service.classify_provider：
驗證 URL 分流邏輯（gallery-dl / yt-dlp）。
"""
from __future__ import annotations

import pytest

from app.services.download_service import classify_provider
from app.domain.enums import Provider


class TestClassifyProvider:
    # ── gallery-dl 網域 ──────────────────────────────────

    def test_pixiv_is_gallery_dl(self):
        assert classify_provider("https://www.pixiv.net/artworks/12345678") == Provider.GALLERY_DL

    def test_nhentai_is_gallery_dl(self):
        assert classify_provider("https://nhentai.net/g/123456/") == Provider.GALLERY_DL

    def test_wnacg_is_gallery_dl(self):
        assert classify_provider("https://www.wnacg.com/photos-index-aid-12345.html") == Provider.GALLERY_DL

    def test_danbooru_is_gallery_dl(self):
        assert classify_provider("https://danbooru.donmai.us/posts/1234567") == Provider.GALLERY_DL

    def test_yandere_is_gallery_dl(self):
        assert classify_provider("https://yande.re/post/show/12345") == Provider.GALLERY_DL

    def test_fanbox_is_gallery_dl(self):
        assert classify_provider("https://artist.fanbox.cc/posts/12345") == Provider.GALLERY_DL

    # ── yt-dlp 網域 ──────────────────────────────────────

    def test_youtube_is_ytdlp(self):
        assert classify_provider("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == Provider.YTDLP

    def test_youtu_be_is_ytdlp(self):
        assert classify_provider("https://youtu.be/dQw4w9WgXcQ") == Provider.YTDLP

    # ── 多 provider 網域（預設回傳第一個候選）────────────

    def test_twitter_defaults_to_gallery_dl(self):
        # provider_candidates 對 multi-provider 回傳 [GALLERY_DL, YTDLP]
        # classify_provider 取 [0]
        result = classify_provider("https://x.com/user/status/123456")
        assert result == Provider.GALLERY_DL

    def test_facebook_defaults_to_gallery_dl(self):
        result = classify_provider("https://www.facebook.com/video/12345")
        assert result == Provider.GALLERY_DL

    # ── ytdlp:// 強制 ────────────────────────────────────

    def test_ytdlp_scheme_forces_ytdlp(self):
        assert classify_provider("ytdlp://https://www.youtube.com/watch?v=abc") == Provider.YTDLP

    def test_ytdlp_scheme_on_gallery_domain(self):
        # ytdlp:// 即使用 gallery-dl 的網域也強制走 yt-dlp
        assert classify_provider("ytdlp://https://www.pixiv.net/artworks/123") == Provider.YTDLP

    # ── 未知網域 ─────────────────────────────────────────

    def test_unknown_domain_defaults_to_gallery_dl(self):
        result = classify_provider("https://unknown-site.example.com/image.jpg")
        assert result == Provider.GALLERY_DL
