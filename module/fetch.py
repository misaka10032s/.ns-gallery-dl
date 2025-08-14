import sys
import os
import threading
import time
import itertools
import subprocess
from .site.pixiv import get_pixiv_token
from .site.nhentai import download_nhentai
from .site.wnacg import download_wnacg
from .config import DOWNLOAD_DIR, MAX_RETRIES, RETRY_DELAY, INPUT_FILE

def try_download(url, tokens):
    if "nhentai.net" in url.lower():
        return download_nhentai(url, tokens)
    if "wnacg.com" in url.lower():
        return download_wnacg(url, tokens)
        
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
        with open(INPUT_FILE, "w", encoding="utf-8") as f:
            pass  # Create the file
        print(f"[!] {INPUT_FILE} not found.")
        print(f"[*] An empty {INPUT_FILE} has been created for you.")
        print(f"[*] Please add URLs to it and run the script again.")
        sys.exit(0)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw_lines = f.read().splitlines()

    urls = []
    for line in raw_lines:
        line = line.strip().replace(" ", "")
        if not line:
            continue

        if line.startswith("pw") and line[2:].isdigit():
            url = f"https://www.pixiv.net/artworks/{line[2:]}"
        elif line.startswith("pu") and line[2:].isdigit():
            url = f"https://www.pixiv.net/users/{line[2:]}"
        elif line.startswith("p") and line[1:].isdigit():
            url = f"https://www.pixiv.net/artworks/{line[1:]}"
        elif line.lower() == "x":
            url = "https://x.com"
        elif line.startswith("http://") or line.startswith("https://"):
            url = line
        else:
            url = f"https://{line}"

        urls.append(url)
    return urls
