from __future__ import annotations

import ipaddress
import socket

import cloudscraper
from flask import Flask, jsonify, request

from app.config.features import ENABLE_COOKIE_API
from app.providers.cookies.registry import scan_cookie_files
from app.services.download_service import recent_jobs_payload
from app.services import cookie_service, queue_service
from app.storage.repositories import history_repo, jobs_repo
from app.storage.repositories import cookies_repo


def _is_safe_url(url: str) -> tuple[bool, str]:
    """
    Validate that a URL is safe to proxy.
    Rejects non-HTTP(S) schemes and private/loopback/link-local hosts to prevent SSRF.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL."
    if parsed.scheme not in {"http", "https"}:
        return False, "Only http and https URLs are allowed."
    host = parsed.hostname
    if not host:
        return False, "Missing host."

    # Resolve hostname to IP and check it is a public address.
    try:
        addr_str = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)[0][4][0]
        addr = ipaddress.ip_address(addr_str)
    except Exception:
        return False, f"Could not resolve host: {host}"

    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved or addr.is_unspecified:
        return False, "Requests to private or reserved addresses are not allowed."

    return True, ""


def register(app: Flask) -> None:
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"ok": True, "app": "ns-media-hub"})

    @app.route("/api/fetch_status", methods=["POST"])
    def fetch_status():
        payload = request.get_json() or {}
        url = payload.get("url", "")
        if not url:
            return jsonify({"error": "URL is missing"}), 400
        safe, reason = _is_safe_url(url)
        if not safe:
            return jsonify({"error": reason}), 400
        scraper = cloudscraper.create_scraper()
        try:
            response = scraper.get(url, timeout=10)
            return jsonify({"status_code": response.status_code, "text": response.text[:500]})
        except cloudscraper.exceptions.CloudflareChallengeError as exc:
            return jsonify({"error": str(exc)}), 403
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/dashboard", methods=["GET"])
    def dashboard():
        queue_state = queue_service.get_state()
        history_stats = history_repo.summary()
        recent_jobs = jobs_repo.list_recent(8)
        return jsonify(
            {
                "queue": queue_state,
                "jobs": {
                    "counts": jobs_repo.counts_by_status(),
                    "recent": recent_jobs_payload(recent_jobs),
                },
                "history": history_stats,
                "cookies": {
                    "count": cookies_repo.count_cookies(),
                },
            }
        )

    if ENABLE_COOKIE_API:
        @app.route("/api/cookies", methods=["GET"])
        def get_cookies():
            return jsonify(cookie_service.list_cookies())

        @app.route("/api/cookies/<path:domain>", methods=["GET"])
        def get_cookie(domain: str):
            record = cookie_service.read_cookie(domain)
            if not record:
                return jsonify({"error": "Cookie file not found."}), 404
            return jsonify(record)

        @app.route("/api/cookies", methods=["POST"])
        def create_cookie():
            payload = request.get_json() or {}
            try:
                record = cookie_service.save_cookie(
                    domain=payload.get("domain", ""),
                    cookie_value=payload.get("cookieValue", ""),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"message": "Cookie created.", "cookie": record}), 201

        @app.route("/api/cookies", methods=["PUT"])
        def update_cookie():
            payload = request.get_json() or {}
            try:
                record = cookie_service.save_cookie(
                    domain=payload.get("domain", ""),
                    cookie_value=payload.get("cookieValue", ""),
                    previous_domain=payload.get("previousDomain", ""),
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"message": "Cookie updated.", "cookie": record})

        @app.route("/api/cookies", methods=["DELETE"])
        def delete_cookie():
            payload = request.get_json() or {}
            try:
                deleted = cookie_service.delete_cookie(payload.get("domain", ""))
            except FileNotFoundError as exc:
                return jsonify({"error": str(exc)}), 404
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"message": f"Deleted {deleted} cookie file(s)."})
