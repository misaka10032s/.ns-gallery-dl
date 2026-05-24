from __future__ import annotations

import mimetypes

from flask import Flask, Response, abort, jsonify, request, send_file

from app.services import gallery_service


def register(app: Flask) -> None:
    @app.route("/api/gallery", methods=["GET"])
    def gallery_categories():
        return jsonify(gallery_service.list_categories())

    @app.route("/api/gallery/items", methods=["GET"])
    def gallery_items():
        category = request.args.get("category", "")
        return jsonify(gallery_service.list_items(category))

    @app.route("/api/gallery/files", methods=["GET"])
    def gallery_files():
        path = request.args.get("path", "")
        return jsonify(gallery_service.list_files(path))

    @app.route("/api/gallery/serve", methods=["GET"])
    def gallery_serve():
        rel_path = request.args.get("p", "")
        if not rel_path:
            abort(400)
        file_path = gallery_service.resolve_file(rel_path)
        if not file_path:
            abort(404)

        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"
        file_size = file_path.stat().st_size
        range_header = request.headers.get("Range")

        if range_header:
            try:
                byte_range = range_header.replace("bytes=", "").split("-")
                start = int(byte_range[0]) if byte_range[0] else 0
                end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1
                with open(file_path, "rb") as f:
                    f.seek(start)
                    data = f.read(length)
                return Response(
                    data,
                    status=206,
                    mimetype=mime,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(length),
                    },
                )
            except (ValueError, OSError):
                abort(400)

        return send_file(file_path, mimetype=mime, conditional=True)
