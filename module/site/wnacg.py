import cloudscraper
from bs4 import BeautifulSoup
import os
import re
from threading import Thread, BoundedSemaphore
from time import sleep
from urllib.parse import urljoin
from pathlib import Path
from tqdm import tqdm
import zipfile
import io
import json

# Imports for multi-format archive support
try:
    import py7zr
except ImportError:
    py7zr = None
try:
    import rarfile
except ImportError:
    rarfile = None

from ..tokens import save_tokens, load_tokens
from ..config import MAX_DOWNLOAD_THREADS

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "ja-JP,ja;q=0.9,zh-TW;q=0.8,zh;q=0.7,en-US;q=0.6,en;q=0.5,zh-CN;q=0.4",
    "cache-control": "no-cache",
    "cookie": "X_CACHE_KEY=9aa9086a3fafb3797b9ec284a06144b1; _cfuvid=whz4jN29ZLES7PJ1mbhVX89U4HPKfs4J3grjzsxyUrM-1772711299.0108857-1.0.1.1-4_QtHtslpkyJ8j5kRXf.f2gpSsRR8oC_xfZMDl4dc3c",
    "pragma": "no-cache",
    "priority": "u=0, i",
    "sec-ch-ua": "\"Not(A:Brand\";v=\"8\", \"Chromium\";v=\"144\", \"Google Chrome\";v=\"144\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
}

def remove_illegal_chars(filename):
    """Removes characters that are invalid for Windows filenames."""
    cleaned = re.sub(r'[\\/*?:",<>|]', "", filename)
    cleaned = cleaned.strip('. ')
    cleaned = cleaned[:150]
    return cleaned

def getResourceUrl_1(soup, scraper):
    scripts = soup.find_all('script')
    config_script = None
    for script in scripts:
        if script.string and "const CONFIG = {" in script.string:
            config_script = script.string
            break
            
    if not config_script:
        return None, None

    try:
        worker_api = re.search(r'WORKER_API:\s*"(.*?)"', config_script).group(1)
        file_key = re.search(r'FILE_KEY:\s*"(.*?)"', config_script).group(1)
        file_name = re.search(r'FILE_NAME:\s*"(.*?)"', config_script).group(1)
    except AttributeError:
         return None, None

    archive_filename = file_name
    
    # Request download link
    try:
        print(f'[debug] worker_api: {worker_api}, file_key: {file_key}, file_name: {file_name}')
        
        # Prepare headers for the API request based on the scraper's current headers
        api_headers = scraper.headers.copy()
        api_headers.update({
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.wnacg.com",
            "Referer": "https://www.wnacg.com/",
            "Priority": "u=1, i",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
        })

        api_response = scraper.post(
            worker_api,
            json={"file_key": file_key, "file_name": file_name},
            headers=api_headers
        )
        api_response.raise_for_status()
        api_data = api_response.json()
        
        if not api_data.get('success'):
             print(f"[wnacg] API request failed: {api_data.get('msg')}")
             return None, None
             
        return api_data.get('url'), archive_filename
    except Exception as e:
        print(f"[wnacg] Failed to get download link from API: {e}")
        return None, None

def getResourceUrl_2(soup, url):
    # Try to find the backup download button (Server 2)
    # Target: <button ...><a class="ads" href="..."><span>備用線路 (Server 2)</span></a></button>
    
    # Strategy 1: Find by button text content
    server2_span = soup.find('span', string=re.compile(r'備用線路\s*\(Server 2\)'))
    if server2_span:
        link_tag = server2_span.find_parent('a')
        if link_tag and link_tag.get('href'):
             download_link = link_tag.get('href')
             if not download_link.startswith('http'):
                download_link = urljoin('https:', download_link)
             
             # Need to find filename separately since it's not in the button
             filename_p = soup.find('p', class_='download_filename')
             archive_filename = filename_p.text.strip() if filename_p else "wnacg_archive.zip"
             return download_link, archive_filename

    # Strategy 2: Find by class structure if text fails
    ads_link = soup.find('a', class_='ads', href=True)
    if ads_link and "備用線路" in ads_link.get_text():
        download_link = ads_link.get('href')
        if not download_link.startswith('http'):
            download_link = urljoin('https:', download_link)
        
        filename_p = soup.find('p', class_='download_filename')
        archive_filename = filename_p.text.strip() if filename_p else "wnacg_archive.zip"
        return download_link, archive_filename

    return None, None

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
        response = scraper.get(url, headers=headers)
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
    gallery_url = url.replace('photos-slide-aid-', 'download-index-aid-').replace('photos-index-aid-', 'download-index-aid-')
    try:
        response = scraper.get(gallery_url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f"[wnacg] Failed to fetch gallery page at {gallery_url}: {e}")
        return "failed"

    # 3. Scrape download URL and filename for the archive
    soup = BeautifulSoup(response.text, 'lxml')
    
    # Try method 1: API Config
    download_link, archive_filename = getResourceUrl_1(soup, scraper)
    
    # Try method 2: Backup Button if method 1 failed
    if not download_link:
        print("[wnacg] Method 1 failed or not available. Trying Method 2 (Backup Server)...")
        download_link, archive_filename = getResourceUrl_2(soup, gallery_url)
    
    if not download_link:
        print(f"[wnacg] Could not find valid download link on page: {gallery_url}")
        return "failed"

    archive_path = download_dir / archive_filename

    # 4. Download and extract archive
    if os.path.exists(archive_path):
        print(f"'{archive_filename}' already downloaded. Skipping.")
        return "success"

    print(f"Downloading '{archive_filename}'...")
    try:
        response = scraper.get(download_link, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(archive_path, 'wb') as f, tqdm(
            total=total_size, unit='iB', unit_scale=True, desc='Downloading'
        ) as pbar:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))

    except Exception as e:
        print(f"Failed to download {archive_filename}: {e}")
        return "failed"

    print(f"Extracting '{archive_filename}'...")
    try:
        file_ext = Path(archive_filename).suffix.lower()

        # Supported formats: .zip, .7z, .rar (requires unrar command-line tool in PATH)
        if file_ext == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as archive:
                archive.extractall(download_dir)
        elif file_ext == '.7z':
            if py7zr:
                with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                    archive.extractall(path=download_dir)
            else:
                print("[wnacg] Error: py7zr library not installed. Please run 'pip install py7zr'")
                return "failed"
        elif file_ext == '.rar':
            if rarfile:
                try:
                    with rarfile.RarFile(archive_path, 'r') as archive:
                        archive.extractall(path=download_dir)
                except rarfile.RarCannotExec as e:
                    print(f"[wnacg] Error: Failed to extract RAR. Ensure 'unrar' command-line tool is installed and in your PATH. Details: {e}")
                    return "failed"
            else:
                print("[wnacg] Error: rarfile library not installed. Please run 'pip install rarfile'")
                return "failed"
        else:
            print(f"[wnacg] Error: Unsupported archive format '{file_ext}'. Cannot extract.")
            # We don't return "failed" here, as the download itself was successful.
            # The user can manually extract the file.
            return "success"

        print(f"Successfully extracted to '{download_dir}'")
    except Exception as e:
        print(f"[wnacg] Failed to extract archive {archive_path}: {e}")
        return "failed"

    return "success"

if __name__ == '__main__':
    tokens = load_tokens()
    test_url = "https://www.wnacg.com/photos-slide-aid-196160.html"
    download_wnacg(test_url, tokens)
