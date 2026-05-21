from __future__ import annotations

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
        count = browser_bridge_service.submit_urls(links, source=source, provider=provider)
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
        provider_value = job.get("provider")
        provider = Provider(provider_value) if provider_value in {member.value for member in Provider} else None
        count = browser_bridge_service.submit_urls([job["url"]], source=source, metadata={"retry_of": job_id}, provider=provider)
        return jsonify({"message": f"Queued {count} retry job.", "retry_of": job_id}), 202
