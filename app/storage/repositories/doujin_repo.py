from __future__ import annotations

from datetime import datetime
from typing import Any

from app.storage.db import connection, execute, fetch_all, fetch_one

BOOK_COLUMNS = (
    "folder_path", "title_override", "artist_override", "circle_override",
    "title_fetched", "artist_fetched", "circle_fetched", "page_count_fetched",
    "meta_fetch_status", "meta_fetched_at", "meta_source_url",
    "size_label", "series_id", "purchase_state", "page_count",
    "page_count_override", "cover_page", "last_page_index",
    "created_at", "updated_at",
)

# Fields a caller may write via update_book(); folder_path/created_at/updated_at
# are managed here, never taken from caller input. *_override is the user's
# manual value (wins when not NULL); *_fetched + the meta_* columns are the
# site-sourced cache + fetch provenance, written only by
# doujin_service.fetch_book_metadata — never by a plain field edit.
EDITABLE_BOOK_FIELDS = (
    "title_override", "artist_override", "circle_override",
    "title_fetched", "artist_fetched", "circle_fetched", "page_count_fetched",
    "meta_fetch_status", "meta_fetched_at", "meta_source_url",
    "size_label", "series_id", "purchase_state", "page_count",
    "page_count_override", "cover_page", "last_page_index",
)

# Every book read joins the referenced series' display name in — callers get
# `series_name` alongside `series_id` without a second query per book.
_BOOK_SELECT = """
    SELECT b.*, s.name AS series_name
    FROM doujin_books b
    LEFT JOIN doujin_series s ON b.series_id = s.id
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_book(folder_path: str) -> dict | None:
    row = fetch_one(f"{_BOOK_SELECT} WHERE b.folder_path = ?", (folder_path,))
    return dict(row) if row else None


def get_books(folder_paths: list[str]) -> dict[str, dict]:
    """Bulk-fetch DB rows for a set of folder paths in ONE query — used by the
    cover wall so listing N books never issues N DB round-trips."""
    if not folder_paths:
        return {}
    placeholders = ",".join("?" for _ in folder_paths)
    rows = fetch_all(
        f"{_BOOK_SELECT} WHERE b.folder_path IN ({placeholders})",
        tuple(folder_paths),
    )
    return {row["folder_path"]: dict(row) for row in rows}


def ensure_book(folder_path: str, defaults: dict[str, Any]) -> dict:
    """Return the existing row for folder_path, or lazily create one seeded with
    `defaults` (typically the live-scanned page_count / auto title) and return
    that. Never overwrites an existing row."""
    existing = get_book(folder_path)
    if existing:
        return existing
    now = _now()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO doujin_books
                (folder_path, title_override, artist_override, circle_override,
                 title_fetched, artist_fetched, circle_fetched, page_count_fetched,
                 meta_fetch_status, meta_fetched_at, meta_source_url,
                 size_label, series_id, purchase_state, page_count,
                 page_count_override, cover_page, last_page_index,
                 created_at, updated_at)
            VALUES (?, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                    NULL, NULL, NULL, '', NULL, 'not_purchased', ?, NULL, '', 0, ?, ?)
            ON CONFLICT(folder_path) DO NOTHING
            """,
            (
                folder_path,
                defaults.get("page_count", 0),
                now,
                now,
            ),
        )
    return get_book(folder_path) or {
        "folder_path": folder_path,
        "title_override": None,
        "artist_override": None,
        "circle_override": None,
        "title_fetched": None,
        "artist_fetched": None,
        "circle_fetched": None,
        "page_count_fetched": None,
        "meta_fetch_status": None,
        "meta_fetched_at": None,
        "meta_source_url": None,
        "size_label": "",
        "series_id": None,
        "series_name": None,
        "purchase_state": "not_purchased",
        "page_count": defaults.get("page_count", 0),
        "page_count_override": None,
        "cover_page": "",
        "last_page_index": 0,
        "created_at": now,
        "updated_at": now,
    }


def update_book(folder_path: str, fields: dict[str, Any], seed_defaults: dict[str, Any]) -> dict:
    """Upsert folder_path with `fields` (already validated by the service layer),
    ensuring the row exists first (seeded via seed_defaults for any column not
    covered by `fields`)."""
    ensure_book(folder_path, seed_defaults)
    updates = {k: v for k, v in fields.items() if k in EDITABLE_BOOK_FIELDS}
    if not updates:
        return get_book(folder_path)  # type: ignore[return-value]
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    params = tuple(updates.values()) + (_now(), folder_path)
    execute(
        f"UPDATE doujin_books SET {set_clause}, updated_at = ? WHERE folder_path = ?",
        params,
    )
    return get_book(folder_path)  # type: ignore[return-value]


def set_import_fields(
    folder_path: str,
    *,
    favorite: bool,
    thumbnail_path: str | None,
    title_fetched: str | None,
    artist_fetched: str | None,
    seed_defaults: dict[str, Any],
) -> dict:
    """Write the legacy-import-owned columns for a book matched to an
    existing folder (app/scripts/import_hentai_viewer.py). Bypasses
    update_book()/EDITABLE_BOOK_FIELDS on purpose — imported_favorite and
    imported_thumbnail are never user-editable via the book edit API, only
    written here.

    imported_favorite / imported_thumbnail are set UNCONDITIONALLY to the
    import's value every call — they are import-owned data with no other
    writer, so re-running the import with the same source is naturally
    idempotent (same value written = no observable change) and a changed
    source (re-imported favorite flag, a newly copied thumbnail) is always
    reflected.

    title_fetched / artist_fetched are the manual-edit-wins channel's
    write-side guard: written ONLY when BOTH the matching *_override (the
    user's own manual edit) AND *_fetched (a value already cached from a
    real site fetch) are empty on the CURRENT row — so this never clobbers
    something the user typed by hand, and never clobbers a genuine
    doujin_meta_service fetch result with a lower-quality legacy copy.
    """
    ensure_book(folder_path, seed_defaults)
    current = get_book(folder_path) or {}

    fields: dict[str, Any] = {
        "imported_favorite": 1 if favorite else 0,
        "imported_thumbnail": thumbnail_path,
    }
    if title_fetched and not current.get("title_override") and not current.get("title_fetched"):
        fields["title_fetched"] = title_fetched
    if artist_fetched and not current.get("artist_override") and not current.get("artist_fetched"):
        fields["artist_fetched"] = artist_fetched

    set_clause = ", ".join(f"{col} = ?" for col in fields)
    params = (*tuple(fields.values()), _now(), folder_path)
    execute(
        f"UPDATE doujin_books SET {set_clause}, updated_at = ? WHERE folder_path = ?",
        params,
    )
    return get_book(folder_path)  # type: ignore[return-value]


def list_links(book: str) -> list[dict]:
    rows = fetch_all(
        "SELECT id, book, label, url, created_at FROM doujin_book_links WHERE book = ? ORDER BY id",
        (book,),
    )
    return [dict(row) for row in rows]


def add_link(book: str, label: str, url: str) -> dict:
    row = fetch_one(
        "SELECT id FROM doujin_book_links WHERE book = ? AND url = ?", (book, url)
    )
    if row:
        raise ValueError("duplicate link")
    with connection() as conn:
        cursor = conn.execute(
            "INSERT INTO doujin_book_links (book, label, url, created_at) VALUES (?, ?, ?, ?)",
            (book, label, url, _now()),
        )
        link_id = int(cursor.lastrowid)
    return {"id": link_id, "book": book, "label": label, "url": url}


def delete_link(link_id: int, book: str) -> bool:
    """Delete a link, scoped to `book` so one book's edit panel cannot delete
    another book's link by guessing an id."""
    row = fetch_one(
        "SELECT id FROM doujin_book_links WHERE id = ? AND book = ?", (link_id, book)
    )
    if not row:
        return False
    execute("DELETE FROM doujin_book_links WHERE id = ?", (link_id,))
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Series (分類) — controlled vocabulary
# ──────────────────────────────────────────────────────────────────────────────


def get_series(series_id: int) -> dict | None:
    row = fetch_one("SELECT * FROM doujin_series WHERE id = ?", (series_id,))
    return dict(row) if row else None


def find_series_by_normalized(normalized_name: str) -> dict | None:
    row = fetch_one("SELECT * FROM doujin_series WHERE normalized_name = ?", (normalized_name,))
    return dict(row) if row else None


def list_all_series() -> list[dict]:
    """Every series row — small table by nature (a controlled vocabulary), so a
    full scan is what both the near-duplicate check and the as-you-type search
    use rather than round-tripping per keystroke with a different query shape."""
    rows = fetch_all("SELECT * FROM doujin_series ORDER BY name COLLATE NOCASE")
    return [dict(row) for row in rows]


def search_series(query: str) -> list[dict]:
    """Substring match on the display name, case-insensitive — backs the
    combobox's as-you-type filtering."""
    rows = fetch_all(
        "SELECT * FROM doujin_series WHERE name LIKE ? ESCAPE '\\' ORDER BY name COLLATE NOCASE",
        (f"%{_escape_like(query)}%",),
    )
    return [dict(row) for row in rows]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def create_series(name: str, normalized_name: str) -> dict:
    now = _now()
    with connection() as conn:
        cursor = conn.execute(
            "INSERT INTO doujin_series (name, normalized_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, normalized_name, now, now),
        )
        series_id = int(cursor.lastrowid)
    return get_series(series_id)  # type: ignore[return-value]


def count_books_for_series(series_id: int) -> int:
    row = fetch_one("SELECT COUNT(*) AS n FROM doujin_books WHERE series_id = ?", (series_id,))
    return int(row["n"]) if row else 0


def clear_series_on_books(series_id: int) -> None:
    execute("UPDATE doujin_books SET series_id = NULL WHERE series_id = ?", (series_id,))


def delete_series(series_id: int) -> None:
    execute("DELETE FROM doujin_series WHERE id = ?", (series_id,))


# ──────────────────────────────────────────────────────────────────────────────
# Wanted books (待購/想看, no download/ folder yet) — imported from the legacy
# hentaiViewer library only, no editing API. See doujin_wanted_books in
# app/storage/db.py for why this is a separate table rather than a fake
# doujin_books row.
# ──────────────────────────────────────────────────────────────────────────────


def get_wanted_book(source: str, code: str) -> dict | None:
    row = fetch_one(
        "SELECT * FROM doujin_wanted_books WHERE source = ? AND code = ?", (source, code)
    )
    return dict(row) if row else None


def list_wanted_books() -> list[dict]:
    rows = fetch_all(
        "SELECT * FROM doujin_wanted_books ORDER BY source, code"
    )
    return [dict(row) for row in rows]


def upsert_wanted_book(
    source: str,
    code: str,
    *,
    title: str,
    artist: str,
    favorite: bool,
    thumbnail_path: str | None,
) -> dict:
    """Insert-or-overwrite one wanted-book row with the import's current
    values. Every field here traces to the same-run allData.json record, so
    writing it unconditionally on every call is idempotent (same source data
    -> same row, no observable change on a re-run)."""
    now = _now()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO doujin_wanted_books
                (source, code, title, artist, favorite, thumbnail_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, code) DO UPDATE SET
                title = excluded.title,
                artist = excluded.artist,
                favorite = excluded.favorite,
                thumbnail_path = excluded.thumbnail_path,
                updated_at = excluded.updated_at
            """,
            (source, code, title, artist, 1 if favorite else 0, thumbnail_path, now, now),
        )
    return get_wanted_book(source, code)  # type: ignore[return-value]


def delete_wanted_book(source: str, code: str) -> bool:
    """Remove a wanted-book row — used when a re-run of the importer finds
    the book now has a real download/ folder (promoted into doujin_books).
    Idempotent no-op if the row is already gone."""
    row = get_wanted_book(source, code)
    if not row:
        return False
    execute("DELETE FROM doujin_wanted_books WHERE source = ? AND code = ?", (source, code))
    return True
