from app.api.app import create_app
from app.config.settings import API_PORT


app = create_app()


if __name__ == "__main__":
    # Reads the SAME `API_PORT` app/api/origin_guard.py's Host-header check
    # requires (待回答 #47 review F3) — this legacy entry point used to
    # hardcode 7601 independently, so overriding NS_MEDIA_HUB_PORT would bind
    # this process to the new port while the guard still demanded the old
    # one, 403-ing every mutating request through it.
    app.run(host="127.0.0.1", port=API_PORT)
