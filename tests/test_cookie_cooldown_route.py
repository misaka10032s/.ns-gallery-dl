"""
tests/test_cookie_cooldown_route.py

DELETE /api/cookies/<domain>/cooldown — the manual override endpoint from
dispatch B2 (fix round 2): lets the owner end a domain's auth-failure
cooldown right now, without touching its cookie jar, when they believe the
site's own block already lifted.

- Same-origin CSRF guard reused from misc.py (403 on a foreign Origin),
  matching every other cookie-mutation endpoint in this file.
- 200 + cleared=True when a cooldown existed and was removed.
- 200 + cleared=False (idempotent, never an error) when there was none.

Heavy dependencies (DB init, cookie scan, queue worker thread) are mocked at
app bootstrap — this only exercises the route's own logic, matching
tests/test_downloaders_route.py's pattern for the same reason.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def client():
    with (
        patch("app.api.app.init_db"),
        patch("app.api.app.scan_cookie_files"),
        patch("app.api.app.queue_service.start_worker"),
    ):
        from app.api.app import create_app

        app = create_app()
        app.testing = True
        with app.test_client() as test_client:
            yield test_client


class TestClearCookieCooldownRoute:
    def test_clears_an_existing_cooldown(self, client):
        with patch("app.api.routes.misc.auth_cooldown.clear_cooldown", return_value=True) as mock_clear:
            response = client.delete("/api/cookies/x.com/cooldown")

        mock_clear.assert_called_once_with("x.com")
        assert response.status_code == 200
        body = response.get_json()
        assert body["cleared"] is True

    def test_no_op_when_no_cooldown_existed_is_still_200(self, client):
        with patch("app.api.routes.misc.auth_cooldown.clear_cooldown", return_value=False):
            response = client.delete("/api/cookies/x.com/cooldown")

        assert response.status_code == 200
        assert response.get_json()["cleared"] is False

    def test_blocks_foreign_origin(self, client):
        with patch("app.api.routes.misc.auth_cooldown.clear_cooldown") as mock_clear:
            response = client.delete(
                "/api/cookies/x.com/cooldown",
                headers={"Origin": "https://evil.example.com"},
            )

        mock_clear.assert_not_called()
        assert response.status_code == 403
