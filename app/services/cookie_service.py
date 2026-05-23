from __future__ import annotations

from http.cookies import SimpleCookie
from pathlib import Path

from app.config.paths import COOKIE_DIR
from app.config.settings import normalize_domain
from app.providers.cookies.registry import scan_cookie_files
from app.services.path_service import sanitize_component
from app.storage.repositories import cookies_repo


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
    path.write_text(_normalize_cookie_text(normalized, cookie_value), encoding="utf-8")
    scan_cookie_files()
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
    return deleted
