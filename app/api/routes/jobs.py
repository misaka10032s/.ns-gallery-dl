from __future__ import annotations

import json

from flask import Flask, jsonify, request

from app.domain.enums import JobSource, Provider
from app.services import browser_bridge_service
from app.services.download_service import recent_jobs_payload
from app.storage.repositories import jobs_repo


def register(app: Flask) -> None:
    @app.route("/api/jobs", methods=["GET"])
    def get_jobs():
        return jsonify(recent_jobs_payload(jobs_repo.list_recent(200)))

    @app.route("/api/jobs", methods=["POST"])
    def submit_jobs():
        payload = request.get_json() or {}
        links = payload.get("links") or [item.get("url") for item in payload.get("items", []) if item.get("url")]
        links = [link.strip() for link in links if isinstance(link, str) and link.strip()]
        if not links:
            return jsonify({"error": 'Invalid request. "links" is required.'}), 400
        try:
            source = JobSource(payload.get("source", JobSource.API.value))
        except ValueError:
            source = JobSource.API
        provider_hint = payload.get("providerHint")
        provider = Provider(provider_hint) if provider_hint in {member.value for member in Provider} else None
        raw_meta = payload.get("meta")
        meta = raw_meta if isinstance(raw_meta, dict) else None
        count = browser_bridge_service.submit_urls(links, source=source, provider=provider, metadata=meta)
        return jsonify({"message": f"Queued {count} links for download."}), 202

    @app.route("/download", methods=["POST"])
    def legacy_download():
        payload = request.get_json() or {}
        links = payload.get("links", [])
        if not isinstance(links, list):
            return jsonify({"error": '"links" must be a list of strings.'}), 400
        count = browser_bridge_service.submit_urls([item for item in links if isinstance(item, str)], source=JobSource.API)
        return jsonify({"message": f"Queued {count} links for download."}), 202

    @app.route("/api/jobs/<int:job_id>/retry", methods=["POST"])
    def retry_job(job_id: int):
        job = jobs_repo.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        try:
            source = JobSource(job.get("source", JobSource.API.value))
        except ValueError:
            source = JobSource.API
        meta = json.loads(job.get("meta_json", "{}") or "{}")
        retry_meta = {
            key: value
            for key, value in meta.items()
            if key not in {"attempted_providers", "attempts", "selected_provider"}
        }
        retry_meta["retry_of"] = job_id
        provider_value = job.get("provider")
        provider_mode = retry_meta.get("provider_mode")
        if provider_mode is None:
            provider_mode = "forced" if provider_value == Provider.DIRECT_FILE.value else "auto"
            retry_meta["provider_mode"] = provider_mode
        if provider_mode == "auto":
            provider = None
        elif provider_value in {member.value for member in Provider}:
            provider = Provider(provider_value)
        else:
            provider = None
        count = browser_bridge_service.submit_urls([job["url"]], source=source, metadata=retry_meta, provider=provider)
        return jsonify({"message": f"Queued {count} retry job.", "retry_of": job_id}), 202
