import os
import json
from datetime import datetime
from .config import HISTORY_FILE

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
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