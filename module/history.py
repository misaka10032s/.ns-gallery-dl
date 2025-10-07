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
    if today not in history:
        history[today] = []
    history[today].extend(results)
    save_history(history)

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