from __future__ import annotations

from flask import Flask

from app.api import origin_guard
from app.api.routes import register_routes
from app.config.paths import UI_DIR
from app.config.settings import API_PORT
from app.providers.cookies.registry import scan_cookie_files
from app.services import queue_service
from app.storage.db import init_db


def _bootstrap_app() -> None:
    init_db()
    scan_cookie_files()
    queue_service.start_worker()


def create_app() -> Flask:
    _bootstrap_app()
    app = Flask(__name__, static_folder=str(UI_DIR), static_url_path="/ui")
    # Registered before the routes purely for readability — before_request
    # hooks apply globally regardless of registration order relative to
    # add_url_rule (待回答 #47; see app/api/origin_guard.py).
    origin_guard.register(app)
    register_routes(app)
    return app


def run_server(host: str = "127.0.0.1", port: int = API_PORT) -> None:
    app = create_app()
    print(f"[*] Starting NS Media Hub server at http://{host}:{port}")
    app.run(host=host, port=port, use_reloader=False)
