"""
tests/test_tmp_db_isolation_guard.py

覆蓋 tests/conftest.py 的 assert_db_paths_isolated() —— 證明這道防線真的能
失敗（rubric R2：一個從沒示範過失敗的 gate 不算 gate），不只是一個看起來合理
但從未真正擋下任何東西的檢查。

2026-09-01 事故：tmp_db 只 patch 了 DATA_DIR / DB_FILE，漏掉
app.storage.db 自己另外綁定的 LEGACY_HISTORY_FILE，導致每一個使用 tmp_db 的
測試在 main tree（真的存在 data/history.json 時）都會把正式的下載歷史悄悄
灌進「乾淨」的暫存 db。這個檔案把「指回正式檔案就要大聲失敗」這件事釘死成
迴歸測試，不只是修好那一次。
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.storage import db as db_module
from tests.conftest import (
    _REAL_DB_FILE,
    _REAL_LEGACY_HISTORY_FILE,
    assert_db_paths_isolated,
)


class TestGuardFiresOnRealPaths:
    def test_guard_raises_when_db_file_points_at_the_real_production_db(self, tmp_path):
        # Every OTHER path stays properly isolated (tmp_path-based); only
        # DB_FILE is deliberately mis-set back to the real production file —
        # isolates which single mismatch the guard is catching.
        with patch.object(db_module, "DATA_DIR", tmp_path), \
             patch.object(db_module, "LEGACY_HISTORY_FILE", tmp_path / "unused.json"), \
             patch.object(db_module, "DB_FILE", _REAL_DB_FILE):
            with pytest.raises(RuntimeError, match="DB_FILE"):
                assert_db_paths_isolated(db_module)

    def test_guard_raises_when_legacy_history_file_points_at_the_real_file(self, tmp_path):
        """This is the exact 2026-09-01 defect shape: DATA_DIR/DB_FILE stay
        isolated while LEGACY_HISTORY_FILE quietly still points at the real
        file — the guard must catch that specific mismatch too, not just a
        DATA_DIR/DB_FILE one."""
        with patch.object(db_module, "DATA_DIR", tmp_path), \
             patch.object(db_module, "DB_FILE", tmp_path / "test_app.db"), \
             patch.object(db_module, "LEGACY_HISTORY_FILE", _REAL_LEGACY_HISTORY_FILE):
            with pytest.raises(RuntimeError, match="LEGACY_HISTORY_FILE"):
                assert_db_paths_isolated(db_module)


class TestGuardStaysGreenWhenIsolated:
    def test_guard_passes_for_a_properly_isolated_tmp_db(self, tmp_db):
        # tmp_db already ran this guard once on entry without raising;
        # calling it again here pins that a correctly isolated fixture never
        # trips the guard, AND that none of its three patched paths equal the
        # real production ones — the actual property under test, not just
        # "did not raise".
        assert assert_db_paths_isolated(db_module) is None
        assert db_module.DB_FILE.resolve() != _REAL_DB_FILE.resolve()
        assert db_module.LEGACY_HISTORY_FILE.resolve() != _REAL_LEGACY_HISTORY_FILE.resolve()
