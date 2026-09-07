"""
tests/test_origin_guard.py

app/api/origin_guard.py — the global before_request Origin/Host guard
(待回答 #47). Two layers of coverage:

1. Unit tests against `resolve_allowed_origins()` / `_host_header_matches()`
   directly (no Flask app needed) — the allow-list construction, env-var
   extra origins, and the wildcard-drop rule.
2. A Flask test-client end-to-end pass against a REAL write route
   (`POST /api/jobs`, chosen because it previously had NO same-origin check
   at all — see app/api/origin_guard.py's module docstring) proving the
   guard actually applies globally, not just to the two routes that already
   had `_check_same_origin`.

Every `.post()`/`.put()`/`.delete()` call below passes
`base_url="http://127.0.0.1:7601"` — Werkzeug's test client defaults its
`Host` header to bare `localhost` (no port) otherwise, which the Host check
would itself reject before ever reaching the Origin check. Fixture-level
only; no assertion depends on this beyond "the legitimate request is not
blocked by Host".
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.api import origin_guard

_BASE_URL = "http://127.0.0.1:7601"
_VALID_EXT_ID = "abcdefghijklmnopabcdefghijklmnop"  # 32 chars, alphabet a-p


# ──────────────────────────────────────────────────────────
# resolve_allowed_origins() / _host_header_matches()
# ──────────────────────────────────────────────────────────


class TestResolveAllowedOrigins:
    def test_includes_configured_api_port_loopback_variants(self, monkeypatch):
        monkeypatch.delenv("NS_MEDIA_HUB_EXTRA_ORIGINS", raising=False)
        with patch.object(origin_guard, "API_PORT", 7601):
            origins = origin_guard.resolve_allowed_origins()
        assert "http://127.0.0.1:7601" in origins
        assert "http://localhost:7601" in origins
        assert "http://[::1]:7601" in origins

    def test_includes_vite_dev_port(self, monkeypatch):
        monkeypatch.delenv("NS_MEDIA_HUB_EXTRA_ORIGINS", raising=False)
        origins = origin_guard.resolve_allowed_origins()
        assert "http://127.0.0.1:5173" in origins
        assert "http://localhost:5173" in origins

    def test_env_extra_origin_is_accepted(self, monkeypatch):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "http://127.0.0.1:6100")
        origins = origin_guard.resolve_allowed_origins()
        assert "http://127.0.0.1:6100" in origins

    def test_env_wildcard_origin_is_dropped(self, monkeypatch, capsys):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "http://*.example.com")
        origins = origin_guard.resolve_allowed_origins()
        assert not any("*" in origin for origin in origins)
        assert "WARNING" in capsys.readouterr().out

    def test_env_malformed_origin_is_dropped(self, monkeypatch, capsys):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "not-a-url, ftp://bad.example, http://ok.example/with/path")
        origins = origin_guard.resolve_allowed_origins()
        assert not any("ok.example" in origin for origin in origins)
        assert "WARNING" in capsys.readouterr().out

    def test_env_concrete_chrome_extension_origin_is_accepted(self, monkeypatch):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", f"chrome-extension://{_VALID_EXT_ID}")
        origins = origin_guard.resolve_allowed_origins()
        assert f"chrome-extension://{_VALID_EXT_ID}" in origins

    def test_env_chrome_extension_wildcard_star_is_dropped(self, monkeypatch, capsys):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "chrome-extension://*")
        origins = origin_guard.resolve_allowed_origins()
        assert not any(origin.startswith("chrome-extension://") for origin in origins)
        assert "WARNING" in capsys.readouterr().out

    def test_env_chrome_extension_no_id_is_dropped(self, monkeypatch, capsys):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "chrome-extension://")
        origins = origin_guard.resolve_allowed_origins()
        assert not any(origin.startswith("chrome-extension://") for origin in origins)
        assert "WARNING" in capsys.readouterr().out

    def test_env_chrome_extension_uppercase_id_is_dropped(self, monkeypatch, capsys):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "chrome-extension://ABCDEFGHIJKLMNOPABCDEFGHIJKLMNOP")
        origins = origin_guard.resolve_allowed_origins()
        assert not any(origin.startswith("chrome-extension://") for origin in origins)
        assert "WARNING" in capsys.readouterr().out

    def test_env_chrome_extension_wrong_length_id_is_dropped(self, monkeypatch, capsys):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "chrome-extension://abc")
        origins = origin_guard.resolve_allowed_origins()
        assert not any(origin.startswith("chrome-extension://") for origin in origins)
        assert "WARNING" in capsys.readouterr().out

    def test_env_chrome_extension_with_path_is_dropped(self, monkeypatch, capsys):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", f"chrome-extension://{_VALID_EXT_ID}/path")
        origins = origin_guard.resolve_allowed_origins()
        assert not any(origin.startswith("chrome-extension://") for origin in origins)
        assert "WARNING" in capsys.readouterr().out


class TestHostHeaderMatches:
    def test_exact_loopback_port_matches(self):
        with patch.object(origin_guard, "API_PORT", 7601):
            assert origin_guard._host_header_matches("127.0.0.1:7601") is True
            assert origin_guard._host_header_matches("localhost:7601") is True
            assert origin_guard._host_header_matches("[::1]:7601") is True

    def test_wrong_port_rejected(self):
        with patch.object(origin_guard, "API_PORT", 7601):
            assert origin_guard._host_header_matches("127.0.0.1:9999") is False

    def test_missing_port_compares_against_scheme_default_and_fails(self):
        # No port in the header -> urlsplit's default (80) -> fails unless
        # API_PORT is itself 80. Never silently skipped.
        with patch.object(origin_guard, "API_PORT", 7601):
            assert origin_guard._host_header_matches("127.0.0.1") is False

    def test_non_loopback_host_rejected(self):
        with patch.object(origin_guard, "API_PORT", 7601):
            assert origin_guard._host_header_matches("evil.example.com:7601") is False


# ──────────────────────────────────────────────────────────
# End-to-end: POST /api/jobs (previously had NO same-origin check at all)
# ──────────────────────────────────────────────────────────


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


class TestJobsRouteGuardedGlobally:
    def test_good_origin_passes(self, client):
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls", return_value=1):
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": "http://127.0.0.1:7601"},
            )
        assert response.status_code == 202

    def test_foreign_origin_blocked(self, client):
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit:
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": "https://evil.example.com"},
            )
        mock_submit.assert_not_called()
        assert response.status_code == 403
        assert "error" in response.get_json()

    def test_null_origin_blocked(self, client):
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit:
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": "null"},
            )
        mock_submit.assert_not_called()
        assert response.status_code == 403

    def test_wrong_port_host_blocked(self, client):
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit:
            response = client.post(
                "/api/jobs",
                base_url="http://127.0.0.1:9999",
                json={"links": ["https://example.com/a"]},
            )
        mock_submit.assert_not_called()
        assert response.status_code == 403

    def test_host_with_no_port_blocked(self, client):
        # Werkzeug's default test-client Host header (no explicit base_url)
        # is bare "localhost" — no port — which must fail the Host check
        # rather than being treated as "port absent, skip the check".
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit:
            response = client.post("/api/jobs", json={"links": ["https://example.com/a"]})
        mock_submit.assert_not_called()
        assert response.status_code == 403

    def test_no_origin_no_referer_with_good_host_passes(self, client):
        # A local CLI tool (curl) sends no Origin at all — the Host check
        # alone is the full guard for this path, by design.
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls", return_value=1):
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
            )
        assert response.status_code == 202

    def test_get_with_foreign_origin_is_not_blocked(self, client):
        with patch("app.api.routes.jobs.jobs_repo.list_recent", return_value=[]):
            response = client.get(
                "/api/jobs",
                base_url=_BASE_URL,
                headers={"Origin": "https://evil.example.com"},
            )
        assert response.status_code == 200

    def test_options_is_unaffected(self, client):
        response = client.options("/api/jobs", base_url=_BASE_URL, headers={"Origin": "https://evil.example.com"})
        # Flask's default OPTIONS handler answers automatically; the guard
        # must never turn this into a 403.
        assert response.status_code != 403

    def test_env_added_origin_is_accepted_end_to_end(self, client, monkeypatch):
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "http://127.0.0.1:6100")
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls", return_value=1):
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": "http://127.0.0.1:6100"},
            )
        assert response.status_code == 202

    def test_env_chrome_extension_origin_is_accepted_end_to_end(self, client, monkeypatch):
        # 待回答 #47 review F1: this repo's own Chrome extension sends
        # `Origin: chrome-extension://<id>` on POST /api/jobs; a concrete id
        # added via NS_MEDIA_HUB_EXTRA_ORIGINS must reach the route.
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", f"chrome-extension://{_VALID_EXT_ID}")
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls", return_value=1):
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": f"chrome-extension://{_VALID_EXT_ID}"},
            )
        assert response.status_code == 202

    def test_chrome_extension_wildcard_star_still_blocked_end_to_end(self, client, monkeypatch):
        # Even with a wildcard configured (which is dropped, never accepted),
        # an arbitrary other extension's Origin must still 403.
        monkeypatch.setenv("NS_MEDIA_HUB_EXTRA_ORIGINS", "chrome-extension://*")
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit:
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": f"chrome-extension://{_VALID_EXT_ID}"},
            )
        mock_submit.assert_not_called()
        assert response.status_code == 403

    def test_chrome_extension_no_id_still_blocked_end_to_end(self, client):
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit:
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": "chrome-extension://"},
            )
        mock_submit.assert_not_called()
        assert response.status_code == 403

    def test_chrome_extension_uppercase_id_still_blocked_end_to_end(self, client):
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit:
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": "chrome-extension://ABCDEFGHIJKLMNOPABCDEFGHIJKLMNOP"},
            )
        mock_submit.assert_not_called()
        assert response.status_code == 403

    def test_chrome_extension_with_path_still_blocked_end_to_end(self, client):
        with patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit:
            response = client.post(
                "/api/jobs",
                base_url=_BASE_URL,
                json={"links": ["https://example.com/a"]},
                headers={"Origin": f"chrome-extension://{_VALID_EXT_ID}/path"},
            )
        mock_submit.assert_not_called()
        assert response.status_code == 403

    def test_rejected_origin_warning_logged_once_for_two_identical_requests(self, client, caplog):
        # 待回答 #47 review F1b: the same rejected Origin value must produce
        # exactly ONE WARNING log record across two identical requests, not
        # one per request (which would flood the log for a browser retrying
        # the same blocked call).
        origin_guard._rejected_origins_logged.clear()
        distinct_origin = "https://evil-dedupe-test.example"
        with (
            patch("app.api.routes.jobs.browser_bridge_service.submit_urls") as mock_submit,
            caplog.at_level("WARNING", logger="app.api.origin_guard"),
        ):
            for _ in range(2):
                response = client.post(
                    "/api/jobs",
                    base_url=_BASE_URL,
                    json={"links": ["https://example.com/a"]},
                    headers={"Origin": distinct_origin},
                )
                assert response.status_code == 403
        mock_submit.assert_not_called()
        matching = [r for r in caplog.records if distinct_origin in r.getMessage()]
        assert len(matching) == 1
        assert matching[0].levelname == "WARNING"
        assert "NS_MEDIA_HUB_EXTRA_ORIGINS=" + distinct_origin in matching[0].getMessage()
