"""Shared SSRF-safe URL validator (待回答 #48).

`app/api/routes/misc.py` already had a `_is_safe_url()` doing roughly this
job for `/api/fetch_status` (a debug "is this URL reachable" probe), but
nothing else in the app called it: `app/providers/direct_file/provider.py`
(the generic direct-file downloader — reachable with an arbitrary,
fully user-supplied URL via `POST /api/jobs` / `/api/history/requeue` with
`providerHint=direct-file`, or a `provider_mode=forced` retry) fetched via
bare `urllib.request.urlopen()` with NO validation at all, and
`app/services/discord_service.py`'s embed-image downloader fetched via bare
`aiohttp` with none either — both are genuine SSRF vectors: a caller who can
reach the Web UI (or craft a Discord embed) could point either at
`http://127.0.0.1:7601/...`, a cloud metadata endpoint
(`http://169.254.169.254/...`), or any other internal/reserved address and
have THIS SERVER make the request on their behalf.

This module is the ONE shared validator both of those call sites (and
`misc.py`'s own `_is_safe_url`) now use — `app.domain` sits below both
`app.services` and `app.providers` in the `pyproject.toml`
`[tool.importlinter]` layers contract, so both can legally import it without
adding a new cross-layer violation (see `app/domain/error_sanitizer.py`'s
docstring for the same reasoning, applied to a different shared helper).

Two responsibilities, deliberately kept together because a caller that
manually follows redirects needs both:

1. :func:`is_safe_url` — validate a SINGLE url. Rejects a non-http(s)
   scheme, embedded userinfo (``user:pass@host``), a missing host, and any
   host that resolves (via ``socket.getaddrinfo`` — literal IPs resolve to
   themselves, so this covers both) to a private / loopback / link-local /
   multicast / reserved / unspecified / otherwise-non-global address. EVERY
   address a hostname resolves to is checked (not just the first), since a
   multi-A-record host could otherwise pass on its first, public address
   while a later one points at an internal target.
2. :data:`MAX_REDIRECT_HOPS` — the shared "how many redirects a caller may
   manually follow" constant (owner ruling, 待回答 #48: "up to 5 hops").
   `is_safe_url()` only validates ONE url; it does not fetch or follow
   redirects itself — a caller that manually follows a redirect chain MUST
   call this again on every hop's ``Location`` target BEFORE requesting it,
   or an initially-safe URL could still 302 straight to a private address
   after the check already passed (the exact bug this module replaces).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Owner ruling (待回答 #48, 2026-09-07, verbatim): "轉址後每跳重驗 ... 上限 5
# 跳". A caller manually following redirects may issue at most this many
# ADDITIONAL requests beyond the first (so at most MAX_REDIRECT_HOPS + 1
# requests total before giving up).
MAX_REDIRECT_HOPS: int = 5


class UnsafeUrlError(ValueError):
    """Raised by a caller that manually follows redirects when a hop's
    `Location` target fails :func:`is_safe_url`, or when the redirect chain
    exceeds :data:`MAX_REDIRECT_HOPS`. Not raised by `is_safe_url()` itself
    — that function returns a `(bool, str)` pair instead, matching the
    original `misc.py::_is_safe_url` calling convention every existing
    caller already expects."""


def _is_unsafe_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Unwrap an IPv4-mapped IPv6 address (::ffff:127.0.0.1) so the IPv4-side
    # checks below actually apply to it. (CPython's ipaddress module already
    # classifies most of these correctly on its own for IPv6Address, but the
    # explicit unwrap is kept — matching the sibling implementation this
    # module was generalized from — as defence against a future Python
    # version narrowing that behaviour.)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        # Catches ranges `is_private` alone misses on this Python version —
        # e.g. 100.64.0.0/10 (RFC 6598 shared/CGNAT address space, the range
        # cloud metadata endpoints commonly sit adjacent to): `is_private` is
        # False for it, but `is_global` is correctly False too.
        or not ip.is_global
    )


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate that `url` is safe to fetch server-side.

    Rejects non-http(s) schemes, embedded userinfo, a missing host, and any
    host whose resolved address(es) are private/loopback/link-local/
    multicast/reserved/unspecified/non-global. Returns `(True, "")` on
    success, `(False, reason)` on the first failing check. Does not raise for
    any input it has been probed with, including a malformed URL or a
    hostname `socket.getaddrinfo` cannot resolve (a DNS failure, or a label
    exceeding IDNA's length limit) — every one of those comes back as
    `(False, reason)` rather than propagating an exception to the caller.

    This validates ONE url only. A caller that manually follows redirects
    MUST call this again on every hop's `Location` target (see module
    docstring) — it does not fetch anything or follow redirects itself.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL."
    if parsed.scheme not in {"http", "https"}:
        return False, "Only http and https URLs are allowed."
    if parsed.username or parsed.password:
        return False, "URLs with embedded userinfo (user:pass@host) are not allowed."
    host = parsed.hostname
    if not host:
        return False, "Missing host."

    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError) as exc:
        # `getaddrinfo` raises `socket.gaierror` for an ordinary DNS failure,
        # but a `UnicodeError` (a `ValueError` subclass, NOT `gaierror`) for a
        # hostname whose IDNA-encoded label exceeds the DNS length limit
        # (待回答 #47 review F2 — reproduced: 64x'a' + '.com' escaped the
        # narrower `except socket.gaierror` and 500'd `POST /api/fetch_status`
        # instead of returning the intended 400). Any other platform-specific
        # `OSError` from the resolver is caught the same way, on the same
        # reasoning as the bare `except Exception` this replaced in the
        # pre-refactor `misc.py::_is_safe_url`.
        return False, f"Could not resolve host: {host} ({exc})"
    if not infos:
        return False, f"Could not resolve host: {host}"

    for info in infos:
        # `info[4]` (the sockaddr tuple) is a union of the IPv4/IPv6 shapes
        # in typeshed's socket stub; index 0 is the address string in both.
        raw_address = str(info[4][0]).split("%", 1)[0]  # strip an IPv6 zone id, if any
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            return False, f"Could not parse a resolved address for host: {host}"
        if _is_unsafe_address(address):
            return False, "Requests to private or reserved addresses are not allowed."

    return True, ""
