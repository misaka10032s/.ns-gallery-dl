from __future__ import annotations

import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from app.config.gallery_modes import MODE_DOUJINSHI, resolve_mode
from app.config.paths import DOWNLOAD_DIR
from app.services import doujin_meta_service
from app.services.gallery_service import IMAGE_EXTS
from app.storage.repositories import doujin_repo

ALLOWED_PURCHASE_STATES = ("not_purchased", "purchased")
DEFAULT_PURCHASE_STATE = "not_purchased"

# Strings are user-typed metadata — cap length so a pasted wall of text can't
# bloat a row; not a hard business limit. title/artist/circle have their own
# override/fetched handling below; size_label is the only field left in this
# "plain editable string" bucket.
# 彩頁 (color_pages) was removed 2026-08-26 — the user does not want the field
# and it carried no data yet. Do not re-add without a stated reason.
MAX_FIELD_LEN = 500
_STRING_FIELDS = ("size_label",)

_NUM_RE = re.compile(r"(\d+)")

# Near-duplicate series threshold (SequenceMatcher.ratio() on the
# whitespace-collapsed, lowercased form). Anything at or above this is
# surfaced as "you probably mean this one"; below it, series are treated as
# unrelated. Exact matches after normalization (case/whitespace-only
# differences) never reach this check at all — they resolve to the SAME row
# automatically, see resolve_or_create_series().
SERIES_SIMILARITY_THRESHOLD = 0.82


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
#
# title/artist/circle precedence, computed at read time (never pre-merged
# into storage): *_override (manual, always wins) > *_fetched (site-sourced,
# see doujin_meta_service) > a plain default (folder name for title, '' for
# artist/circle). There is deliberately NO folder-name parsing anywhere in
# this file — a folder name is treated only as a display fallback and, via
# doujin_meta_service.extract_gallery_id, a place to read a bare numeric
# identifier off the front. It is never interpreted for title/artist/circle.


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


def _resolve_field(db_row: dict | None, field: str, default: str) -> tuple[str, str]:
    """Returns (effective_value, source) where source is "manual" | "fetched"
    | "default"."""
    row = db_row or {}
    override = row.get(f"{field}_override")
    if override is not None:
        return override, "manual"
    fetched = row.get(f"{field}_fetched")
    if fetched:
        return fetched, "fetched"
    return default, "default"


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
        title, _ = _resolve_field(db_row, "title", name)
        artist, _ = _resolve_field(db_row, "artist", "")
        circle, _ = _resolve_field(db_row, "circle", "")
        cover = _cover_for(pages, db_row)
        # Free — meta_fetch_status is already in db_row from the ONE bulk
        # query above, no extra I/O. Collapsed to a bool (see
        # doujin_meta_service.ATTENTION_FETCH_STATUSES) rather than exposing
        # the raw status: the cover wall only needs "does this book need a
        # look", not the full status vocabulary — that detail stays in the
        # edit panel (get_book_detail's meta_fetch_status).
        needs_fetch_attention = (
            (db_row or {}).get("meta_fetch_status") in doujin_meta_service.ATTENTION_FETCH_STATUSES
        )
        books.append(
            {
                "folder_path": folder_path,
                "title": title,
                "artist": artist,
                "circle": circle,
                "series_id": (db_row or {}).get("series_id"),
                "series_name": (db_row or {}).get("series_name"),
                "purchase_state": (db_row or {}).get("purchase_state") or DEFAULT_PURCHASE_STATE,
                "page_count": _effective_page_count(db_row, len(pages)),
                "cover": f"{folder_path}/{cover}" if cover else None,
                "needs_fetch_attention": needs_fetch_attention,
            }
        )
    return books


def get_book_detail(folder_path: str) -> dict | None:
    """Full detail for the reader + edit panel. This DOES lazily create the DB
    row (an explicit open/edit is a real "touch"), refreshing the cached
    page_count from disk at the same time — title/artist/circle are never
    touched here (no parsing to refresh); they only change via update_book
    (manual) or fetch_book_metadata (site)."""
    book_dir = resolve_book_dir(folder_path)
    if book_dir is None:
        return None
    pages = _pages(book_dir)
    db_row = doujin_repo.ensure_book(folder_path, {"page_count": len(pages)})
    if db_row.get("page_count") != len(pages):
        db_row = doujin_repo.update_book(folder_path, {"page_count": len(pages)}, {"page_count": len(pages)})

    title, title_source = _resolve_field(db_row, "title", book_dir.name)
    artist, artist_source = _resolve_field(db_row, "artist", "")
    circle, circle_source = _resolve_field(db_row, "circle", "")

    cover = _cover_for(pages, db_row)
    last_page_index = min(max(db_row.get("last_page_index", 0), 0), max(len(pages) - 1, 0))

    return {
        "folder_path": folder_path,
        "folder_name": book_dir.name,  # original on-disk name — always visible
        "title": title,
        "title_source": title_source,
        "title_override": db_row.get("title_override"),
        "title_fetched": db_row.get("title_fetched"),
        "artist": artist,
        "artist_source": artist_source,
        "artist_override": db_row.get("artist_override"),
        "artist_fetched": db_row.get("artist_fetched"),
        "circle": circle,
        "circle_source": circle_source,
        "circle_override": db_row.get("circle_override"),
        "circle_fetched": db_row.get("circle_fetched"),
        "size_label": db_row.get("size_label", ""),
        "series_id": db_row.get("series_id"),
        "series_name": db_row.get("series_name"),
        "purchase_state": db_row.get("purchase_state") or DEFAULT_PURCHASE_STATE,
        "page_count": _effective_page_count(db_row, len(pages)),
        "page_count_override": db_row.get("page_count_override"),
        "page_count_fetched": db_row.get("page_count_fetched"),
        "cover": f"{folder_path}/{cover}" if cover else None,
        "cover_page": db_row.get("cover_page", ""),
        "last_page_index": last_page_index,
        "pages": [{"name": p, "path": f"{folder_path}/{p}"} for p in pages],
        "links": doujin_repo.list_links(folder_path),
        "gallery_id": doujin_meta_service.extract_gallery_id(book_dir.name),
        "meta_fetch_status": db_row.get("meta_fetch_status"),
        "meta_fetched_at": db_row.get("meta_fetched_at"),
        "meta_source_url": db_row.get("meta_source_url"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Writes — book fields
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

    # title/artist/circle: a client-supplied value always writes the
    # *_override column (JSON null clears it -> falls back to *_fetched, then
    # the plain default) — this is the manual-edit-always-wins channel, and
    # it is untouched by fetch_book_metadata.
    for key in ("title", "artist", "circle"):
        if key in payload:
            value = payload[key]
            if value is None:
                fields[f"{key}_override"] = None
            else:
                if not isinstance(value, str):
                    raise ValidationError(f"{key} must be a string or null")
                if len(value) > MAX_FIELD_LEN:
                    raise ValidationError(f"{key} exceeds {MAX_FIELD_LEN} characters")
                fields[f"{key}_override"] = value.strip()

    if "purchase_state" in payload:
        state = payload["purchase_state"]
        if state not in ALLOWED_PURCHASE_STATES:
            raise ValidationError(f"purchase_state must be one of {ALLOWED_PURCHASE_STATES}")
        fields["purchase_state"] = state

    if "series_id" in payload:
        series_id = payload["series_id"]
        if series_id is not None:
            if not isinstance(series_id, int) or isinstance(series_id, bool):
                raise ValidationError("series_id must be an integer or null")
            if doujin_repo.get_series(series_id) is None:
                raise ValidationError(f"series_id {series_id} does not exist")
        fields["series_id"] = series_id

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

    doujin_repo.update_book(folder_path, fields, {"page_count": len(pages)})
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
    doujin_repo.ensure_book(folder_path, {"page_count": len(pages)})
    return doujin_repo.add_link(folder_path, label, url)


def delete_link(folder_path: str, link_id: int) -> bool:
    book_dir = resolve_book_dir(folder_path)
    if book_dir is None:
        return False
    return doujin_repo.delete_link(link_id, folder_path)


# ──────────────────────────────────────────────────────────────────────────────
# Writes — metadata fetch (site-sourced title/artist/circle/page count)
# ──────────────────────────────────────────────────────────────────────────────


def fetch_book_metadata(folder_path: str) -> dict | None:
    """Fetch this book's metadata from its source site (see
    doujin_meta_service) and store the RESULT — never overwriting a manual
    override (title_override etc. are a completely separate column; a fetch
    only ever writes *_fetched + the meta_* provenance fields). Always
    records the attempt's outcome (meta_fetch_status/_fetched_at/_source_url)
    even when it did not yield usable fields, so a failure is visible rather
    than looking identical to "never tried". Returns None if folder_path
    doesn't resolve to a real doujinshi book."""
    book_dir = resolve_book_dir(folder_path)
    if book_dir is None:
        return None

    source = folder_path.split("/", 1)[0]
    gallery_id = doujin_meta_service.extract_gallery_id(book_dir.name)
    if gallery_id is None:
        result = {"status": doujin_meta_service.FETCH_STATUS_NO_GALLERY_ID}
    else:
        result = doujin_meta_service.fetch_metadata(source, gallery_id)

    fields: dict = {
        "meta_fetch_status": result["status"],
        "meta_fetched_at": datetime.now().isoformat(timespec="seconds"),
        "meta_source_url": result.get("source_url"),
    }
    if result["status"] == doujin_meta_service.FETCH_STATUS_OK:
        if result.get("title"):
            fields["title_fetched"] = result["title"]
        if result.get("artist"):
            fields["artist_fetched"] = result["artist"]
        if result.get("circle"):
            fields["circle_fetched"] = result["circle"]
        if result.get("page_count") is not None:
            fields["page_count_fetched"] = result["page_count"]

    pages = _pages(book_dir)
    doujin_repo.update_book(folder_path, fields, {"page_count": len(pages)})
    return get_book_detail(folder_path)


# ──────────────────────────────────────────────────────────────────────────────
# Series (分類) — controlled vocabulary
# ──────────────────────────────────────────────────────────────────────────────

_WHITESPACE_RUN_RE = re.compile(r"\s+")


def normalize_series_name(raw: str) -> str:
    """Trim + collapse internal whitespace runs to one space. This IS the
    display form (preserves the user's original casing — a series name is a
    display label, not a slug). The separate uniqueness key
    (case-insensitive) is this value lower-cased — see
    doujin_repo.find_series_by_normalized / create_series."""
    return _WHITESPACE_RUN_RE.sub(" ", (raw or "").strip())


class NearDuplicateSeriesError(ValueError):
    """Raised when a series name would create a near-duplicate of an existing
    one (differs by more than case/spacing — e.g. a likely typo) and the
    caller has not confirmed they want a separate entry anyway."""

    def __init__(self, candidates: list[dict]):
        super().__init__("near-duplicate series")
        self.candidates = candidates


class SeriesInUseError(ValueError):
    """Raised by delete_series when books still reference it and the caller
    has not passed force=True."""

    def __init__(self, book_count: int):
        super().__init__("series still referenced by books")
        self.book_count = book_count


def _find_near_duplicate_series(display_name: str) -> list[dict]:
    key = display_name.lower()
    scored: list[tuple[float, dict]] = []
    for series in doujin_repo.list_all_series():
        ratio = SequenceMatcher(None, key, series["normalized_name"]).ratio()
        if ratio >= SERIES_SIMILARITY_THRESHOLD:
            scored.append((ratio, series))
    scored.sort(key=lambda t: -t[0])
    return [{**series, "similarity": round(ratio, 3)} for ratio, series in scored[:5]]


def search_series(query: str) -> list[dict]:
    """Backs the edit panel's as-you-type combobox filtering."""
    query = (query or "").strip()
    if not query:
        return doujin_repo.list_all_series()
    return doujin_repo.search_series(query)


def resolve_or_create_series(raw_name: str, *, confirm: bool = False) -> dict:
    """Attach-or-create a series by display name.

    - Exact match after normalization (case/whitespace differences only) ->
      silently reuses the existing row (status "reused") — this is what
      "treat names differing only by case or spacing as the same series"
      means: they ARE the same row, not a warning.
    - No exact match, but a near-duplicate (typo/punctuation-level
      similarity) exists and `confirm` is not set -> raises
      NearDuplicateSeriesError with the candidate(s); the caller must either
      attach to a candidate's id directly, or resubmit with confirm=True to
      create the new one anyway. This is the "make the collision visible,
      don't block" behavior.
    - Otherwise -> creates a new series (status "created").
    """
    display = normalize_series_name(raw_name)
    if not display:
        raise ValidationError("series name is required")
    if len(display) > MAX_FIELD_LEN:
        raise ValidationError(f"series name exceeds {MAX_FIELD_LEN} characters")

    key = display.lower()
    existing = doujin_repo.find_series_by_normalized(key)
    if existing:
        return {"status": "reused", "series": existing}

    if not confirm:
        candidates = _find_near_duplicate_series(display)
        if candidates:
            raise NearDuplicateSeriesError(candidates)

    created = doujin_repo.create_series(display, key)
    return {"status": "created", "series": created}


def delete_series(series_id: int, *, force: bool = False) -> dict | None:
    """Delete a series. Books referencing it are never silently orphaned:
    without force=True, deletion is BLOCKED (raises SeriesInUseError) while
    any book still references it; with force=True, those books' series_id is
    cleared to NULL (an explicit, visible choice — not a silent side effect)
    before the series row is removed. Returns None if series_id doesn't
    exist."""
    existing = doujin_repo.get_series(series_id)
    if existing is None:
        return None
    book_count = doujin_repo.count_books_for_series(series_id)
    if book_count > 0:
        if not force:
            raise SeriesInUseError(book_count)
        doujin_repo.clear_series_on_books(series_id)
    doujin_repo.delete_series(series_id)
    return {"deleted": True, "cleared_books": book_count if force else 0}
