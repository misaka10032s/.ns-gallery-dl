"""
tests/test_direct_file_ssrf.py

app/providers/direct_file/provider.py::download() — SSRF hardening
(待回答 #48). Never touches the real network: `socket.getaddrinfo` is
monkeypatched for every DNS-relevant address, and the actual HTTP fetch goes
through a fake `urllib.request.OpenerDirector.open` so no real request is
ever made.
"""
from __future__ import annotations

import ipaddress
import socket
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from app.domain.enums import JobStatus
from app.providers.direct_file import provider as direct_file_provider


def _fake_getaddrinfo(addr: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))]


def _dns_side_effect(safe_ip: str):
    """A `socket.getaddrinfo` side_effect that resolves a LITERAL IP host to
    itself (so a redirect Location like `http://127.0.0.1:7601/...` is
    correctly judged unsafe on its own address) and every named host to
    `safe_ip` — a single static `return_value` would make EVERY hostname
    (including a redirect target that is itself a literal loopback IP)
    resolve to the same fake public address, hiding exactly the bug this
    test suite exists to catch."""

    def _resolve(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return _fake_getaddrinfo(safe_ip)
        return _fake_getaddrinfo(host)

    return _resolve


class _FakeResponse(BytesIO):
    """Minimal stand-in for what `urlopen()`/`opener.open()` returns: needs
    `.headers.get()` and to survive `contextlib.closing()`."""

    def __init__(self, body: bytes = b"file-bytes", content_type: str = "application/octet-stream"):
        super().__init__(body)
        self.headers = {"Content-Type": content_type}
        # dict has no case-insensitive .get with a default distinct from
        # missing-key, but Content-Type is the only header this code path
        # reads — a plain dict is enough here.


class TestInitialUrlValidation:
    def test_literal_private_ip_rejected_without_any_request(self, tmp_path):
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch.object(direct_file_provider._REDIRECT_GUARDED_OPENER, "open") as mock_open,
        ):
            result = direct_file_provider.download("http://10.0.0.5/secret")
        mock_open.assert_not_called()
        assert result.status == JobStatus.FAILED
        assert "private or reserved" in result.error

    def test_dns_resolved_metadata_endpoint_rejected(self, tmp_path):
        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("169.254.169.254")),
        ):
            result = direct_file_provider.download("https://metadata.example.com/latest")
        assert result.status == JobStatus.FAILED
        assert "private or reserved" in result.error


class TestRedirectChain:
    def test_redirect_to_loopback_is_rejected(self, tmp_path):
        """hop 1 (the initial URL) resolves publicly and 302s to
        http://127.0.0.1:7601/ — that hop must be rejected before it is ever
        requested, even though the FIRST url passed is_safe_url()."""

        def fake_open(request, timeout=None):
            url = request.full_url
            if url == "https://safe.example.com/start":
                error = HTTPError(url, 302, "Found", {"Location": "http://127.0.0.1:7601/api/jobs"}, None)
                raise error
            raise AssertionError(f"should never request the redirect target, got {url}")

        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("socket.getaddrinfo", side_effect=_dns_side_effect("93.184.216.34")),
            patch.object(direct_file_provider._REDIRECT_GUARDED_OPENER, "open", side_effect=fake_open),
        ):
            result = direct_file_provider.download("https://safe.example.com/start")

        assert result.status == JobStatus.FAILED
        assert "private or reserved" in result.error

    def test_six_hop_redirect_chain_rejected(self, tmp_path):
        call_count = {"n": 0}

        def fake_open(request, timeout=None):
            call_count["n"] += 1
            n = call_count["n"]
            url = request.full_url
            # 6 redirects (hop 0..5 all redirect) exceeds MAX_REDIRECT_HOPS (5).
            raise HTTPError(url, 302, "Found", {"Location": f"https://safe.example.com/hop{n}"}, None)

        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("socket.getaddrinfo", side_effect=_dns_side_effect("93.184.216.34")),
            patch.object(direct_file_provider._REDIRECT_GUARDED_OPENER, "open", side_effect=fake_open),
        ):
            result = direct_file_provider.download("https://safe.example.com/start")

        assert result.status == JobStatus.FAILED
        assert "Too many redirects" in result.error
        # MAX_REDIRECT_HOPS + 1 total attempts before giving up.
        assert call_count["n"] == direct_file_provider.MAX_REDIRECT_HOPS + 1

    def test_redirect_to_another_safe_host_succeeds(self, tmp_path):
        def fake_open(request, timeout=None):
            url = request.full_url
            if url == "https://safe.example.com/start":
                raise HTTPError(url, 302, "Found", {"Location": "https://cdn.example.com/final.bin"}, None)
            assert url == "https://cdn.example.com/final.bin"
            return _FakeResponse(b"payload")

        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("socket.getaddrinfo", side_effect=_dns_side_effect("93.184.216.34")),
            patch.object(direct_file_provider._REDIRECT_GUARDED_OPENER, "open", side_effect=fake_open),
        ):
            result = direct_file_provider.download("https://safe.example.com/start")

        assert result.status == JobStatus.SUCCESS


class TestHappyPathStillWorks:
    def test_direct_download_without_redirect_succeeds(self, tmp_path):
        def fake_open(request, timeout=None):
            assert request.full_url == "https://safe.example.com/file.bin"
            return _FakeResponse(b"hello world")

        with (
            patch("app.services.path_service.DOWNLOAD_DIR", tmp_path),
            patch("socket.getaddrinfo", side_effect=_dns_side_effect("93.184.216.34")),
            patch.object(direct_file_provider._REDIRECT_GUARDED_OPENER, "open", side_effect=fake_open),
        ):
            result = direct_file_provider.download("https://safe.example.com/file.bin")

        assert result.status == JobStatus.SUCCESS
        assert result.download_path
        from pathlib import Path

        assert Path(result.download_path).read_bytes() == b"hello world"
