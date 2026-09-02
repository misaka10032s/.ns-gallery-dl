from __future__ import annotations

import os
import tempfile
from http.cookies import SimpleCookie
from pathlib import Path

from app.config.paths import COOKIE_DIR
from app.config.settings import normalize_domain
from app.domain import auth_cooldown
from app.providers.cookies.registry import scan_cookie_files
from app.services.path_service import sanitize_component
from app.storage.repositories import cookies_repo


def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically: write to a temp file in the SAME
    directory, then `os.replace()` it into place — matches gallery-dl's own
    `cookies_store()` (gallery_dl/extractor/common.py), which already uses
    `os.replace()` for exactly this reason. A crash/kill mid-write with the
    old `path.write_text()` could leave a truncated file on disk; gallery-dl
    and yt-dlp both re-open and rewrite this SAME cookie file after every
    run, and a truncated/corrupt Netscape cookie jar is
    NOT surfaced as an error — `http.cookiejar` / this app's own
    `doujin_meta_service.MozillaCookieJar.load(...)` silently treat it as
    empty, which is exactly the silent-downgrade-to-guest-session failure
    this whole phase exists to catch (item 5).

    Same-directory temp file guarantees the final `os.replace()` is on the
    same filesystem/volume — a cross-filesystem rename is not atomic on
    POSIX, and `os.replace()` raises outright across drives on Windows.

    Line-ending / encoding: opened in the SAME default text mode
    (`newline=None`) `Path.write_text()` itself uses, so the on-disk
    line-ending behavior this produces is byte-for-byte identical to the
    previous `path.write_text(content, encoding=encoding)` call — only the
    write MECHANISM changed (atomic replace vs. direct truncate-and-write),
    not the resulting bytes. File permissions: a brand-new file created by
    `tempfile.mkstemp` inherits the containing directory's default ACL —
    this repo has never applied explicit POSIX permission bits to cookie
    files (Windows is the only platform this repo runs on; see this repo's
    CLAUDE.md), so there is nothing further to preserve here.
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            # Flush the Python-level text buffer AND force the OS to commit
            # the new file's bytes to disk before the rename below. Without
            # this, `os.replace()` is still atomic (the ORIGINAL file can
            # never be left truncated), but a power loss between the rename
            # and the OS actually flushing its own write-back cache could
            # still leave the NEW file zero-length on next boot — narrower
            # than the failure this function exists to close, but a real gap
            # (review finding, 2026-09-02 round 2).
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _cookie_file_name(domain: str) -> str:
    # sanitize_component strips path-traversal characters (/, \, ..) before use as filename
    safe = sanitize_component(domain.replace(".", "-"), "unknown")
    return f"cookies-{safe}.txt"


def _cookie_file_path(domain: str) -> Path:
    path = COOKIE_DIR / _cookie_file_name(domain)
    # Final guard: ensure the resolved path stays within COOKIE_DIR
    resolved = path.resolve()
    cookie_dir_resolved = COOKIE_DIR.resolve()
    if not str(resolved).startswith(str(cookie_dir_resolved)):
        raise ValueError(f"Invalid domain — path would escape cookie directory: {domain}")
    return path


def _normalize_cookie_text(domain: str, cookie_value: str) -> str:
    raw = cookie_value.strip()
    if not raw:
        raise ValueError("Cookie value is required.")
    if raw.startswith("# Netscape HTTP Cookie File"):
        return raw if raw.endswith("\n") else f"{raw}\n"

    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()

    parser = SimpleCookie()
    parser.load(raw)
    if not parser:
        raise ValueError("Cookie value must be a valid Cookie header string or Netscape cookie file content.")

    lines = ["# Netscape HTTP Cookie File", ""]
    for name, morsel in parser.items():
        lines.append(f".{domain}\tTRUE\t/\tTRUE\t0\t{name}\t{morsel.value}")
    return "\n".join(lines) + "\n"


def list_cookies() -> list[dict]:
    scan_cookie_files()
    return cookies_repo.list_cookies()


def read_cookie(domain: str) -> dict | None:
    normalized = normalize_domain(domain)
    if not normalized:
        return None
    path = _cookie_file_path(normalized)
    if not path.exists():
        return None
    return {
        "domain": normalized,
        "file_name": path.name,
        "file_path": str(path.resolve()),
        "content": path.read_text(encoding="utf-8"),
    }


def save_cookie(domain: str, cookie_value: str, previous_domain: str | None = None) -> dict:
    normalized = normalize_domain(domain)
    if not normalized:
        raise ValueError("A valid domain is required.")

    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    previous = normalize_domain(previous_domain) if previous_domain else ""
    if previous and previous != normalized:
        delete_cookie(previous, missing_ok=True)

    path = _cookie_file_path(normalized)
    _atomic_write_text(path, _normalize_cookie_text(normalized, cookie_value), encoding="utf-8")
    scan_cookie_files()
    # B2 fix (2026-09-02): a re-seeded cookie IS the fix an armed cooldown was
    # waiting for — don't make the owner also wait out AUTH_COOLDOWN_SECONDS
    # on top of re-seeding. Cleared unconditionally (idempotent no-op if the
    # domain had no cooldown) rather than only on a "did this actually
    # change anything" check, since a byte-identical re-save is still the
    # owner's explicit signal that they believe the credential is now good.
    auth_cooldown.clear_cooldown(normalized)
    record = read_cookie(normalized)
    if not record:
        raise ValueError("Cookie saved, but registry lookup failed.")
    return record


def delete_cookie(domain: str, missing_ok: bool = False) -> int:
    normalized = normalize_domain(domain)
    if not normalized:
        raise ValueError("A valid domain is required.")

    deleted = 0
    path = _cookie_file_path(normalized)
    if path.exists():
        path.unlink()
        deleted += 1

    for item in cookies_repo.list_cookies():
        if item["domain"] != normalized:
            continue
        existing = Path(item["file_path"])
        if existing.exists() and existing.parent == COOKIE_DIR and existing != path:
            existing.unlink()
            deleted += 1

    scan_cookie_files()
    if deleted == 0 and not missing_ok:
        raise FileNotFoundError(f"No cookie file found for domain: {normalized}")
    if deleted:
        # B2 fix: a removed cookie also ends any cooldown for this domain —
        # the domain will now be attempted anonymously (no cookie candidate)
        # rather than skipped for up to AUTH_COOLDOWN_SECONDS against a jar
        # that no longer exists. Only cleared when a file was ACTUALLY
        # removed (never on the missing_ok no-op case, where nothing changed).
        auth_cooldown.clear_cooldown(normalized)
    return deleted
