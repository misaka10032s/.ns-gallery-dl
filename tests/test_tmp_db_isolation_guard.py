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


class TestWidenedConnectGuardFiresRegardlessOfFixtureUse:
    """fix-round-2 (B2): assert_db_paths_isolated() alone only ever fired
    for a test that explicitly called it (i.e. only tmp_db users). The
    2026-09-02 incident was two NEW tests that never requested tmp_db at
    all, so that check never ran for them. The real, durable fix is
    tests/conftest.py's autouse `_isolate_every_test_from_the_real_database`
    fixture, which wraps app.storage.db._connect() (the single choke point
    every read/write goes through) for EVERY test unconditionally — this
    class proves that wrap actually fires, by deliberately re-pointing
    DB_FILE at the real production path AFTER the autouse fixture has
    already run for this test, and confirming the wrapped _connect() still
    refuses rather than silently opening the real file."""

    def test_probe_connect_guard_fires_on_real_db_file_when_deliberately_repointed(self, monkeypatch):
        # This test itself runs entirely inside the autouse isolation
        # fixture (it applies to every test, unconditionally) — so this
        # monkeypatch deliberately UNDOES that isolation for DB_FILE only,
        # to prove the connect-time wrap catches it independently, not
        # merely because the autouse fixture happened to keep it isolated.
        monkeypatch.setattr(db_module, "DB_FILE", _REAL_DB_FILE)
        with pytest.raises(RuntimeError, match="production database"):
            db_module._connect()
