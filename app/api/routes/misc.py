from __future__ import annotations

from urllib.parse import urlparse

import cloudscraper
from flask import Flask, jsonify, request

from app.config.features import ENABLE_COOKIE_API
from app.domain import auth_cooldown
from app.domain.network_safety import is_safe_url as _is_safe_url
from app.providers.cookies.registry import scan_cookie_files
from app.services.download_service import recent_jobs_payload
from app.services import cookie_service, queue_service
from app.storage.repositories import history_repo, jobs_repo
from app.storage.repositories import cookies_repo


def _check_same_origin() -> tuple[bool, str]:
    """驗證請求來自同源（Origin 或 Referer 必須為 127.0.0.1:7601）。
    防止本機其他頁面對變更端點發送 CSRF 請求。

    KNOWN GAP: this is a same-origin CSRF check only — there is no session/token
    auth anywhere in this app's mutating endpoints (cookie CRUD here, jobs/history
    requeue, /api/downloaders/update). That's fine for a strictly local-only
    (127.0.0.1) tool but would NOT be safe if this server were ever exposed beyond
    localhost. Reused as-is by app/api/routes/downloaders.py; also imported by
    that module for the same reason.
    """
    # 取得 Origin 或 Referer（依 RFC 6454，變更請求瀏覽器通常送 Origin）
    origin = request.headers.get("Origin", "").strip()
    referer = request.headers.get("Referer", "").strip()

    source = origin or referer
    if not source:
        # 不含 Origin/Referer 的請求（例如 curl 直接呼叫）來自 127.0.0.1 仍屬本地工具呼叫，
        # 允許通過但僅限本地服務已綁定 127.0.0.1 的情境
        return True, ""

    try:
        parsed = urlparse(source)
    except Exception:
        return False, "無法解析 Origin/Referer。"

    host = parsed.hostname or ""
    # 只允許來自 127.0.0.1 的同源請求
    if host not in ("127.0.0.1", "localhost"):
        return False, "拒絕跨來源的 cookie 變更請求。"

    return True, ""


# `_is_safe_url` used to be defined here (bare substring-free but single-
# address, first-getaddrinfo-result-only checks — see 待回答 #48). It is now
# `app.domain.network_safety.is_safe_url`, imported above under its old name
# for backward compatibility (this route below, and anything importing
# `app.api.routes.misc._is_safe_url`, is unaffected) — the shared module also
# checks EVERY resolved address (not just the first), rejects embedded
# userinfo, and is reused by app/providers/direct_file/provider.py and
# app/services/discord_service.py, which previously had no such check at all.


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
            ok, reason = _check_same_origin()
            if not ok:
                return jsonify({"error": reason}), 403
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
            ok, reason = _check_same_origin()
            if not ok:
                return jsonify({"error": reason}), 403
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
            ok, reason = _check_same_origin()
            if not ok:
                return jsonify({"error": reason}), 403
            payload = request.get_json() or {}
            try:
                deleted = cookie_service.delete_cookie(payload.get("domain", ""))
            except FileNotFoundError as exc:
                return jsonify({"error": str(exc)}), 404
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            return jsonify({"message": f"Deleted {deleted} cookie file(s)."})

        @app.route("/api/cookies/<path:domain>/cooldown", methods=["DELETE"])
        def clear_cookie_cooldown(domain: str):
            """Manual override (dispatch B2): end `domain`'s auth-failure
            cooldown right now, without touching its cookie jar at all — for
            when the owner believes the site's own block already lifted and
            doesn't want to wait out AUTH_COOLDOWN_SECONDS
            (app/domain/auth_cooldown.py). Same same-origin CSRF guard as the
            other cookie-mutation endpoints above; idempotent (200 either way,
            `cleared` says whether a cooldown actually existed)."""
            ok, reason = _check_same_origin()
            if not ok:
                return jsonify({"error": reason}), 403
            cleared = auth_cooldown.clear_cooldown(domain)
            return jsonify(
                {
                    "message": "冷卻已解除。" if cleared else "此網域目前沒有冷卻中。",
                    "cleared": cleared,
                }
            )
