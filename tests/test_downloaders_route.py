"""
tests/test_downloaders_route.py

POST /api/downloaders/update:
- Same-origin CSRF guard reused from misc.py (403 on a foreign Origin).
- 409 refusal while a job is actively running (Windows locks the running .exe).
- 200 + per-package old/new versions on the happy path.

Heavy dependencies (DB init, cookie scan, queue worker thread, the real updater)
are mocked — this only exercises the route's own logic.

FIXTURE NOTE (待回答 #47): every `.post()` below now passes
`base_url="http://127.0.0.1:7601"`. Werkzeug's test client defaults its `Host`
header to bare `localhost` (no port) when no `base_url` is given, which the
new global Origin/Host guard (app/api/origin_guard.py, registered in
create_app()) would otherwise reject on the Host check alone — a fixture-only
change to match the real bound address, zero assertions changed.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

_BASE_URL = "http://127.0.0.1:7601"


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


class TestUpdateDownloadersRoute:
    def test_happy_path_returns_per_package_versions(self, client):
        fake_results = [
            {"package": "yt-dlp", "old_version": "2024.01.01", "new_version": "2024.06.01", "changed": True},
            {"package": "gallery-dl", "old_version": "1.27.0", "new_version": "1.27.0", "changed": False},
        ]
        with (
            patch("app.api.routes.downloaders.queue_service.get_state", return_value={"current": None, "pending": [], "total": 0}),
            patch("app.api.routes.downloaders.updater_service.update_all_downloaders", return_value=fake_results),
        ):
            response = client.post("/api/downloaders/update", base_url=_BASE_URL)

        assert response.status_code == 200
        assert response.get_json() == {"results": fake_results}

    def test_refuses_409_while_queue_is_busy(self, client):
        with patch(
            "app.api.routes.downloaders.queue_service.get_state",
            return_value={"current": "https://example.com/1", "pending": [], "total": 1},
        ):
            response = client.post("/api/downloaders/update", base_url=_BASE_URL)

        assert response.status_code == 409
        assert "error" in response.get_json()

    def test_blocks_foreign_origin(self, client):
        with patch("app.api.routes.downloaders.queue_service.get_state", return_value={"current": None, "pending": [], "total": 0}):
            response = client.post(
                "/api/downloaders/update",
                base_url=_BASE_URL,
                headers={"Origin": "https://evil.example.com"},
            )

        assert response.status_code == 403
