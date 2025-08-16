
import cloudscraper
from bs4 import BeautifulSoup
import os
import re
from threading import Thread, BoundedSemaphore
from time import sleep
from urllib.parse import urljoin
from pathlib import Path
from tqdm import tqdm

from ..tokens import save_tokens, load_tokens
from ..config import MAX_DOWNLOAD_THREADS

def remove_illegal_chars(filename):
    """Removes characters that are invalid for Windows filenames."""
    cleaned = re.sub(r'[\\/*?:",<>|]', "", filename)
    cleaned = cleaned.strip('. ')
    cleaned = cleaned[:150]
    return cleaned

def download_image_worker(session, url, path, semaphore, pbar, failed_downloads):
    """Worker thread to download a single image."""
    try:
        # Wnacg can be slow, so a longer timeout is helpful.
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            with open(path, 'wb') as f:
                f.write(response.content)
            pbar.update(1)
        else:
            print(f"Failed to download {url} - Status: {response.status_code}")
            failed_downloads.append(url)
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        failed_downloads.append(url)
    finally:
        semaphore.release()

def download_wnacg(url, tokens):
    """
    Downloads a gallery from wnacg.com by scraping the gallery page.
    This implementation is based on the logic from downloadREF.py.
    """
    scraper = cloudscraper.create_scraper()
    
    # 1. Extract ID and Title
    gallery_id_match = re.search(r'aid-(\d+)', url)
    if not gallery_id_match:
        print(f"[wnacg] Could not extract gallery ID from URL: {url}")
        return "failed"
    gallery_id = gallery_id_match.group(1)

    try:
        # Fetch the initial page to get the title
        response = scraper.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        title_element = soup.find('title')
        if not title_element:
            print("[wnacg] Could not find title")
            return "failed"
        title = remove_illegal_chars(title_element.text.strip().split('-')[0])
    except Exception as e:
        print(f"[wnacg] Failed to fetch title at {url}: {e}")
        return "failed"

    download_dir = Path("download") / "wnacg" / f"{gallery_id}_{title}".strip()
    os.makedirs(download_dir, exist_ok=True)

    # 2. Go to the gallery page to find image links
    gallery_url = url.replace('photos-slide-aid-', 'photos-gallery-aid-').replace('photos-index-aid-', 'photos-gallery-aid-')
    try:
        response = scraper.get(gallery_url)
        response.raise_for_status()
    except Exception as e:
        print(f"[wnacg] Failed to fetch gallery page at {gallery_url}: {e}")
        return "failed"

    # 3. Scrape image URLs using regex, as inspired by downloadREF.py
    # img5.qy0.ru/data/2729/72/17303302240576.jpg
    image_paths = re.findall(r'(img\d+\.qy0\.(?:com|org|net|ru)/data/.+?\.(?:jpg|png|gif|webp))', response.text)
    if not image_paths:
        print(f"[wnacg] Could not find any image links on gallery page: {gallery_url}")
        return "failed"

    image_urls = ['https://' + path for path in image_paths]

    # 4. Download images using a thread pool
    threads = []
    semaphore = BoundedSemaphore(MAX_DOWNLOAD_THREADS)
    failed_downloads = []
    print(f"({len(image_urls): 4} images) Downloading '{title}'")
    with tqdm(total=len(image_urls)) as pbar:
        for i, img_url in enumerate(image_urls):
            file_extension = Path(img_url).suffix
            file_path = download_dir / f"{i+1:03d}{file_extension}".strip()
            
            if os.path.exists(file_path):
                pbar.update(1)
                continue

            semaphore.acquire()
            thread = Thread(target=download_image_worker, args=(scraper, img_url, file_path, semaphore, pbar, failed_downloads))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

    if failed_downloads:
        print(f"[!] Failed to download {len(failed_downloads)} image(s).")
        return "failed"

    return "success"

if __name__ == '__main__':
    tokens = load_tokens()
    test_url = "https://www.wnacg.com/photos-slide-aid-196160.html"
    download_wnacg(test_url, tokens)
