# module/downloader.py
# Shared download queue state — used by both the Flask server worker and the Discord bot.
# The server worker processes items sequentially; the bot registers items for visibility.

import threading
from queue import Queue
from .fetch import try_download
from .history import add_to_history, filter_by_history

download_queue: Queue = Queue()

_lock = threading.Lock()
_queued_items: list[str] = []    # all pending/in-progress URLs (drives /queue page)
_current_item: str | None = None # URL the server worker is currently downloading


# ── server worker API ─────────────────────────────────────────────────────────

def enqueue(links: list[str]) -> None:
    """Add links to the server worker's sequential download queue."""
    with _lock:
        _queued_items.extend(links)
    for link in links:
        download_queue.put(link)


def get_state() -> dict:
    """Return a snapshot of the current queue state for /api/queue."""
    with _lock:
        return {
            'current': _current_item,
            'pending': list(_queued_items),
            'total': len(_queued_items) + (1 if _current_item else 0),
        }


def _worker() -> None:
    global _current_item
    is_remain = False
    while True:
        link = download_queue.get()
        if link is None:
            if is_remain:
                print("[*] No more tasks in the queue. Worker is exiting.\n\n")
            _current_item = None
            break
        is_remain = True

        with _lock:
            try:
                _queued_items.remove(link)
            except ValueError:
                pass
            _current_item = link

        try:
            links = filter_by_history([link])
            if not links:
                print(f"[*] Skipping already downloaded: {link}\n\n")
                continue
            link = links[0]
            print(f"[*] Starting download for: {link}")
            result = try_download(link)
            print(f"[*] Download result for {link}: {result}\n\n")
            add_to_history([{"url": link, "result": result}])
        finally:
            with _lock:
                _current_item = None
            download_queue.task_done()


def start_worker() -> threading.Thread:
    """Start the download worker thread (call once from server startup)."""
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


# ── bot display API ───────────────────────────────────────────────────────────

def add_to_display(url: str) -> None:
    """Register a URL as in-progress so it appears on the /queue page."""
    with _lock:
        _queued_items.append(url)


def remove_from_display(url: str) -> None:
    """Remove a URL from the /queue page display when the bot finishes it."""
    with _lock:
        try:
            _queued_items.remove(url)
        except ValueError:
            pass
