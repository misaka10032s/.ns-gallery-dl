import sys
import os
import json
import subprocess
import time
import threading
import itertools
from datetime import datetime
from pathlib import Path

HISTORY_FILE = "history.json"
TOKEN_FILE = "token.json"
INPUT_FILE = "dl.txt"
DOWNLOAD_DIR = "download"
MAX_RETRIES = 10
RETRY_DELAY = 5  # 秒

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)

def get_pixiv_token(tokens):
    """檢查或取得 Pixiv refresh token"""
    if "pixiv_refresh_token" in tokens and tokens["pixiv_refresh_token"]:
        return tokens["pixiv_refresh_token"]

    print("[Pixiv] 未找到 refresh token，執行認證流程...")
    try:
        subprocess.run(["gallery-dl", "oauth:pixiv"], check=True)
    except subprocess.CalledProcessError:
        print("[Pixiv] 認證流程執行失敗")
        return None

    config_path = Path.home() / ".config" / "gallery-dl" / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            refresh_token = cfg.get("extractor", {}).get("pixiv", {}).get("refresh-token", "")
            if refresh_token:
                tokens["pixiv_refresh_token"] = refresh_token
                save_tokens(tokens)
                print("[Pixiv] refresh token 已儲存到 token.json")
                return refresh_token
        except Exception as e:
            print(f"[Pixiv] 無法讀取 config.json: {e}")

    print("[Pixiv] 無法取得 refresh token")
    return None

def try_download(url, tokens):
    stop_animation = False

    def animate():
        for dots in itertools.cycle([".  ", ".. ", "..."]):
            if stop_animation:
                break
            sys.stdout.write(f"\rdownload: {url} {dots}")
            sys.stdout.flush()
            time.sleep(0.5)

    for attempt in range(1, MAX_RETRIES + 1):
        stop_animation = False
        anim_thread = threading.Thread(target=animate)
        anim_thread.start()

        if attempt > 1:
            if attempt > 2:
                time.sleep(RETRY_DELAY)
            sys.stdout.write(f"\r[Retry {attempt}/{MAX_RETRIES}] 重新嘗試下載: {url}\n")
            sys.stdout.flush()

        try:
            env = os.environ.copy()
            if "pixiv" in url.lower():
                token = get_pixiv_token(tokens)
                if token:
                    env["GALLERYDL_PIXIV_REFRESH_TOKEN"] = token

            subprocess.run(
                ["gallery-dl", url, "-d", DOWNLOAD_DIR],
                check=True,
                capture_output=True,
                text=True,
                env=env
            )
            stop_animation = True
            anim_thread.join()
            sys.stdout.write(f"\rdownload: {url} complete\n")
            sys.stdout.flush()
            return "success"

        except subprocess.CalledProcessError as e:
            stop_animation = True
            anim_thread.join()
            error_msg = (e.stderr or e.stdout or "").lower()
            if "pixiv" in url.lower() and "'refresh-token' required" in error_msg:
                get_pixiv_token(tokens)
                continue
            elif "timed out" in error_msg or "connection" in error_msg:
                print(f"[!] 連線錯誤，將重試: {error_msg.strip()}")
                continue
            else:
                print(f"[!] 下載失敗: {error_msg.strip() or '未知錯誤'}")
                continue

    return "failed"

def parse_urls():
    if not os.path.exists(INPUT_FILE):
        print(f"[!] 找不到 {INPUT_FILE}")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_lines = f.read().splitlines()

    urls = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("p") and line[1:].isdigit():
            url = f"https://www.pixiv.net/artworks/{line[1:]}"
        elif line.lower() == "x":
            url = "https://x.com"
        elif line.startswith("http://") or line.startswith("https://"):
            url = line
        else:
            url = f"https://{line}"

        urls.append(url)
    return urls

def main():
    force_download = any(arg.lower() in ("-f", "-force") for arg in sys.argv[1:])
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
    print("[*] 所有任務完成")

if __name__ == "__main__":
    main()
