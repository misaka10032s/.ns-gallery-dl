from __future__ import annotations

from flask import Flask

from . import auth, history, jobs, misc, pages, queue


def register_routes(app: Flask) -> None:
    pages.register(app)
    history.register(app)
    queue.register(app)
    jobs.register(app)
    auth.register(app)
    misc.register(app)
