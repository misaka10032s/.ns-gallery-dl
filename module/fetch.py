from __future__ import annotations

from app.domain.enums import JobSource
from app.domain.jobs import JobRequest
from app.main import read_input_urls
from app.services import download_service, history_service
from app.services.token_service import load_tokens


def try_download(url: str) -> str:
    result = download_service.download_request(JobRequest(url=url, source=JobSource.MANUAL), load_tokens())
    return result.status.value


def parse_urls(isForce: bool = False) -> list[str]:
    urls = read_input_urls("dl.txt")
    return urls if isForce else history_service.filter_by_history(urls)


def try_download_loop() -> None:
    tokens = load_tokens()
    for url in parse_urls():
        result = download_service.download_request(JobRequest(url=url, source=JobSource.MANUAL), tokens)
        history_service.add_to_history([download_service.history_payload(url, JobSource.MANUAL, result)])
