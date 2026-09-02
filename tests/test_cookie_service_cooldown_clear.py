"""
tests/test_cookie_service_cooldown_clear.py

B2 fix (dispatch round 2): app.services.cookie_service.save_cookie() /
delete_cookie() must clear app.domain.auth_cooldown's cooldown row for the
affected domain — a re-seeded (or removed) cookie jar IS the fix an armed
cooldown was waiting for, so the owner should not also have to wait out
AUTH_COOLDOWN_SECONDS on top of re-seeding.

Uses BOTH `tmp_cookie_dir` (isolates the cookie jar filesystem) and `tmp_db`
(isolates the SQLite auth_cooldown table) so this never touches the real
data/app.db or cookies/ — see tests/conftest.py for both fixtures' docstrings.
"""
from __future__ import annotations

from app.domain import auth_cooldown
from app.services import cookie_service
from app.storage.repositories import auth_cooldown_repo


class TestSaveCookieClearsCooldown:
    def test_save_cookie_clears_an_existing_cooldown(self, tmp_cookie_dir, tmp_db):
        auth_cooldown.record_auth_failure("example.com", "AuthRequired: Protected Tweet")
        cooling_down_before, _ = auth_cooldown.in_cooldown("example.com")
        assert cooling_down_before is True

        cookie_service.save_cookie("example.com", "Cookie: a=1; b=2")

        cooling_down_after, until_after = auth_cooldown.in_cooldown("example.com")
        assert cooling_down_after is False
        assert until_after is None
        assert auth_cooldown_repo.get_state("example.com") is None

    def test_save_cookie_is_a_no_op_when_no_cooldown_existed(self, tmp_cookie_dir, tmp_db):
        # Must not raise / must not fabricate a cooldown row out of nothing.
        cookie_service.save_cookie("no-prior-failure.example", "Cookie: a=1")
        assert auth_cooldown_repo.get_state("no-prior-failure.example") is None

    def test_save_cookie_does_not_clear_a_DIFFERENT_domains_cooldown(self, tmp_cookie_dir, tmp_db):
        auth_cooldown.record_auth_failure("instagram.com", "AuthRequired")

        cookie_service.save_cookie("example.com", "Cookie: a=1")

        cooling_down, _ = auth_cooldown.in_cooldown("instagram.com")
        assert cooling_down is True

    def test_renaming_a_cookie_clears_both_the_old_and_new_domains_cooldown(self, tmp_cookie_dir, tmp_db):
        """save_cookie(domain, value, previous_domain=...) internally calls
        delete_cookie(previous) — that must clear the OLD domain's cooldown
        too (its jar is now gone), on top of the NEW domain's clear."""
        cookie_service.save_cookie("old.example", "Cookie: a=1")
        auth_cooldown.record_auth_failure("old.example", "AuthRequired")
        auth_cooldown.record_auth_failure("new.example", "AuthRequired")

        cookie_service.save_cookie("new.example", "Cookie: a=1", previous_domain="old.example")

        assert auth_cooldown_repo.get_state("old.example") is None
        assert auth_cooldown_repo.get_state("new.example") is None


class TestDeleteCookieClearsCooldown:
    def test_delete_cookie_clears_an_existing_cooldown(self, tmp_cookie_dir, tmp_db):
        cookie_service.save_cookie("example.com", "Cookie: a=1")
        auth_cooldown.record_auth_failure("example.com", "AuthRequired: Protected Tweet")

        cookie_service.delete_cookie("example.com")

        assert auth_cooldown_repo.get_state("example.com") is None

    def test_delete_cookie_missing_ok_noop_does_not_touch_cooldown_state(self, tmp_cookie_dir, tmp_db):
        """When nothing was actually deleted (missing_ok short-circuit), no
        cookie change happened — clearing here would be an unjustified side
        effect for a domain whose jar was never touched."""
        auth_cooldown.record_auth_failure("never-had-a-file.example", "AuthRequired")

        deleted = cookie_service.delete_cookie("never-had-a-file.example", missing_ok=True)

        assert deleted == 0
        cooling_down, _ = auth_cooldown.in_cooldown("never-had-a-file.example")
        assert cooling_down is True
