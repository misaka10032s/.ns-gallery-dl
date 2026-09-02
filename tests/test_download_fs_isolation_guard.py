"""
tests/test_download_fs_isolation_guard.py

review-3.md B1 (fix-round-3, 2026-09-02): app.services.gallery_service,
app.services.path_service and app.services.doujin_service each bind their
own module-level DOWNLOAD_DIR at import time
(`from app.config.paths import DOWNLOAD_DIR`) — three separate names, none
of which the (pre-fix-round-3) autouse fixture touched. path_service.
category_root() / discord_root() both call `root.mkdir(parents=True,
exist_ok=True)` — so any test that reaches them without the opt-in
tmp_download_dir/tmp_doujin_download_dir fixture would create real
directories under the owner's live download/ tree.
"""
from __future__ import annotations

import re

import pytest

from app.services import doujin_service, gallery_service, path_service
from tests.conftest import _REAL_DOWNLOAD_DIR, assert_fs_paths_isolated


class TestLandsInTmpPathWithoutAnyOptInFixture:
    """No test here requests tmp_download_dir / tmp_doujin_download_dir —
    proving the autouse fixture's DEFAULT isolation covers all three
    DOWNLOAD_DIR-bound consumer modules on its own."""

    def test_category_root_mkdir_never_creates_a_directory_under_the_real_download_tree(self):
        root = path_service.category_root("pixiv.net")
        assert _REAL_DOWNLOAD_DIR.resolve() not in root.resolve().parents
        assert root.exists()  # category_root() itself calls mkdir()

    def test_discord_root_mkdir_never_creates_a_directory_under_the_real_download_tree(self):
        root = path_service.discord_root("some-guild-id", "attachments")
        assert _REAL_DOWNLOAD_DIR.resolve() not in root.resolve().parents
        assert root.exists()

    def test_gallery_service_download_dir_binding_is_isolated(self):
        assert gallery_service.DOWNLOAD_DIR.resolve() != _REAL_DOWNLOAD_DIR.resolve()

    def test_doujin_service_download_dir_binding_is_isolated(self):
        assert doujin_service.DOWNLOAD_DIR.resolve() != _REAL_DOWNLOAD_DIR.resolve()

    def test_all_three_download_dir_bindings_agree_with_each_other_by_default(self):
        # They don't HAVE to be the identical directory to each be safe, but
        # the autouse fixture's default does point all three at the same
        # tmp dir — pinned here so a future accidental split (three
        # different, all-safe-but-inconsistent tmp dirs) is visible as a
        # deliberate change, not a silent one.
        assert gallery_service.DOWNLOAD_DIR == path_service.DOWNLOAD_DIR == doujin_service.DOWNLOAD_DIR


class TestGuardFiresOnRealPaths:
    def test_assert_fs_paths_isolated_raises_when_path_service_download_dir_is_real(self):
        with pytest.raises(RuntimeError, match=re.escape("path_service.DOWNLOAD_DIR")):
            assert_fs_paths_isolated(
                {"path_service.DOWNLOAD_DIR": (_REAL_DOWNLOAD_DIR, _REAL_DOWNLOAD_DIR)}
            )

    def test_assert_fs_paths_isolated_stays_green_for_a_properly_isolated_pair(self, tmp_path):
        assert (
            assert_fs_paths_isolated(
                {"gallery_service.DOWNLOAD_DIR": (tmp_path / "download", _REAL_DOWNLOAD_DIR)}
            )
            is None
        )


class TestWidenedGuardFiresRegardlessOfFixtureUse:
    def test_category_root_mkdir_guard_fires_when_path_service_download_dir_is_repointed_at_real(
        self, monkeypatch
    ):
        # Deliberately UNDOES the autouse fixture's isolation for this one
        # consumer, after it already ran for this test — proving the
        # structural Path.mkdir guard catches it independently.
        monkeypatch.setattr(path_service, "DOWNLOAD_DIR", _REAL_DOWNLOAD_DIR)
        with pytest.raises(RuntimeError, match="production"):
            path_service.category_root("pixiv.net")

    def test_direct_path_mkdir_under_the_real_download_dir_is_blocked(self):
        with pytest.raises(RuntimeError, match="production"):
            (_REAL_DOWNLOAD_DIR / "some-new-category").mkdir(parents=True, exist_ok=True)
