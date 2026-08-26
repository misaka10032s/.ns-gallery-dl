"""
tests/test_path_service.py

覆蓋 app.services.path_service.storage_category / CATEGORY_ALIASES ——
2026-08-26 新增的兩筆別名（threads.com -> threads, bilibili.com -> bilibili），
使用者原話：「threads.com/bilibili.com = threads/bilibili」，之前沒有這兩筆
別名，兩站的下載會落在原始 domain 資料夾而不是乾淨的分類名稱。
"""
from __future__ import annotations

from app.services import path_service


class TestNewAliases:
    def test_threads_com_maps_to_threads(self):
        assert path_service.storage_category("threads.com") == "threads"

    def test_bilibili_com_maps_to_bilibili(self):
        assert path_service.storage_category("bilibili.com") == "bilibili"


class TestExistingAliasesUnaffected:
    """新增兩筆別名不能動到既有對映——用既有幾筆當回歸樣本。"""

    def test_nhentai_net_still_maps_to_nhentai(self):
        assert path_service.storage_category("nhentai.net") == "nhentai"

    def test_pixiv_net_still_maps_to_pixiv(self):
        assert path_service.storage_category("pixiv.net") == "pixiv"

    def test_x_com_still_maps_to_x(self):
        assert path_service.storage_category("x.com") == "x"

    def test_unaliased_domain_falls_back_to_sanitized_domain(self):
        assert path_service.storage_category("some-other-site.example") == "some-other-site.example"
