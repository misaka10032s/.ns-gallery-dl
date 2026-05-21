from __future__ import annotations

from flask import Flask, jsonify, request

from app.domain.enums import JobSource
from app.services import browser_bridge_service
from app.services import history_service


def register(app: Flask) -> None:
    @app.route("/api/history", methods=["GET"])
    def get_history():
        return jsonify(history_service.load_history())

    @app.route("/api/history", methods=["DELETE"])
    def delete_history():
        payload = request.get_json() or {}
        if not payload.get("date") or not payload.get("url"):
            return jsonify({"error": "Missing date or url"}), 400
        ok = history_service.delete_from_history(payload["date"], payload["url"])
        if ok:
            return jsonify({"message": "Deleted"}), 200
        return jsonify({"error": "History item not found"}), 404

    @app.route("/api/history", methods=["PUT"])
    def update_history():
        payload = request.get_json() or {}
        if not all(payload.get(key) for key in ("date", "url", "status")):
            return jsonify({"error": "Missing date, url, or status"}), 400
        ok = history_service.update_history_status(payload["date"], payload["url"], payload["status"])
        if ok:
            return jsonify({"message": "Updated"}), 200
        return jsonify({"error": "History item not found"}), 404

    @app.route("/api/history/requeue", methods=["POST"])
    def requeue_history():
        payload = request.get_json() or {}
        links = payload.get("links") or []
        if not isinstance(links, list):
            return jsonify({"error": '"links" must be a list of strings.'}), 400
        cleaned = [item.strip() for item in links if isinstance(item, str) and item.strip()]
        if not cleaned:
            return jsonify({"error": "No valid links supplied."}), 400
        count = browser_bridge_service.submit_urls(cleaned, source=JobSource.MANUAL)
        return jsonify({"message": f"Queued {count} links for download."}), 202
