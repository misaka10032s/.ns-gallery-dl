from __future__ import annotations

import re
from pathlib import Path
from threading import BoundedSemaphore, Thread

import cloudscraper
from bs4 import BeautifulSoup
from tqdm import tqdm

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

MAX_THREADS = 5


def _remove_illegal_chars(value: str) -> str:
    cleaned = re.sub(r'[\\/*?:",<>|]', "", (value or "").strip())
    cleaned = cleaned.strip(". ")
    return cleaned[:150]


def _scraper() -> cloudscraper.CloudScraper:
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )


def _download_worker(
    session: cloudscraper.CloudScraper,
    url: str,
    dest: Path,
    semaphore: BoundedSemaphore,
    pbar: tqdm,
    failed: list[str],
) -> None:
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200:
            dest.write_bytes(resp.content)
            pbar.update(1)
        else:
            failed.append(url)
    except Exception:
        failed.append(url)
    finally:
        semaphore.release()


def _download_images(
    scraper: cloudscraper.CloudScraper,
    image_urls: list[str],
    dest_dir: Path,
    desc: str = "Downloading",
) -> bool:
    """Download a list of image URLs into dest_dir using thread pool.  Returns True on full success."""
    if not image_urls:
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    semaphore = BoundedSemaphore(MAX_THREADS)
    threads: list[Thread] = []
    with tqdm(total=len(image_urls), desc=desc, unit="img") as pbar:
        for idx, url in enumerate(image_urls, start=1):
            ext = Path(url.split("?")[0]).suffix or ".jpg"
            dest = dest_dir / f"{idx:04d}{ext}"
            if dest.exists():
                pbar.update(1)
                continue
            semaphore.acquire()
            t = Thread(
                target=_download_worker,
                args=(scraper, url, dest, semaphore, pbar, failed),
                daemon=True,
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
    return len(failed) == 0


def _extract_images_from_article(article_div) -> list[str]:
    """Extract image URLs from a Bahamut article div."""
    urls: list[str] = []
    for img in article_div.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if src and src.startswith("http"):
            urls.append(src)
    return urls


def _is_co_php(url: str) -> bool:
    """Return True if the URL is a Co.php single-post URL.

    Detects by path containing Co.php, or by query having sn= without snA=.
    Pure function — no I/O — so it is unit-testable in isolation.

    Examples:
        https://forum.gamer.com.tw/Co.php?bsn=74934&sn=83404  → True
        https://forum.gamer.com.tw/C.php?bsn=74934&snA=83404  → False
    """
    if re.search(r"/Co\.php", url):
        return True
    has_sn = bool(re.search(r"[?&]sn=", url))
    has_snA = bool(re.search(r"[?&]snA=", url))
    return has_sn and not has_snA


def _get_total_pages(soup: BeautifulSoup) -> int:
    """Return total number of pages from pagination element. Returns 1 if not found."""
    pagination = soup.find("p", class_="BH-pagebtnA")
    if not pagination:
        return 1
    page_links = pagination.find_all("a")
    if not page_links:
        return 1
    try:
        return int(page_links[-1].get_text(strip=True))
    except (ValueError, TypeError):
        return 1


def _page_url(base_url: str, page: int) -> str:
    if page == 1:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}page={page}"


def download_bahamut(url: str, output_root: Path) -> str:
    """
    Download images from a Bahamut forum article.

    Supports:
    - Co.php single-post URLs — folder named ``baha_co_{sn}_{title}``
    - C.php thread URLs — multi-page, folder named ``baha_{snA}_{title}``

    Returns 'success' or 'failed'.
    """
    scraper = _scraper()

    try:
        resp = scraper.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return "failed"
    except Exception:
        return "failed"

    soup = BeautifulSoup(resp.text, "lxml")

    # ── Co.php single-post mode ────────────────────────────────────────────
    if _is_co_php(url):
        title_el = soup.find("h1", class_="c-post__header__title")
        if not title_el:
            return "failed"
        title = _remove_illegal_chars(title_el.get_text(strip=True))

        sn_match = re.search(r"[?&]sn=(\d+)", url)
        sn = sn_match.group(1) if sn_match else "0"
        download_dir = output_root / f"baha_co_{sn}_{title}"

        # Take ONLY the first c-article__content div (post body).
        # Later divs belong to the comment section and carry thumbnail URLs
        # (e.g. ?w=300&h=300&fit=o) that must NOT be downloaded.
        articles = soup.find_all("div", class_="c-article__content")
        if not articles:
            return "failed"
        image_urls = _extract_images_from_article(articles[0])

        if not image_urls:
            return "failed"

        success = _download_images(
            scraper, image_urls, download_dir, desc=f"Bahamut Co: {title[:40]}"
        )
        return "success" if success else "failed"

    # ── C.php thread mode (original behavior, unchanged) ──────────────────

    # Must have pagination marker to confirm this is a valid thread page
    if not soup.find("p", class_="BH-pagebtnA"):
        return "failed"

    title_el = soup.find("h1", class_="c-post__header__title")
    if not title_el:
        return "failed"
    title = _remove_illegal_chars(title_el.get_text(strip=True))

    # Derive a unique folder name from URL + title
    snA_match = re.search(r"snA=(\d+)", url)
    folder_prefix = f"baha_{snA_match.group(1)}_" if snA_match else "baha_"
    download_dir = output_root / f"{folder_prefix}{title}"
    download_dir.mkdir(parents=True, exist_ok=True)

    total_pages = _get_total_pages(soup)
    all_image_urls: list[str] = []

    for page in range(1, total_pages + 1):
        if page == 1:
            page_soup = soup
        else:
            try:
                page_resp = scraper.get(_page_url(url, page), headers=HEADERS, timeout=30)
                if page_resp.status_code != 200:
                    continue
                page_soup = BeautifulSoup(page_resp.text, "lxml")
            except Exception:
                continue

        # First article on each page = OP / main post
        articles = page_soup.find_all("div", class_="c-article__content")
        if articles:
            all_image_urls.extend(_extract_images_from_article(articles[0]))

    if not all_image_urls:
        return "failed"

    success = _download_images(scraper, all_image_urls, download_dir, desc=f"Bahamut: {title[:40]}")
    return "success" if success else "failed"
