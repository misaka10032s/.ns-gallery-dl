from __future__ import annotations

import re
from pathlib import Path
from threading import BoundedSemaphore, Thread

import cloudscraper
from bs4 import BeautifulSoup
from tqdm import tqdm


def fetch_gallery_metadata(gallery_id: str, scraper=None) -> dict:
    """Fetch a nhentai gallery page and return ITS OWN structured fields —
    the clean title (span.pretty inside h1.title — not the bracket-wrapped
    "[circle (artist)] title [tags]" the h1's full .text would give, which
    is the same lossy string the folder name already carries), the
    Artists:/Groups: tag-container names, and the Pages: count — rather
    than re-deriving any of it from the folder name. This is deliberately
    the ONLY source of title/artist/circle for doujin books that support a
    fetch (app.services.doujin_meta_service) — the folder name is never
    parsed for this.

    Raises LookupError if the gallery doesn't exist (404), RuntimeError if
    the page loaded but doesn't look like a real gallery page (e.g. a
    Cloudflare challenge page with no #info block), or lets network
    exceptions (timeout, connection error, non-2xx via raise_for_status)
    propagate — callers (doujin_meta_service) classify all of these."""
    owns_scraper = scraper is None
    if owns_scraper:
        scraper = cloudscraper.create_scraper()

    url = f"https://nhentai.net/g/{gallery_id}/"
    response = scraper.get(url, timeout=15)
    if response.status_code == 404:
        raise LookupError(f"nhentai gallery {gallery_id} not found")
    response.raise_for_status()
    response.encoding = "utf-8"

    soup = BeautifulSoup(response.text, "lxml")
    info = soup.find("div", id="info")
    if info is None:
        raise RuntimeError("nhentai gallery page missing #info block (likely a challenge/blocked page)")

    h1 = info.find("h1", class_="title")
    pretty = h1.find("span", class_="pretty") if h1 else None
    title = pretty.get_text(strip=True) if pretty else ""
    if not title:
        raise RuntimeError("nhentai gallery page missing its title")

    fields: dict[str, list[str]] = {}
    for container in info.find_all("div", class_="tag-container"):
        label = (container.find(string=True, recursive=False) or "").strip().rstrip(":")
        names = [span.get_text(strip=True) for span in container.find_all("span", class_="name")]
        fields[label] = names

    artist = " / ".join(fields.get("Artists", []))
    circle = " / ".join(fields.get("Groups", []))
    pages_raw = fields.get("Pages", [])
    page_count = int(pages_raw[0]) if pages_raw and pages_raw[0].isdigit() else None

    return {
        "title": title,
        "artist": artist,
        "circle": circle,
        "page_count": page_count,
        "source_url": url,
    }


def _remove_illegal_chars(filename: str) -> str:
    cleaned = re.sub(r'[\\/*?:",<>|]', "", filename)
    cleaned = cleaned.strip(". ")
    return cleaned[:150]


def _download_image_worker(session, url: str, path: Path, semaphore: BoundedSemaphore, pbar: tqdm, failed: list[str]) -> None:
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            path.write_bytes(response.content)
            pbar.update(1)
        else:
            failed.append(url)
    except Exception:
        failed.append(url)
    finally:
        semaphore.release()


def download_nhentai(url: str, output_root: Path, max_threads: int = 5) -> str:
    scraper = cloudscraper.create_scraper()
    try:
        response = scraper.get(url)
        if response.status_code != 200:
            return "failed"
        response.encoding = "utf-8"
    except Exception:
        return "failed"

    soup = BeautifulSoup(response.text, "lxml")
    title_el = soup.find("h1", class_="title")
    gallery_id_match = re.search(r"/g/(\d+)/", url)
    if not title_el or not gallery_id_match:
        return "failed"

    gallery_id = gallery_id_match.group(1)
    title = _remove_illegal_chars(title_el.text.strip())
    download_dir = output_root / f"{gallery_id}_{title}"
    download_dir.mkdir(parents=True, exist_ok=True)

    image_urls: list[str] = []
    for thumb in soup.find_all("a", class_="gallerythumb"):
        img_tag = thumb.find("img")
        thumb_url = None
        if img_tag:
            thumb_url = img_tag.get("data-src") or img_tag.get("src")
        if not thumb_url:
            continue
        full = re.sub(r"//t(\d+)\.nhentai\.net", r"//i\1.nhentai.net", thumb_url)
        file_name = full.split("/")[-1]
        number = re.search(r"(\d+)t", file_name)
        suffix_parts = file_name.split(".")
        suffix = suffix_parts[1] if len(suffix_parts) > 1 else "jpg"
        if number:
            full = f"{full.rsplit('/', 1)[0]}/{number.group(1)}.{suffix}"
        if full.startswith("//"):
            full = f"https:{full}"
        image_urls.append(full)

    if not image_urls:
        return "failed"

    failed: list[str] = []
    semaphore = BoundedSemaphore(max_threads)
    threads: list[Thread] = []
    with tqdm(total=len(image_urls), desc="Downloading", unit="file") as pbar:
        for index, image_url in enumerate(image_urls, start=1):
            target = download_dir / f"{index:03d}{Path(image_url).suffix}"
            if target.exists():
                pbar.update(1)
                continue
            semaphore.acquire()
            thread = Thread(
                target=_download_image_worker,
                args=(scraper, image_url, target, semaphore, pbar, failed),
                daemon=True,
            )
            threads.append(thread)
            thread.start()
        for thread in threads:
            thread.join()

    return "failed" if failed else "success"
