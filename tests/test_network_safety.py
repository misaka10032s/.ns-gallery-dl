"""
tests/test_network_safety.py

app/domain/network_safety.py::is_safe_url — the shared SSRF-safe URL
validator (待回答 #48). Never touches the real network: `socket.getaddrinfo`
is monkeypatched everywhere DNS resolution matters.
"""
from __future__ import annotations

import socket
from unittest.mock import patch

from app.domain.network_safety import is_safe_url


def _fake_getaddrinfo(*addresses: str):
    """Builds a `socket.getaddrinfo`-shaped return value resolving to each
    of `addresses` (mirrors the real 5-tuple shape; only `sockaddr[0]`, the
    element `is_safe_url` reads, is realistic)."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0)) for addr in addresses]


class TestSchemeAndShape:
    def test_rejects_non_http_scheme(self):
        safe, reason = is_safe_url("ftp://example.com/file")
        assert safe is False
        assert reason

    def test_rejects_missing_host(self):
        safe, _reason = is_safe_url("http:///no-host")
        assert safe is False

    def test_rejects_malformed_url(self):
        safe, _reason = is_safe_url("http://[::1/broken")
        assert safe is False

    def test_rejects_embedded_userinfo(self):
        safe, reason = is_safe_url("http://user:pass@example.com/x")
        assert safe is False
        assert "userinfo" in reason.lower()


class TestDomainBypassAttempts:
    """The bug this module replaces: a bare substring check
    ("private.example" not in url) was trivially bypassed by putting the
    disallowed text somewhere that doesn't matter — is_safe_url has NO
    domain allow-list at all, so these are really just 'does it resolve
    publicly' checks, but they document the exact bypass shapes #48 named."""

    def test_query_string_lookalike_does_not_matter_only_real_host_does(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("8.8.8.8")):
            safe, _ = is_safe_url("https://example.com/?u=169.254.169.254")
        assert safe is True

    def test_subdomain_lookalike_is_judged_by_its_own_resolution(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("169.254.169.254")):
            safe, reason = is_safe_url("https://169.254.169.254.evil.example/")
        assert safe is False
        assert "private or reserved" in reason


class TestLiteralIpHosts:
    def test_literal_public_ip_allowed(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("93.184.216.34")):
            safe, _ = is_safe_url("http://93.184.216.34/file.zip")
        assert safe is True

    def test_literal_loopback_ip_rejected(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("127.0.0.1")):
            safe, reason = is_safe_url("http://127.0.0.1/admin")
        assert safe is False
        assert "private or reserved" in reason


class TestDnsResolvedUnsafeAddresses:
    """Mocked DNS resolution to each address the dispatch brief named."""

    def test_resolves_to_private_10_rejected(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("10.0.0.5")):
            safe, reason = is_safe_url("https://internal.example.com/x")
        assert safe is False
        assert "private or reserved" in reason

    def test_resolves_to_loopback_rejected(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("127.0.0.1")):
            safe, _reason = is_safe_url("https://sneaky.example.com/x")
        assert safe is False

    def test_resolves_to_link_local_metadata_endpoint_rejected(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("169.254.169.254")):
            safe, _reason = is_safe_url("https://metadata.example.com/x")
        assert safe is False

    def test_resolves_to_ipv6_loopback_rejected(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("::1")):
            safe, _reason = is_safe_url("https://sneaky6.example.com/x")
        assert safe is False

    def test_resolves_to_shared_cgnat_space_rejected(self):
        # 100.64.0.0/10 (RFC 6598): NOT ipaddress.is_private on this Python
        # version, but correctly `not is_global` — the exact gap `not
        # ip.is_global` exists to close on top of the named checks.
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("100.64.0.1")):
            safe, _reason = is_safe_url("https://cgnat.example.com/x")
        assert safe is False

    def test_multi_record_host_unsafe_on_any_resolved_address(self):
        # A public FIRST address must not shadow an unsafe LATER one — the
        # original _is_safe_url only ever checked getaddrinfo(...)[0].
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("8.8.8.8", "127.0.0.1")):
            safe, _reason = is_safe_url("https://multi.example.com/x")
        assert safe is False

    def test_dns_resolution_failure_rejected_not_crashed(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("nope")):
            safe, reason = is_safe_url("https://does-not-resolve.invalid/x")
        assert safe is False
        assert "resolve" in reason.lower()

    def test_overlong_label_hostname_rejected_not_crashed(self):
        # 待回答 #47 review F2: `socket.getaddrinfo` raises `UnicodeError` (a
        # `ValueError` subclass, NOT `socket.gaierror`) for a hostname whose
        # IDNA-encoded label exceeds the DNS length limit — this used to
        # escape the narrower `except socket.gaierror` and propagate as an
        # uncaught exception. Real (unmocked) getaddrinfo call: the failure
        # happens during IDNA encoding, before any actual network I/O.
        overlong_host = "a" * 64 + ".com"
        safe, reason = is_safe_url(f"https://{overlong_host}/x")
        assert safe is False
        assert reason
        assert "resolve" in reason.lower()


class TestHappyPath:
    def test_public_domain_allowed(self):
        with patch("socket.getaddrinfo", return_value=_fake_getaddrinfo("93.184.216.34")):
            safe, reason = is_safe_url("https://example.com/file.zip")
        assert safe is True
        assert reason == ""


class TestFetchStatusRouteDoesNotCrashOnOverlongHostname:
    """待回答 #47 review F2: before the fix, this exact request 500'd
    (`UnicodeError` escaping `_is_safe_url`) instead of returning the
    intended 400 'unsafe URL' response."""

    def test_fetch_status_returns_400_not_500(self):
        with (
            patch("app.api.app.init_db"),
            patch("app.api.app.scan_cookie_files"),
            patch("app.api.app.queue_service.start_worker"),
        ):
            from app.api.app import create_app

            app = create_app()
            app.testing = True
            with app.test_client() as client:
                overlong_host = "a" * 64 + ".com"
                response = client.post(
                    "/api/fetch_status",
                    base_url="http://127.0.0.1:7601",
                    json={"url": f"https://{overlong_host}/x"},
                )
        assert response.status_code == 400
        assert "error" in response.get_json()
