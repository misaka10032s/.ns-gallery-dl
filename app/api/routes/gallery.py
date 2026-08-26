from __future__ import annotations

import mimetypes

from flask import Flask, Response, abort, jsonify, request, send_file

from app.services import doujin_service, gallery_service


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

    # ── Doujinshi mode (本子): cover wall + book detail/edit/links ──────────
    # Pages themselves are served through the existing /api/gallery/serve
    # endpoint above (Range-capable, same traversal guard) — a book page is
    # just another file under DOWNLOAD_DIR, so no new file-serving path exists.

    @app.route("/api/gallery/doujin/books", methods=["GET"])
    def doujin_books():
        source = request.args.get("source", "")
        books = doujin_service.list_source_books(source)
        if books is None:
            abort(400, description="source is not a doujinshi-mode source")
        return jsonify(books)

    @app.route("/api/gallery/doujin/book", methods=["GET"])
    def doujin_book_detail():
        path = request.args.get("path", "")
        detail = doujin_service.get_book_detail(path)
        if detail is None:
            abort(404)
        return jsonify(detail)

    @app.route("/api/gallery/doujin/book", methods=["PUT"])
    def doujin_book_update():
        payload = request.get_json(silent=True) or {}
        path = payload.get("folder_path", "")
        if not path:
            abort(400, description="folder_path is required")
        try:
            detail = doujin_service.update_book(path, payload)
        except doujin_service.ValidationError as exc:
            abort(400, description=str(exc))
        if detail is None:
            abort(404)
        return jsonify(detail)

    @app.route("/api/gallery/doujin/book/links", methods=["POST"])
    def doujin_link_add():
        payload = request.get_json(silent=True) or {}
        path = payload.get("folder_path", "")
        if not path:
            abort(400, description="folder_path is required")
        try:
            link = doujin_service.add_link(path, payload.get("label", ""), payload.get("url", ""))
        except doujin_service.ValidationError as exc:
            abort(400, description=str(exc))
        except ValueError:
            abort(409, description="this link already exists on this book")
        if link is None:
            abort(404)
        return jsonify(link), 201

    @app.route("/api/gallery/doujin/book/links/<int:link_id>", methods=["DELETE"])
    def doujin_link_delete(link_id: int):
        path = request.args.get("folder_path", "")
        if not path:
            abort(400, description="folder_path is required")
        ok = doujin_service.delete_link(path, link_id)
        if not ok:
            abort(404)
        return jsonify({"ok": True})

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
