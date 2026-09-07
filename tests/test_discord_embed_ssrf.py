"""
tests/test_discord_embed_ssrf.py

app/services/discord_service.py::_download_embed_image — SSRF hardening
(待回答 #48). Never touches the real network: `socket.getaddrinfo` is
monkeypatched, and `aiohttp.ClientSession` is replaced with a fake that
never opens a socket. Uses `asyncio.run()` directly (this repo's existing
async-test pattern — see tests/test_discord_backfill.py; no pytest-asyncio
plugin is installed).

Requires `tmp_db` (from tests/conftest.py) so `jobs_repo.create_job()` /
`update_job()` — called internally by `_download_embed_image` — have a real,
isolated, initialized SQLite file to write to instead of failing with
"no such table: jobs".
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from unittest.mock import patch

from app.services import discord_service as ds


def _fake_getaddrinfo(addr: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))]


def _dns_side_effect(safe_ip: str):
    """Same host-aware DNS fake as tests/test_direct_file_ssrf.py — a
    literal-IP redirect target must resolve to ITSELF, not to whatever
    `safe_ip` the named test host resolves to."""

    def _resolve(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return _fake_getaddrinfo(safe_ip)
        return _fake_getaddrinfo(host)

    return _resolve


class _FakeContent:
    def __init__(self, body: bytes):
        self._body = body

    async def iter_chunked(self, size: int):
        yield self._body


class _FakeAiohttpResponse:
    def __init__(self, status: int, headers: dict | None = None, body: bytes = b""):
        self.status = status
        self.headers = headers or {}
        self.content = _FakeContent(body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


class _FakeSession:
    def __init__(self, get_side_effect):
        self._get_side_effect = get_side_effect

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def get(self, url, allow_redirects=True):
        return self._get_side_effect(url, allow_redirects)


def _run_download_embed_image(get_side_effect, safe_ip: str, url: str, tmp_path, tmp_db):
    fake_session = _FakeSession(get_side_effect)
    with (
        patch("app.services.discord_service.aiohttp.ClientSession", return_value=fake_session),
        patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
        patch("app.services.discord_service.discord_root", side_effect=lambda guild, kind=None: tmp_path),
        patch("socket.getaddrinfo", side_effect=_dns_side_effect(safe_ip)),
    ):
        return asyncio.run(ds._download_embed_image(url, "test-guild"))


class TestInitialUrlValidation:
    def test_literal_private_ip_rejected_without_any_request(self, tmp_path, tmp_db):
        def get_side_effect(url, allow_redirects):
            raise AssertionError("must never request an unsafe URL")

        ok = _run_download_embed_image(get_side_effect, "93.184.216.34", "http://10.0.0.5/evil.png", tmp_path, tmp_db)
        assert ok is False


class TestRedirectChain:
    def test_redirect_to_loopback_is_rejected(self, tmp_path, tmp_db):
        def get_side_effect(url, allow_redirects):
            assert allow_redirects is False
            if url == "https://safe.example.com/embed.jpg":
                return _FakeAiohttpResponse(302, headers={"Location": "http://127.0.0.1:7601/api/jobs"})
            raise AssertionError(f"should never request the redirect target, got {url}")

        ok = _run_download_embed_image(
            get_side_effect, "93.184.216.34", "https://safe.example.com/embed.jpg", tmp_path, tmp_db
        )
        assert ok is False

    def test_six_hop_redirect_chain_rejected(self, tmp_path, tmp_db):
        call_count = {"n": 0}

        def get_side_effect(url, allow_redirects):
            call_count["n"] += 1
            n = call_count["n"]
            return _FakeAiohttpResponse(302, headers={"Location": f"https://safe.example.com/hop{n}"})

        ok = _run_download_embed_image(
            get_side_effect, "93.184.216.34", "https://safe.example.com/start.jpg", tmp_path, tmp_db
        )
        assert ok is False
        assert call_count["n"] == ds.MAX_REDIRECT_HOPS + 1

    def test_redirect_to_another_safe_host_succeeds(self, tmp_path, tmp_db):
        def get_side_effect(url, allow_redirects):
            if url == "https://safe.example.com/embed.jpg":
                return _FakeAiohttpResponse(302, headers={"Location": "https://cdn.example.com/final.jpg"})
            assert url == "https://cdn.example.com/final.jpg"
            return _FakeAiohttpResponse(200, body=b"image-bytes")

        ok = _run_download_embed_image(
            get_side_effect, "93.184.216.34", "https://safe.example.com/embed.jpg", tmp_path, tmp_db
        )
        assert ok is True


class TestHappyPathStillWorks:
    def test_direct_embed_download_succeeds(self, tmp_path, tmp_db):
        def get_side_effect(url, allow_redirects):
            assert url == "https://safe.example.com/embed.jpg"
            return _FakeAiohttpResponse(200, body=b"image-bytes")

        ok = _run_download_embed_image(
            get_side_effect, "93.184.216.34", "https://safe.example.com/embed.jpg", tmp_path, tmp_db
        )
        assert ok is True
