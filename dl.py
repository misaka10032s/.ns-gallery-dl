import sys
import os
import subprocess
from datetime import datetime
from module.history import load_history, save_history
from module.tokens import load_tokens
from module.fetch import parse_urls, try_download
from module.config import DOWNLOAD_DIR

def main():
    if any(arg.lower() in ("-s", "--server") for arg in sys.argv[1:]):
        from module.server import app
        print("[*] Starting Flask server...")
        app.run(host='127.0.0.1', port=5001)
        return

    if any(arg.lower() in ("-u", "--update") for arg in sys.argv[1:]):
        print("[*] Updating pip and gallery-dl...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "gallery-dl"], check=True)
            print("[*] Update complete.")
        except subprocess.CalledProcessError as e:
            print(f"[!] Update failed: {e}")
        return

    force_download = any(arg.lower() in ("-f", "--force") for arg in sys.argv[1:])
    history = load_history()
    tokens = load_tokens()

    today = datetime.now().strftime("%Y-%m-%d")
    if today not in history:
        history[today] = []

    downloaded_all = {
        entry["url"]
        for entries in history.values()
        for entry in entries
        if entry.get("result") == "success"
    }

    urls = parse_urls()
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for url in urls:
        if not force_download and url in downloaded_all:
            print(f"# skip: {url}")
            continue

        result = try_download(url, tokens)
        history[today].append({"url": url, "result": result})

    save_history(history)
    print("[*] All tasks completed.")

if __name__ == "__main__":
    main()
