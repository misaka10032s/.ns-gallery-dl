import cloudscraper
from bs4 import BeautifulSoup
import os
import re
from threading import Thread, BoundedSemaphore
from time import sleep
from urllib.parse import unquote
from pathlib import Path
from tqdm import tqdm

from ..tokens import save_tokens, load_tokens
from ..config import MAX_DOWNLOAD_THREADS

def get_nhentai_cookies(tokens):
    """Check for nhentai cookies or prompt user to log in."""
    if "nhentai_cookie" in tokens and tokens["nhentai_cookie"]:
        return tokens["nhentai_cookie"]
    
    # cloudscraper handles cloudflare, but a cookie might still be needed for login
    # For now, we assume cloudscraper is enough and we don't need to login
    return {}

def remove_illegal_chars(filename):
    """Removes characters that are invalid for filenames."""
    cleaned = re.sub(r'[\\/*?:",<>|]', '', filename)
    cleaned = cleaned.strip('. ')
    cleaned = cleaned[:150]
    return cleaned

def download_image_worker(session, url, path, semaphore, pbar, failed_downloads):
    try:
        response = session.get(url, timeout=10)
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

def download_nhentai(url, tokens):
    """Download nhentai content using requests and BeautifulSoup."""
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(url)
        if response.status_code != 200:
            print(f"[nhentai] Failed to access {url}, status code: {response.status_code}")
            if "cloudflare" in response.text.lower():
                 print("[nhentai] Cloudflare challenge failed.")
            return "failed"
    except Exception as e:
        print(f"[nhentai] Failed to access {url}: {e}")
        return "failed"

    soup = BeautifulSoup(response.text, 'lxml')
    
    title_element = soup.find('h1', class_='title')
    if not title_element:
        print("[nhentai] Could not find title")
        return "failed"
        
    title = remove_illegal_chars(title_element.text.strip())
    
    gallery_id_match = re.search(r'/g/(\d+)/', url)
    if not gallery_id_match:
        print(f"[nhentai] Could not extract gallery ID from URL: {url}")
        return "failed"
    
    gallery_id = gallery_id_match.group(1)
    download_dir = Path("download") / "nhentai" / f"{gallery_id}_{title}".strip()
    os.makedirs(download_dir, exist_ok=True)

    thumbnails = soup.find_all('a', class_='gallerythumb')
    if not thumbnails:
        print("[nhentai] Could not find image thumbnails.")
        return "failed"

    image_urls = []
    for thumb in thumbnails:
        img_tag = thumb.find('img')
        if not img_tag:
            continue
        
        thumb_url = img_tag.get('data-src')
        if not thumb_url:
            continue

        # Convert thumbnail URL to full image URL
        # e.g. //t1.nhentai.net/galleries/3452010/40t.jpg.webp -> //i2.nhentai.net/galleries/3452010/40.jpg
        # //t1.nhentai.net/galleries/3452010/7t.webp -> //i2.nhentai.net/galleries/3452010/7.webp
        # //t9.nhentai.net/galleries/3483246/7t.webp -> //i9.nhentai.net/galleries/3483246/7.webp

        # trans t to i
        full_image_url = re.sub(r'//t(\d+)\.nhentai\.net', r'//i\1.nhentai.net', thumb_url)
        # trans 123t.sub1.sub2 to 123.sub1
        fileName = full_image_url.split('/')[-1]
        number = re.search(r'(\d+)t', fileName)
        subName = fileName.split('.')[1:][0]
        if number:
            full_image_url = full_image_url.replace(fileName, '') + f"{number.group(1)}.{subName}"

        if full_image_url.startswith('//'):
            full_image_url = 'https:' + full_image_url

        # print(f"[nhentai] Found image URL: {full_image_url}")
        
        image_urls.append(full_image_url)

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
        print(f"\n[!] Failed to download {len(failed_downloads)} image(s).")
        return "failed"

    return "success"

if __name__ == '__main__':
    tokens = load_tokens()
    test_url = "https://nhentai.net/g/334431/" 
    download_nhentai(test_url, tokens)
