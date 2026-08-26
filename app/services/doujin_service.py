from __future__ import annotations

import os
import re
from pathlib import Path

from app.config.gallery_modes import MODE_DOUJINSHI, resolve_mode
from app.config.paths import DOWNLOAD_DIR
from app.services.gallery_service import IMAGE_EXTS
from app.storage.repositories import doujin_repo

ALLOWED_PURCHASE_STATES = ("not_purchased", "purchased")
DEFAULT_PURCHASE_STATE = "not_purchased"

# Strings are user-typed metadata (title/artist/circle/...) — cap length so a
# pasted wall of text can't bloat a row; not a hard business limit.
MAX_FIELD_LEN = 500

_STRING_FIELDS = ("title", "artist", "circle", "size_label", "color_pages", "series")

_NUM_RE = re.compile(r"(\d+)")


# ──────────────────────────────────────────────────────────────────────────────
# Natural / numeric filename ordering
# ──────────────────────────────────────────────────────────────────────────────


def natural_sort_key(name: str) -> list[tuple[int, int | str]]:
    """Sort key so "2.jpg" < "10.jpg" (plain lexicographic sort gets this
    backwards). Every token is wrapped as (0, int) or (1, str) so the list is
    always internally comparable — two filenames can split into different
    digit/text layouts (e.g. "cover.png" vs "003.png"), and comparing a bare
    int to a bare str at the same position would raise TypeError."""
    tokens = _NUM_RE.split(name)
    return [(0, int(tok)) if tok.isdigit() else (1, tok.lower()) for tok in tokens]


# ──────────────────────────────────────────────────────────────────────────────
# Filesystem helpers
# ──────────────────────────────────────────────────────────────────────────────


def _rel(path: Path) -> str:
    return path.relative_to(DOWNLOAD_DIR).as_posix()


def _pages(folder: Path) -> list[str]:
    """Naturally-ordered image filenames directly inside `folder`. Uses
    os.scandir + DirEntry.is_file()/.name only (no per-file os.stat()) so
    listing hundreds of books stays a bulk directory read, not N file stats."""
    names: list[str] = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_EXTS:
                    names.append(entry.name)
    except OSError:
        return []
    names.sort(key=natural_sort_key)
    return names


def resolve_source_dir(source: str) -> Path | None:
    """Resolve a top-level source name to its DOWNLOAD_DIR subfolder, only if
    that source is configured for doujinshi mode."""
    if not source or "/" in source or resolve_mode(source) != MODE_DOUJINSHI:
        return None
    try:
        resolved = (DOWNLOAD_DIR / source).resolve()
        if not resolved.is_relative_to(DOWNLOAD_DIR.resolve()):
            return None
        return resolved if resolved.is_dir() else None
    except OSError:
        return None


def resolve_book_dir(folder_path: str) -> Path | None:
    """Resolve folder_path (relative to DOWNLOAD_DIR) to a book directory.
    Rejects anything that escapes DOWNLOAD_DIR (same is_relative_to guard as
    gallery_service.resolve_file — kept intact here), anything not exactly one
    level under a doujinshi-mode source (a book is a direct child of its
    source, never deeper), and anything that isn't an existing directory."""
    if not folder_path:
        return None
    try:
        resolved = (DOWNLOAD_DIR / folder_path.strip("/")).resolve()
        base = DOWNLOAD_DIR.resolve()
        if not resolved.is_relative_to(base):
            return None
        rel = resolved.relative_to(base)
        if len(rel.parts) != 2:
            return None
        if resolve_mode(rel.parts[0]) != MODE_DOUJINSHI:
            return None
        return resolved if resolved.is_dir() else None
    except OSError:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Read paths
# ──────────────────────────────────────────────────────────────────────────────


def _cover_for(pages: list[str], db_row: dict | None) -> str | None:
    cover_page = (db_row or {}).get("cover_page") or ""
    if cover_page and cover_page in pages:
        chosen = cover_page
    elif pages:
        chosen = pages[0]
    else:
        return None
    return chosen


def _effective_page_count(db_row: dict | None, live_count: int) -> int:
    override = (db_row or {}).get("page_count_override")
    return override if override is not None else live_count


def list_source_books(source: str) -> list[dict] | None:
    """Cover-wall data for one doujinshi source. Read-only — never writes a
    lazy DB row, so browsing a wall of hundreds of never-edited books does not
    trigger hundreds of inserts. One bulk DB query overlays any existing rows
    onto the live filesystem scan."""
    source_dir = resolve_source_dir(source)
    if source_dir is None:
        return None

    folders: list[tuple[str, Path]] = []
    try:
        with os.scandir(source_dir) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    folders.append((entry.name, source_dir / entry.name))
    except OSError:
        return []
    folders.sort(key=lambda t: natural_sort_key(t[0]))

    folder_paths = [f"{source}/{name}" for name, _ in folders]
    db_rows = doujin_repo.get_books(folder_paths)

    books: list[dict] = []
    for (name, path), folder_path in zip(folders, folder_paths):
        pages = _pages(path)
        db_row = db_rows.get(folder_path)
        cover = _cover_for(pages, db_row)
        books.append(
            {
                "folder_path": folder_path,
                "title": (db_row or {}).get("title") or name,
                "artist": (db_row or {}).get("artist", ""),
                "circle": (db_row or {}).get("circle", ""),
                "series": (db_row or {}).get("series", ""),
                "purchase_state": (db_row or {}).get("purchase_state") or DEFAULT_PURCHASE_STATE,
                "page_count": _effective_page_count(db_row, len(pages)),
                "cover": f"{folder_path}/{cover}" if cover else None,
            }
        )
    return books


def get_book_detail(folder_path: str) -> dict | None:
    """Full detail for the reader + edit panel. This DOES lazily create the DB
    row (an explicit open/edit is a real "touch"), refreshing the cached
    page_count from disk at the same time."""
    book_dir = resolve_book_dir(folder_path)
    if book_dir is None:
        return None
    pages = _pages(book_dir)
    db_row = doujin_repo.ensure_book(folder_path, {"title": book_dir.name, "page_count": len(pages)})
    # keep the cached count fresh without clobbering a manual override
    if db_row.get("page_count") != len(pages):
        db_row = doujin_repo.update_book(folder_path, {"page_count": len(pages)}, {"title": book_dir.name, "page_count": len(pages)})

    cover = _cover_for(pages, db_row)
    last_page_index = min(max(db_row.get("last_page_index", 0), 0), max(len(pages) - 1, 0))

    return {
        "folder_path": folder_path,
        "title": db_row.get("title") or book_dir.name,
        "artist": db_row.get("artist", ""),
        "circle": db_row.get("circle", ""),
        "size_label": db_row.get("size_label", ""),
        "color_pages": db_row.get("color_pages", ""),
        "series": db_row.get("series", ""),
        "purchase_state": db_row.get("purchase_state") or DEFAULT_PURCHASE_STATE,
        "page_count": _effective_page_count(db_row, len(pages)),
        "page_count_override": db_row.get("page_count_override"),
        "cover": f"{folder_path}/{cover}" if cover else None,
        "cover_page": db_row.get("cover_page", ""),
        "last_page_index": last_page_index,
        "pages": [{"name": p, "path": f"{folder_path}/{p}"} for p in pages],
        "links": doujin_repo.list_links(folder_path),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Writes
# ──────────────────────────────────────────────────────────────────────────────


class ValidationError(ValueError):
    pass


def update_book(folder_path: str, payload: dict) -> dict | None:
    """Validate + persist editable book fields. Returns the refreshed detail,
    or None if folder_path does not resolve to a real doujinshi book."""
    book_dir = resolve_book_dir(folder_path)
    if book_dir is None:
        return None
    pages = _pages(book_dir)

    fields: dict = {}
    for key in _STRING_FIELDS:
        if key in payload:
            value = payload[key]
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise ValidationError(f"{key} must be a string")
            if len(value) > MAX_FIELD_LEN:
                raise ValidationError(f"{key} exceeds {MAX_FIELD_LEN} characters")
            fields[key] = value.strip()

    if "purchase_state" in payload:
        state = payload["purchase_state"]
        if state not in ALLOWED_PURCHASE_STATES:
            raise ValidationError(f"purchase_state must be one of {ALLOWED_PURCHASE_STATES}")
        fields["purchase_state"] = state

    if "cover_page" in payload:
        cover_page = payload["cover_page"] or ""
        if cover_page and cover_page not in pages:
            raise ValidationError("cover_page must be one of this book's actual pages")
        fields["cover_page"] = cover_page

    if "page_count_override" in payload:
        override = payload["page_count_override"]
        if override is not None:
            if not isinstance(override, int) or isinstance(override, bool) or override < 0:
                raise ValidationError("page_count_override must be a non-negative integer or null")
        fields["page_count_override"] = override

    if "last_page_index" in payload:
        idx = payload["last_page_index"]
        if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
            raise ValidationError("last_page_index must be a non-negative integer")
        fields["last_page_index"] = min(idx, max(len(pages) - 1, 0))

    # page_count itself is never client-settable — always refreshed from disk.
    fields["page_count"] = len(pages)

    doujin_repo.update_book(folder_path, fields, {"title": book_dir.name, "page_count": len(pages)})
    return get_book_detail(folder_path)


def add_link(folder_path: str, label: str, url: str) -> dict | None:
    book_dir = resolve_book_dir(folder_path)
    if book_dir is None:
        return None
    url = (url or "").strip()
    if not url:
        raise ValidationError("url is required")
    if len(url) > 2000:
        raise ValidationError("url exceeds 2000 characters")
    label = (label or "").strip()
    if len(label) > 100:
        raise ValidationError("label exceeds 100 characters")

    pages = _pages(book_dir)
    doujin_repo.ensure_book(folder_path, {"title": book_dir.name, "page_count": len(pages)})
    return doujin_repo.add_link(folder_path, label, url)


def delete_link(folder_path: str, link_id: int) -> bool:
    book_dir = resolve_book_dir(folder_path)
    if book_dir is None:
        return False
    return doujin_repo.delete_link(link_id, folder_path)
