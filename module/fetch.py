import sys
import os
import subprocess
import time
from tqdm import tqdm
from .site.pixiv import get_pixiv_token
from .site.nhentai import download_nhentai
from .site.wnacg import download_wnacg
from .config import DOWNLOAD_DIR, MAX_RETRIES, RETRY_DELAY, INPUT_FILE

def try_download(url, tokens):
    if "nhentai.net" in url.lower():
        return download_nhentai(url, tokens)
    if "wnacg.com" in url.lower():
        return download_wnacg(url, tokens)
        
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            if attempt > 2:
                time.sleep(RETRY_DELAY)
            sys.stdout.write(f"\r[Retry {attempt}/{MAX_RETRIES}] Retrying download: {url}\n")
            sys.stdout.flush()

        try:
            env = os.environ.copy()
            if "pixiv" in url.lower():
                token = get_pixiv_token(tokens)
                if token:
                    env["GALLERYDL_PIXIV_REFRESH_TOKEN"] = token

            # Step 1: Simulate to get total file count
            simulate_cmd = ["gallery-dl", "--simulate", url]
            simulate_process = subprocess.run(
                simulate_cmd,
                capture_output=True,
                text=True,
                env=env,
                encoding='utf-8'
            )
            
            if simulate_process.returncode != 0:
                error_msg = (simulate_process.stderr or simulate_process.stdout or "").lower()
                if "pixiv" in url.lower() and "'refresh-token' required" in error_msg:
                    get_pixiv_token(tokens) # Refresh token and retry
                    continue
                else:
                    print(f"[!] Simulation failed: {error_msg.strip() or 'Unknown error'}")
                    continue

            # output format: 
            # # url1
            # # url2
            # # url3 ...
            # they all start with `# ` so we should slice the strings from the 2nd character
            total_files = len([line[2:] for line in simulate_process.stdout.splitlines()])
            if total_files == 0:
                print(f"[*] No new files to download for {url}")
                return "success"

            # Step 2: Run the actual download with Popen and tqdm
            download_cmd = ["gallery-dl", url, "-d", DOWNLOAD_DIR]
            process = subprocess.Popen(
                download_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                encoding='utf-8',
                errors='replace'
            )
            with tqdm(total=total_files, desc=f"Downloading {url}", unit="file") as pbar:
                for line in iter(process.stdout.readline, ''):
                    # Update progress bar when a file is saved
                    if DOWNLOAD_DIR in line:
                        pbar.update(1)
            
            process.wait()

            if process.returncode == 0:
                return "success"
            else:
                stderr_output = process.stderr.read()
                error_msg = stderr_output.lower()
                if "pixiv" in url.lower() and "'refresh-token' required" in error_msg:
                    get_pixiv_token(tokens)
                    continue
                elif "timed out" in error_msg or "connection" in error_msg:
                    print(f"[!] Connection error, will retry: {error_msg.strip()}")
                    continue
                else:
                    print(f"[!] Download failed: {error_msg.strip() or 'Unknown error'}")
                    continue

        except Exception as e:
            print(f"[!] An unexpected error occurred: {e}")
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
        if not line or line.startswith("#"):
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
