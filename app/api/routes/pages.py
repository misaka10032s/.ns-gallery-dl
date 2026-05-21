from __future__ import annotations

from flask import Flask, send_from_directory

from app.config.paths import UI_DIR


def register(app: Flask) -> None:
    def _spa_entry():
        return send_from_directory(str(UI_DIR), "index.html")

    app.add_url_rule("/", view_func=_spa_entry, methods=["GET"])
    app.add_url_rule("/history", view_func=_spa_entry, methods=["GET"])
    app.add_url_rule("/queue", view_func=_spa_entry, methods=["GET"])
    app.add_url_rule("/jobs", view_func=_spa_entry, methods=["GET"])
    app.add_url_rule("/cookies", view_func=_spa_entry, methods=["GET"])
