import os
import json
from datetime import datetime
from .config import HISTORY_FILE
import threading

# Thread lock for history file access
history_lock = threading.Lock()

def load_history():
    with history_lock:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

def save_history(history):
    with history_lock:
        # filter same url of the same day, preserve the last status
        for date, entries in history.items():
            seen = {}
            # Iterate in reverse to keep the last entry
            for entry in reversed(entries):
                if entry["url"] not in seen:
                    seen[entry["url"]] = entry
            # Restore original order
            history[date] = list(reversed(list(seen.values())))

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

def filter_by_history(urls):
    history = load_history()

    downloaded_all = {
        entry["url"]
        for entries in history.values()
        for entry in entries
        if entry.get("result") == "success"
    }

    filtered = [url for url in urls if url not in downloaded_all]
    return filtered

def add_to_history(results):
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")

    # Each URL keeps only one record (the latest attempt).
    # Remove any prior entries for these URLs across all dates before inserting.
    new_urls = {r["url"] for r in results}
    for date in list(history.keys()):
        history[date] = [item for item in history[date] if item.get("url") not in new_urls]
        if not history[date]:
            del history[date]

    if today not in history:
        history[today] = []
    history[today].extend(results)
    save_history(history)

def delete_from_history(date, url):
    history = load_history()
    if date not in history:
        return False
    original = history[date]
    history[date] = [item for item in original if item.get("url") != url]
    if len(history[date]) == len(original):
        return False
    if not history[date]:
        del history[date]
    save_history(history)
    return True

def update_history_status(date, url, new_status):
    history = load_history()
    if date in history:
        item_found = False
        for item in history[date]:
            if item.get('url') == url:
                item['result'] = new_status
                item_found = True
                break
        if item_found:
            save_history(history)
            return True
    return False