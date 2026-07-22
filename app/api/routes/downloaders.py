from __future__ import annotations

from flask import Flask, jsonify

from app.api.routes.misc import _check_same_origin
from app.services import queue_service, updater_service


def register(app: Flask) -> None:
    @app.route("/api/downloaders/update", methods=["POST"])
    def update_downloaders():
        # Reuses the same same-origin CSRF guard as the cookie-mutation endpoints
        # (app/api/routes/misc.py) — see app/api/routes/misc.py's docstring for the
        # known gap: this app has no session/token auth on ANY mutating endpoint,
        # local-only by assumption.
        ok, reason = _check_same_origin()
        if not ok:
            return jsonify({"error": reason}), 403

        # Windows locks the running .exe while a job is in flight — refuse instead
        # of racing a pip upgrade against an active subprocess.
        if queue_service.get_state().get("current"):
            return jsonify({"error": "佇列忙碌中，請等待目前下載完成後再試。"}), 409

        results = updater_service.update_all_downloaders()
        return jsonify({"results": results})
