from __future__ import annotations

import re
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

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


_SCHEME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.-]*://')

# A port is 1-5 decimal digits (RFC 3986 §3.2.3 places no upper bound, but
# a real port never exceeds 65535 -- 5 digits is a safe, simple shape test).
_PORT_RE = re.compile(r'^[0-9]{1,5}$')


def _authority_boundary(rest: str) -> int:
    """Index in `rest` (the text right after `scheme://`) where the RFC 3986
    authority component ends: the FIRST subsequent `/`, `?` or `#`. Returns
    `len(rest)` if none of those appear (the whole remainder is authority).
    Nothing at or past this index is ever userinfo."""
    boundary = len(rest)
    for marker in ("/", "?", "#"):
        pos = rest.find(marker)
        if pos != -1 and pos < boundary:
            boundary = pos
    return boundary


def _authority_tail_after_bracket(authority: str) -> tuple[int, str]:
    """Split a leading IPv6-literal bracket pair (`[::1]`, `[2001:db8::1]`)
    off `authority`, returning `(bracket_len, tail)`. An IPv6 address is
    full of colons that are part of the address, never a host:port or
    user:pass separator -- callers that scan for a boundary colon must
    exclude the bracket first, or `[2001:db8::1]:8443` misreads the FIRST
    colon inside the brackets as that separator."""
    if authority.startswith("["):
        close = authority.find("]")
        bracket_len = close + 1 if close != -1 else len(authority)
    else:
        bracket_len = 0
    return bracket_len, authority[bracket_len:]


def _replace_userinfo(userinfo: str) -> str:
    """`user` -> `[@acc]`; `user:pass` -> `[@acc]:[@pw]` -- the owner's rule
    (2026-09-02, verbatim): 「帳號密碼一律不顯示，用[@acc], [@pw] 之類的來
    取代」. Split on the FIRST `:` only: even if the "password" half itself
    contains an embedded `:` or `@` (a D5 malformed-userinfo shape), the
    whole remainder still collapses into the single `[@pw]` placeholder --
    still biased to over-redact WITHIN a genuine credential region, exactly
    like the previous full-deletion behaviour was."""
    if ":" in userinfo:
        return "[@acc]:[@pw]"
    return "[@acc]"


def _redact_authority(url_without_query: str) -> str:
    """Replace ONLY a URL's userinfo with a placeholder -- never delete or
    rewrite the host, port, path, or filename. Owner's rule (2026-09-02,
    verbatim): 「帳號密碼一律不顯示，用[@acc], [@pw] 之類的來取代，但其他
    包含原因 目標 網址之類的一定要顯示」. A username becomes `[@acc]`, a
    password becomes `[@pw]`; everything else survives because it is never
    deleted in the first place -- only the userinfo substring is ever
    overwritten.

    This SUPERSEDES three rounds of a different design (delete userinfo,
    keep only host): "last `@` anywhere" (R3-1) -> "`:` before the first
    `/`" (R4-1/R4-2) -> this. Both prior heuristics scanned PAST the RFC
    3986 authority boundary looking for a userinfo `@`, and so could
    fabricate a wrong host and destroy the real host/path/filename whenever
    the URL PATH itself legally contained an `@` (a site-supplied filename
    like `AB@CD.zip`) or the authority carried an explicit port / IPv6
    literal. Placeholder substitution cannot repeat that failure class,
    because the host is never removed to begin with.

    RFC 3986 structure, strictly:
    - The **authority** is the text between `scheme://` and the FIRST
      subsequent `/`, `?` or `#`. Nothing after that boundary is EVER
      userinfo -- an `@` in the path (`AB@CD.zip`, `/user@1/`, or a
      path-shaped suffix like `;admin@evil.example`) is left alone.
    - Inside the authority only, the LAST `@` separates userinfo from host.
    - An authority with no `@` at all is left untouched -- UNLESS it is the
      one malformed shape this module deliberately still supports: an
      unencoded `/` inside a would-be password (`user:PASS/WORD@host...`)
      pushes the real `@` past the RFC boundary, truncating the visible
      authority to `user:PASS`. There, a `:` whose right-hand side is NOT
      port-shaped (`^[0-9]{1,5}$`) cannot be a port, so it is read as a
      credential and that right-hand side alone becomes `[@pw]` -- the text
      after the erroneous `/` (`/WORD@host...`) is NOT further inspected;
      RFC treats it as path, and it is left alone, per the owner's own
      worked example (`user:PASS/WORD@host...` -> `user:[@pw]/WORD@host...`).
      An IPv6 literal's bracket is excluded from this port check before it
      runs, since its own colons belong to the address, not a separator.
    - A bare `@` with nothing before it (`https://@host/path`) has no
      username or password VALUE to hide, so there is nothing to replace:
      the empty userinfo and its `@` are both dropped, leaving just the
      host. (A documented decision, not an inferred one -- see the fix
      report: replacing an empty string with `[@acc]` would imply a
      credential existed when none did.)
    """
    scheme_match = _SCHEME_RE.match(url_without_query)
    if not scheme_match:
        return url_without_query
    scheme_part = scheme_match.group(0)
    rest = url_without_query[len(scheme_part):]
    boundary = _authority_boundary(rest)
    authority = rest[:boundary]
    remainder = rest[boundary:]

    if "@" in authority:
        at = authority.rfind("@")
        userinfo, host_port = authority[:at], authority[at + 1:]
        new_authority = host_port if userinfo == "" else _replace_userinfo(userinfo) + "@" + host_port
        return scheme_part + new_authority + remainder

    # No '@' within the RFC-strict authority -- the one malformed exception:
    # an unencoded '/' inside a would-be password truncated the authority
    # early (D5). Detect it via a non-port-shaped colon, IPv6 brackets
    # excluded from the check.
    bracket_len, tail = _authority_tail_after_bracket(authority)
    if ":" in tail:
        head, _sep, candidate = tail.rpartition(":")
        if not _PORT_RE.match(candidate):
            new_authority = authority[:bracket_len] + head + ":[@pw]"
            return scheme_part + new_authority + remainder

    return url_without_query


def _strip_url_query(url: str) -> str:
    """Drop a URL's query string, fragment, AND userinfo credentials — used to
    keep a presigned Server-2 / CONFIG-API download URL's signed token (or any
    embedded `user:pass@` credential) out of any error message this module
    surfaces (`jobs.error` / `history_entries.meta.error`, both rendered
    verbatim in the Web UI)."""
    without_fragment = url.split("#", 1)[0]
    without_query = without_fragment.split("?", 1)[0]
    return _redact_authority(without_query)


# Matches any absolute http(s) URL substring found anywhere in an exception
# message — deliberately NOT anchored to a caller-supplied URL, because
# `requests.exceptions.HTTPError.__str__()` embeds `response.url` (the FINAL,
# post-redirect URL), which can differ entirely from the `download_link`
# string the caller passed to `.get()` (e.g. a Server-2 link that 302s to a
# CDN mirror carrying its own signed token). Relying on a caller-supplied
# `urls=` allowlist alone lets that redirected URL's token pass through
# unredacted. This also naturally covers multiple distinct URLs appearing in
# one message (each match is redacted independently).
_ABSOLUTE_URL_RE = re.compile(r'https?://[^\s"\'<>]+', re.IGNORECASE)

# Matches a bare `/path?query` fragment with no scheme/host — the shape
# urllib3's own lower-level connection-error messages use (e.g. "Max retries
# exceeded with url: /dl/abc?token=..."), which `_ABSOLUTE_URL_RE` cannot
# match since there is no `https?://` prefix. The lookbehind requires the
# `/` to be preceded by whitespace/start-of-string OR one of `:`, `(`, `'`,
# `"` — the punctuation a wrapped exception's own str() commonly puts right
# before an embedded path (`url:/dl/abc?...`, `(/dl/abc?...)`) — WITHOUT
# opening it up to match a slash embedded mid-word in ordinary prose (a
# slash preceded by any other non-whitespace character still fails to match).
_PATH_QUERY_RE = re.compile(r"""(?:(?<!\S)|(?<=[:('"]))(/[^\s"'<>]*\?[^\s"'<>]+)""")


def _redact_absolute_url(match: re.Match[str]) -> str:
    return _strip_url_query(match.group(0))


def _redact_path_query(match: re.Match[str]) -> str:
    return match.group(0).split("?", 1)[0]


def _sanitize_error(message: str, *, urls: tuple[str, ...] = (), paths: tuple[Path, ...] = ()) -> str:
    """Redact sensitive values a wrapped exception's `str()` may have embedded
    verbatim, before the message is returned as `(status, error)` and stored
    in `jobs.error` / `history_entries.meta.error` for display.

    Two layers, applied in order:

    1. **Blanket scan (primary defence).** Any `https?://...` substring found
       ANYWHERE in `message` has its query string, fragment, AND userinfo
       credentials stripped — regardless of whether it matches a caller-
       supplied `urls=` entry. This is what makes a REDIRECTED URL's token
       (never named in `urls=`, since the caller only knows the pre-redirect
       `download_link`) and multiple distinct URLs in one message both safe.
       A bare `/path?query` (no scheme — urllib3's connection-error shape)
       is handled by a second, narrower pass.
    2. **Caller-supplied `urls=`/`paths=` (defense-in-depth, kept for the
       exact values the caller already knows are sensitive).** `paths`
       reduces a local filesystem `Path` that may appear in a filesystem/
       archive-extraction exception's message to its basename only — this
       has no URL-like shape, so it is NOT covered by the blanket scan above
       and still needs the caller to name it explicitly.

    **`paths=` element ORDER is load-bearing (R3-6): list the FILE before its
    DIRECTORY, e.g. `paths=(archive_path, download_dir)`, never the reverse.**
    Each path is replaced by its basename in sequence, and `download_dir` is
    itself a path SEGMENT of `archive_path` (`archive_path == download_dir /
    archive_filename`). If the directory is replaced first, the message's
    `download_dir` substring becomes `download_dir.name` while the remaining
    text still holds `archive_path` with its ORIGINAL (unreplaced) directory
    prefix — so the later `archive_path` replacement can no longer find an
    exact match, and a stale `<dirname>\\<filename>` fragment (e.g.
    `1_T\\MYARCHIVE.zip`) survives in the output instead of the clean
    basename. Listing the file first consumes the full `archive_path` string
    before the directory pass has any chance to fragment it.
    """
    sanitized = _ABSOLUTE_URL_RE.sub(_redact_absolute_url, message)
    sanitized = _PATH_QUERY_RE.sub(_redact_path_query, sanitized)
    for url in urls:
        if not url:
            continue
        sanitized = sanitized.replace(url, _strip_url_query(url))
        query = urlsplit(url).query
        if query:
            sanitized = sanitized.replace(f"?{query}", "")
    for path in paths:
        path_str = str(path)
        if path_str:
            sanitized = sanitized.replace(path_str, path.name)
            # `OSError.__str__()` formats its `filename` argument via `%r`
            # (repr), which on Windows doubles every backslash in the path
            # (`C:\Users\x` -> the two-character sequence `\\` for each `\`
            # inside the resulting message text). A plain-string replace of
            # the single-backslash form never matches that doubled form, so
            # the raw path would otherwise survive verbatim in exactly the
            # OSError case D1 exists to close (disk-full / permission-denied
            # during archive write) — confirmed by direct reproduction, not
            # assumed: `str(OSError(28, "...", path_str))` measurably
            # contains twice as many backslash characters as `path_str`.
            doubled = path_str.replace("\\", "\\\\")
            if doubled != path_str:
                sanitized = sanitized.replace(doubled, path.name)
    return sanitized


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


def download_wnacg(url: str, output_root: Path) -> tuple[str, str]:
    """Returns `(status, error)` — `error` is `""` on success, otherwise a
    zh-TW reason distinguishing WHICH stage failed (see module docstring-level
    comment above each branch). Every prior `return "failed"` site threw its
    reason away entirely; this is the only change in behaviour here — no
    download/retry/degradation logic is touched."""
    scraper = cloudscraper.create_scraper()
    gallery_id_match = re.search(r"aid-(\d+)", url)
    if not gallery_id_match:
        return "failed", "URL 不含有效的 aid（相簿 ID），無法辨識為 wnacg 相簿連結"

    gallery_id = gallery_id_match.group(1)
    try:
        response = scraper.get(url, headers=HEADERS)
        response.raise_for_status()
    except Exception as exc:
        return "failed", _sanitize_error(f"作品頁面請求失敗: {exc}", urls=(url,))

    soup = BeautifulSoup(response.text, "lxml")
    title_el = soup.find("title")
    if not title_el:
        return "failed", "作品頁面未找到標題（頁面結構可能已變更）"

    title = _remove_illegal_chars(title_el.text.strip().split("-")[0])
    download_dir = output_root / f"{gallery_id}_{title}"
    download_dir.mkdir(parents=True, exist_ok=True)

    gallery_url = url.replace("photos-slide-aid-", "download-index-aid-").replace("photos-index-aid-", "download-index-aid-")
    try:
        response = scraper.get(gallery_url, headers=HEADERS)
        response.raise_for_status()
    except Exception as exc:
        return "failed", _sanitize_error(f"下載頁面請求失敗: {exc}", urls=(gallery_url,))

    soup = BeautifulSoup(response.text, "lxml")
    config = _parse_config(soup)
    download_link: str | None = None
    archive_filename: str | None = config[2] if config else None
    config_error: str | None = None
    if config:
        worker_api, file_key, file_name = config
        try:
            download_link = _config_link(worker_api, file_key, file_name, scraper)
        except Exception as exc:
            # No `urls=` needed: `_sanitize_error`'s blanket scan already
            # redacts any `https?://` substring found anywhere in the
            # message, including `raise_for_status()`'s FINAL post-redirect
            # URL, which is never the same string as `worker_api`.
            config_error = _sanitize_error(f"CONFIG API（主線路）取得下載連結失敗: {exc}")
            print(f"[wnacg] {config_error}，改用備用線路")
            download_link = None
    if not download_link:
        download_link, archive_filename = _fallback_link(soup, archive_filename)
    if not download_link or not archive_filename:
        if config_error:
            return "failed", f"{config_error}；備用線路（Server 2）也找不到下載連結"
        if config:
            return "failed", "CONFIG API 未回傳有效下載連結，且備用線路（Server 2）也找不到下載連結"
        return "failed", "頁面缺少 CONFIG 設定，且找不到備用線路（Server 2）下載連結"

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
        except Exception as exc:
            # file before its directory — see `_sanitize_error`'s `paths=`
            # docstring note (R3-6): reversing this order leaves a stale
            # `<dirname>\<filename>` fragment in the message instead of the
            # clean basename.
            return "failed", _sanitize_error(f"檔案下載失敗: {exc}", urls=(download_link,), paths=(archive_path, download_dir))

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
    except Exception as exc:
        # file before its directory — same R3-6 ordering rule as the
        # download-failure site above.
        return "failed", _sanitize_error(f"解壓縮失敗: {exc}", paths=(archive_path, download_dir))

    return "success", ""
