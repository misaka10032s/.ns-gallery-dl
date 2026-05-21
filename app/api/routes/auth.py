from __future__ import annotations

from flask import Flask, jsonify

from app.services.token_service import load_tokens


def register(app: Flask) -> None:
    @app.route("/api/auth/pixiv", methods=["GET"])
    def pixiv_auth():
        tokens = load_tokens()
        return jsonify({"has_refresh_token": bool(tokens.get("pixiv_refresh_token"))})
