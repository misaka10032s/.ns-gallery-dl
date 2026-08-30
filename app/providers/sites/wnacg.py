from __future__ import annotations

import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import cloudscraper
from bs4 import BeautifulSoup
from tqdm import tqdm

try:
    import py7zr
except ImportError:  # pragma: no cover
    py7zr = None

try:
    import rarfile
except ImportError:  # pragma: no cover
    rarfile = None


HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "ja-JP,ja;q=0.9,zh-TW;q=0.8,en-US;q=0.6",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}


def _sanitize_chars(value: str) -> str:
    cleaned = re.sub(r'[\\/*?:",<>|]', "", value)
    return cleaned.strip(". ")


def _remove_illegal_chars(filename: str, max_length: int = 150) -> str:
    """Sanitize a string for use as a path component — plain-slice truncation.

    Used ONLY for the gallery title (no extension to preserve). Do NOT reuse this
    for the archive filename — see `_sanitize_archive_filename` below, which is
    deliberately a SEPARATE function so extension-preserving truncation never
    silently changes this one's (title's) behaviour.
    """
    return _sanitize_chars(filename)[:max_length]


def _sanitize_archive_filename(filename: str, max_length: int = 150) -> str:
    """Sanitize an archive filename for use as a path component, preserving a
    trailing extension when truncating (dot followed by <=10 chars, e.g.
    `.zip`/`.7z`/`.rar`) — `download_wnacg` needs the suffix intact to pick the
    right extraction branch. Deliberately NOT shared with `_remove_illegal_chars`
    (the gallery-title sanitizer): a title that happens to end in something
    extension-shaped must still get a plain slice, not this treatment.
    """
    cleaned = _sanitize_chars(filename)
    if len(cleaned) <= max_length:
        return cleaned
    stem, dot, suffix = cleaned.rpartition(".")
    if dot and 0 < len(suffix) <= 10:
        keep = max_length - len(suffix) - 1
        if keep > 0:
            return f"{stem[:keep]}.{suffix}"
    return cleaned[:max_length]


def _parse_config(soup: BeautifulSoup) -> tuple[str, str, str] | None:
    """Parse the page's `const CONFIG = {...}` script block.

    Returns `(worker_api, file_key, file_name)`, or `None` if the block is absent
    or doesn't match the expected shape (page layout changed).
    """
    scripts = soup.find_all("script")
    config_script = next((script.string for script in scripts if script.string and "const CONFIG = {" in script.string), None)
    if not config_script:
        return None
    try:
        worker_api = re.search(r'WORKER_API:\s*"(.*?)"', config_script).group(1)
        file_key = re.search(r'FILE_KEY:\s*"(.*?)"', config_script).group(1)
        file_name = re.search(r'FILE_NAME:\s*"(.*?)"', config_script).group(1)
    except AttributeError:
        return None
    return worker_api, file_key, file_name


def _config_link(worker_api: str, file_key: str, file_name: str, scraper) -> str | None:
    """POST to the Cloudflare Worker API for the primary download link.

    Any network/HTTP/JSON failure (incl. a Cloudflare challenge 403 on the worker
    endpoint) is left to propagate — the caller degrades to `_fallback_link`.
    """
    response = scraper.post(
        worker_api,
        json={"file_key": file_key, "file_name": file_name},
        headers={
            **scraper.headers,
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.wnacg.com",
            "Referer": "https://www.wnacg.com/",
        },
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        return None
    return data.get("url")


def _fallback_link(soup: BeautifulSoup, file_name: str | None) -> tuple[str | None, str | None]:
    """Server-2 fallback link. `file_name` should come from the page's CONFIG block
    (passed in by the caller) — the old `p.download_filename` element this used to
    scrape no longer exists on the live page, which silently produced the literal
    `"wnacg_archive.zip"` for every download."""
    server2 = soup.find("span", string=re.compile(r"備用線路\s*\(Server 2\)"))
    if server2:
        link = server2.find_parent("a")
        if link and link.get("href"):
            return urljoin("https:", link.get("href")), file_name or "wnacg_archive.zip"
    return None, None


def download_wnacg(url: str, output_root: Path) -> str:
    scraper = cloudscraper.create_scraper()
    gallery_id_match = re.search(r"aid-(\d+)", url)
    if not gallery_id_match:
        return "failed"

    gallery_id = gallery_id_match.group(1)
    try:
        response = scraper.get(url, headers=HEADERS)
        response.raise_for_status()
    except Exception:
        return "failed"

    soup = BeautifulSoup(response.text, "lxml")
    title_el = soup.find("title")
    if not title_el:
        return "failed"

    title = _remove_illegal_chars(title_el.text.strip().split("-")[0])
    download_dir = output_root / f"{gallery_id}_{title}"
    download_dir.mkdir(parents=True, exist_ok=True)

    gallery_url = url.replace("photos-slide-aid-", "download-index-aid-").replace("photos-index-aid-", "download-index-aid-")
    try:
        response = scraper.get(gallery_url, headers=HEADERS)
        response.raise_for_status()
    except Exception:
        return "failed"

    soup = BeautifulSoup(response.text, "lxml")
    config = _parse_config(soup)
    download_link: str | None = None
    archive_filename: str | None = config[2] if config else None
    if config:
        worker_api, file_key, file_name = config
        try:
            download_link = _config_link(worker_api, file_key, file_name, scraper)
        except Exception as exc:
            print(f"[wnacg] CONFIG API 取得下載連結失敗，改用備用線路: {exc}")
            download_link = None
    if not download_link:
        download_link, archive_filename = _fallback_link(soup, archive_filename)
    if not download_link or not archive_filename:
        return "failed"

    archive_filename = _sanitize_archive_filename(archive_filename)
    archive_path = download_dir / archive_filename
    if not archive_path.exists():
        try:
            response = scraper.get(download_link, stream=True, timeout=60)
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))
            with archive_path.open("wb") as handle, tqdm(total=total_size, unit="iB", unit_scale=True, desc="Downloading") as pbar:
                for chunk in response.iter_content(chunk_size=1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    pbar.update(len(chunk))
        except Exception:
            return "failed"

    suffix = archive_path.suffix.lower()
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(download_dir)
        elif suffix == ".7z" and py7zr:
            with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                archive.extractall(path=download_dir)
        elif suffix == ".rar" and rarfile:
            with rarfile.RarFile(archive_path, "r") as archive:
                archive.extractall(path=download_dir)
    except Exception:
        return "failed"

    return "success"
