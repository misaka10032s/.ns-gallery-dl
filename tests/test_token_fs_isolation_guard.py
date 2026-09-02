"""
tests/test_token_fs_isolation_guard.py

review-3.md B1 (fix-round-3, 2026-09-02): app.services.token_service binds
its own module-level DATA_DIR + TOKENS_FILE at import time
(`from app.config.paths import DATA_DIR, TOKENS_FILE`) — a separate name
from the ones the (pre-fix-round-3) autouse fixture patched, so
load_tokens()/save_tokens() resolved to the owner's real
`data/tokens.json` in ANY test that called them without a dedicated opt-in
fixture (none existed for this consumer at all). save_tokens() calls
`DATA_DIR.mkdir(parents=True, exist_ok=True)` then
`TOKENS_FILE.write_text(...)` — a full overwrite of the owner's live OAuth
token file, no confirmation, no backup.

Same fix shape as tests/test_tmp_db_isolation_guard.py /
tests/test_cookie_fs_isolation_guard.py.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from app.services import token_service
from tests.conftest import _REAL_DATA_DIR, _REAL_TOKENS_FILE, assert_fs_paths_isolated


def _real_tokens_file_fingerprint():
    """Size + mtime only — never the file's own content. This repo's
    absolute safety rules ban ever reading a token VALUE, even to compare
    it; NAME/SIZE/mtime are the only reportable/comparable facts, so that
    is all these tests ever touch on the real file."""
    if not _REAL_TOKENS_FILE.exists():
        return None
    st = os.stat(_REAL_TOKENS_FILE)
    return st.st_size, st.st_mtime


class TestLandsInTmpPathWithoutAnyOptInFixture:
    def test_save_tokens_never_writes_the_real_tokens_file(self):
        token_service.save_tokens({"probe": "fs-guard"})

        assert token_service.TOKENS_FILE.resolve() != _REAL_TOKENS_FILE.resolve()
        assert token_service.DATA_DIR.resolve() != _REAL_DATA_DIR.resolve()
        assert token_service.TOKENS_FILE.exists()
        assert json.loads(token_service.TOKENS_FILE.read_text(encoding="utf-8")) == {
            "probe": "fs-guard"
        }

    def test_load_tokens_round_trips_through_the_isolated_file_only(self):
        before = _real_tokens_file_fingerprint()
        token_service.save_tokens({"a": "1"})
        assert token_service.load_tokens() == {"a": "1"}
        # The real file's size+mtime (never its content, per this repo's
        # absolute safety rules) are unchanged by this test.
        assert _real_tokens_file_fingerprint() == before


class TestGuardFiresOnRealPaths:
    def test_assert_fs_paths_isolated_raises_when_tokens_file_is_real(self):
        with pytest.raises(RuntimeError, match=re.escape("token_service.TOKENS_FILE")):
            assert_fs_paths_isolated(
                {"token_service.TOKENS_FILE": (_REAL_TOKENS_FILE, _REAL_TOKENS_FILE)}
            )

    def test_assert_fs_paths_isolated_raises_when_data_dir_is_real(self):
        with pytest.raises(RuntimeError, match=re.escape("token_service.DATA_DIR")):
            assert_fs_paths_isolated(
                {"token_service.DATA_DIR": (_REAL_DATA_DIR, _REAL_DATA_DIR)}
            )

    def test_assert_fs_paths_isolated_stays_green_for_a_properly_isolated_pair(self, tmp_path):
        assert (
            assert_fs_paths_isolated(
                {"token_service.TOKENS_FILE": (tmp_path / "tokens.json", _REAL_TOKENS_FILE)}
            )
            is None
        )


class TestWidenedGuardFiresRegardlessOfFixtureUse:
    def test_save_tokens_guard_fires_when_deliberately_repointed_at_the_real_file(
        self, monkeypatch
    ):
        # Deliberately UNDOES the autouse fixture's isolation for this one
        # consumer, after it already ran for this test — proving the
        # structural Path.mkdir guard (DATA_DIR.mkdir() runs before
        # TOKENS_FILE.write_text() in save_tokens()) catches it
        # independently, not merely because the fixture happened to keep
        # things isolated.
        #
        # review-4.md B3: TOKENS_FILE is deliberately repointed at a name
        # that does NOT exist under the real DATA_DIR
        # (_REAL_DATA_DIR / "guard-probe-tokens.json"), never at
        # _REAL_TOKENS_FILE itself. save_tokens() calls DATA_DIR.mkdir()
        # (guarded) BEFORE TOKENS_FILE.write_text() (NOT in the guard's verb
        # set — see tests/conftest.py's guard docstring), so the ONLY thing
        # that stopped a real overwrite before this fix was that incidental
        # line ordering in token_service.save_tokens() — a regression in
        # EITHER the mkdir guard or that ordering would have overwritten the
        # owner's live data/tokens.json with no backup. _path_under_guarded_
        # root() is a pure path-value check (works on a target that does not
        # exist), so the guard still fires identically on this probe path;
        # DATA_DIR itself is still _REAL_DATA_DIR, so the mkdir guard fires
        # exactly as before and this assertion's red-before-green property
        # is unchanged. The worst case if the guard ever fails now is a new,
        # empty, obviously-synthetic "guard-probe-tokens.json" file — never
        # the owner's real token file.
        before = _real_tokens_file_fingerprint()
        monkeypatch.setattr(token_service, "DATA_DIR", _REAL_DATA_DIR)
        monkeypatch.setattr(
            token_service, "TOKENS_FILE", _REAL_DATA_DIR / "guard-probe-tokens.json"
        )
        with pytest.raises(RuntimeError, match="production"):
            token_service.save_tokens({"malicious": "overwrite"})

        # And, separately: the real file is provably untouched (size+mtime
        # unchanged, never its content) — the guard fired BEFORE the write,
        # not after a partial one.
        assert _real_tokens_file_fingerprint() == before

    def test_direct_path_mkdir_under_the_real_data_dir_is_blocked(self):
        with pytest.raises(RuntimeError, match="production"):
            _REAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
