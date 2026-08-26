from __future__ import annotations

import mimetypes
from pathlib import Path

from app.config.gallery_modes import resolve_mode
from app.config.paths import DOWNLOAD_DIR

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v", ".wmv", ".ts"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS


def media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTS:
        return "image"
    if suffix in VIDEO_EXTS:
        return "video"
    return "other"


def _rel(path: Path) -> str:
    return path.relative_to(DOWNLOAD_DIR).as_posix()


def _first_preview(folder: Path) -> str | None:
    """Return relative path of the first image in a folder."""
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
            return _rel(f)
    return None


def _folder_has_only_files(folder: Path) -> bool:
    """True when folder contains at least one file and no sub-directories."""
    has_file = False
    for entry in folder.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            return False
        if entry.is_file():
            has_file = True
    return has_file


def _iter_leaf_items(folder: Path) -> list[dict]:
    """
    Recursively yield item descriptors.
    A leaf item is a directory that directly contains files (no sub-dirs),
    or a standalone media file sitting at any depth.
    """
    items: list[dict] = []
    try:
        entries = sorted(folder.iterdir(), key=lambda e: e.name.lower())
    except PermissionError:
        return items

    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_file():
            if entry.suffix.lower() in MEDIA_EXTS:
                items.append(
                    {
                        "name": entry.name,
                        "path": _rel(entry),
                        "type": "file",
                        "media_type": media_type(entry),
                        "preview": _rel(entry) if entry.suffix.lower() in IMAGE_EXTS else None,
                        "file_count": 1,
                    }
                )
        elif entry.is_dir():
            if _folder_has_only_files(entry):
                file_count = sum(1 for f in entry.iterdir() if f.is_file() and not f.name.startswith("."))
                preview = _first_preview(entry)
                items.append(
                    {
                        "name": entry.name,
                        "path": _rel(entry),
                        "type": "dir",
                        "media_type": None,
                        "preview": preview,
                        "file_count": file_count,
                    }
                )
            else:
                # Intermediate directory (e.g. pixiv/author_name) — recurse
                items.extend(_iter_leaf_items(entry))
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def list_categories() -> list[dict]:
    """Return top-level category directories under DOWNLOAD_DIR.

    `mode` tells the frontend which presentation this source uses
    ("doujinshi" -> cover wall + reader, "general" -> unchanged thumbnail
    wall) so it never needs its own copy of the source list — see
    app.config.gallery_modes.resolve_mode, the single source of truth."""
    if not DOWNLOAD_DIR.exists():
        return []
    cats: list[dict] = []
    for entry in sorted(DOWNLOAD_DIR.iterdir(), key=lambda e: e.name.lower()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        items = _iter_leaf_items(entry)
        cats.append(
            {
                "name": entry.name,
                "path": _rel(entry),
                "item_count": len(items),
                "mode": resolve_mode(entry.name),
            }
        )
    return cats


def list_items(category: str) -> list[dict]:
    """Return all leaf items under a category path (relative to DOWNLOAD_DIR)."""
    folder = DOWNLOAD_DIR / category.strip("/")
    if not folder.exists() or not folder.is_dir():
        return []
    return _iter_leaf_items(folder)


def list_files(item_path: str) -> list[dict]:
    """Return all files inside an item folder (or single-file item)."""
    target = DOWNLOAD_DIR / item_path.strip("/")
    if target.is_file():
        return [
            {
                "name": target.name,
                "path": _rel(target),
                "media_type": media_type(target),
            }
        ]
    if not target.exists() or not target.is_dir():
        return []

    files: list[dict] = []
    for f in sorted(target.iterdir(), key=lambda e: e.name.lower()):
        if f.is_file() and not f.name.startswith("."):
            files.append(
                {
                    "name": f.name,
                    "path": _rel(f),
                    "media_type": media_type(f),
                }
            )
    return files


def resolve_file(rel_path: str) -> Path | None:
    """Resolve rel_path to an absolute Path under DOWNLOAD_DIR.
    Returns None if the path escapes the directory or the file does not exist."""
    try:
        resolved = (DOWNLOAD_DIR / rel_path.lstrip("/")).resolve()
        if not resolved.is_relative_to(DOWNLOAD_DIR.resolve()):
            return None
        return resolved if resolved.is_file() else None
    except Exception:
        return None
