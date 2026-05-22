from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

from app.api.app import run_server
from app.config.paths import DATA_DIR, DOWNLOAD_DIR, ROOT_DIR
from app.domain.enums import JobSource, JobStatus
from app.domain.jobs import JobRequest
from app.providers.cookies.registry import scan_cookie_files
from app.services import download_service, history_service, queue_service
from app.services.discord_service import run as run_bot
from app.services.frontend_service import ensure_frontend_ready
from app.services.token_service import load_tokens
from app.storage.db import init_db


def _bootstrap(ensure_ui: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if ensure_ui:
        ensure_frontend_ready()
    init_db()
    scan_cookie_files()
    queue_service.start_worker()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NS Media Hub unified downloader",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Tip: -sb is accepted as shorthand for -s -b.",
    )
    parser.add_argument("urls", nargs="*", help="URLs to download. If omitted, read dl.txt")
    parser.add_argument("--file", default=str(ROOT_DIR / "dl.txt"), help="Input file for batch downloads")
    parser.add_argument("-s", "--server", action="store_true", help="Start local API server")
    parser.add_argument("-b", "--bot", action="store_true", help="Start Discord bot")
    parser.add_argument("-u", "--update", action="store_true", help="Reserved; launcher scripts already handle dependency updates")
    expanded_args: list[str] = []
    for item in sys.argv[1:]:
        if item == "-sb":
            expanded_args.extend(["-s", "-b"])
        else:
            expanded_args.append(item)
    return parser.parse_args(expanded_args)


def _expand_shortcuts(line: str) -> str:
    value = line.strip().replace(" ", "")
    if not value or value.startswith("#"):
        return ""
    expanded = download_service.expand_url_shortcut(value)
    if expanded:
        return expanded
    lower = value.lower()
    if lower == "x":
        return "https://x.com"
    if lower.startswith(("http://", "https://", "ytdlp://")):
        return value
    return f"https://{value}"


def read_input_urls(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        path.write_text("", encoding="utf-8")
        return []
    urls = [_expand_shortcuts(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [url for url in urls if url]


def run_batch_download(urls: list[str]) -> int:
    tokens = load_tokens()
    filtered = history_service.filter_by_history(urls)
    if not filtered:
        print("[*] No new URLs to download.")
        return 0

    failures = 0
    for url in filtered:
        result = download_service.download_request(JobRequest(url=url, source=JobSource.MANUAL), tokens)
        history_service.add_to_history([download_service.history_payload(url, JobSource.MANUAL, result)])
        print(f"[*] {result.status.value.upper()}: {url}")
        if result.status == JobStatus.FAILED:
            failures += 1
    return 1 if failures else 0


def main() -> int:
    args = parse_args()
    _bootstrap(ensure_ui=args.server)
    if args.update:
        print("[*] Update mode is handled by dl.cmd / dl.sh before Python starts.")

    if args.server and args.bot:
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        run_bot()
        return 0
    if args.server:
        run_server()
        return 0
    if args.bot:
        run_bot()
        return 0

    urls = args.urls or read_input_urls(args.file)
    return run_batch_download(urls)


if __name__ == "__main__":
    raise SystemExit(main())
