from __future__ import annotations

from flask import Flask, jsonify, request

from app.domain.enums import JobSource, JobStatus, Provider
from app.domain.jobs import JobRequest
from app.services import browser_bridge_service
from app.services import history_service

_VALID_HISTORY_STATUSES = {s.value for s in JobStatus}


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
        if payload["status"] not in _VALID_HISTORY_STATUSES:
            return jsonify({"error": f"Invalid status. Must be one of: {sorted(_VALID_HISTORY_STATUSES)}"}), 400
        ok = history_service.update_history_status(payload["date"], payload["url"], payload["status"])
        if ok:
            return jsonify({"message": "Updated"}), 200
        return jsonify({"error": "History item not found"}), 404

    @app.route("/api/history/requeue", methods=["POST"])
    def requeue_history():
        payload = request.get_json() or {}
        items = payload.get("items")
        requests: list[JobRequest] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                if not isinstance(url, str) or not url.strip():
                    continue
                provider_value = item.get("provider")
                provider = Provider(provider_value) if provider_value in {member.value for member in Provider} else None
                metadata = item.get("meta") if isinstance(item.get("meta"), dict) else {}
                provider_mode = metadata.get("provider_mode")
                if provider_mode is None:
                    if provider == Provider.DIRECT_FILE:
                        metadata["provider_mode"] = "forced"
                    else:
                        metadata["provider_mode"] = "auto"
                        provider = None
                requests.append(JobRequest(url=url.strip(), source=JobSource.MANUAL, provider=provider, metadata=metadata))
        else:
            links = payload.get("links") or []
            if not isinstance(links, list):
                return jsonify({"error": '"links" must be a list of strings.'}), 400
            requests = [JobRequest(url=item.strip(), source=JobSource.MANUAL) for item in links if isinstance(item, str) and item.strip()]
        if not requests:
            return jsonify({"error": "No valid links supplied."}), 400
        count = browser_bridge_service.submit_requests(requests)
        return jsonify({"message": f"Queued {count} links for download."}), 202
