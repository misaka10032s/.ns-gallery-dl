from __future__ import annotations

from flask import Flask, jsonify

from app.services import queue_service


def register(app: Flask) -> None:
    @app.route("/api/queue", methods=["GET"])
    def get_queue():
        return jsonify(queue_service.get_state())
