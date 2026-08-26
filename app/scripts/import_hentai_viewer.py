"""
app/scripts/import_hentai_viewer.py

One-time / re-runnable importer for the legacy hentaiViewer library
(D:/backup/CSIA/python/.deprecated/hentaiViewer) into this app's own doujin
model. Deterministic JSON -> SQLite + file copy — NO network, NO LLM, zero
runtime token cost. Every value written here traces back to a field already
present in allData.json or a byte-identical copy of a thumbnail file.

What it imports (see docs/blueprint/entries/BP-SVC-DOUJIN-IMPORT-1.md for the
full design record):
  - allData.json: {artist: {code: {title, favorite}}}, code = "N######"
    (nhentai) or "W######" (wnacg).
  - For a code whose numeric id matches an existing download/nhentai/<id>_...
    or download/wnacg/<id>_... folder: attaches title/artist (into the
    *_fetched cache slot — never *_override) + favorite + thumbnail to that
    book's doujin_books row. Never overwrites a value already present in
    *_override (user's own manual edit) or *_fetched (a real site fetch).
  - For a code with no matching folder: a minimal doujin_wanted_books row
    (待購/想看 — no file, no folder, no wishlist UI, just a queryable record).
  - thumbnail/*.jpg (ALL 600, including the 7 with no allData.json record —
    losing those is permanent, the source galleries are already 404 upstream)
    -> data/doujin_thumbnails/<code>.jpg, copied idempotently (skip when the
    destination's MD5 already matches the source).

What it deliberately does NOT touch: hentaiViewer/backup/, hentaiViewer/
template/, hentaiCollector.py, hentaiViewerServer.py, runserver.cmd,
Link.txt, LinkTmp.txt, 文字.txt, allData.index.json (derivable from
allData.json, no independent information) — see
app/scripts/check_hentai_viewer_import.py, which lists these explicitly as
"not imported — user's judgement".

Safety: the ONLY write targets are the SQLite DB resolved via
app.config.paths (respects the NS_MEDIA_HUB_DATA_DIR override) and
data/doujin_thumbnails/ under that same DATA_DIR. The hentaiViewer source
folder is opened read-only (json.load / os.scandir / file copy FROM it,
never a write, rename, or delete of anything inside it) and download/ is
only ever scanned (os.scandir), never written. If DATA_DIR resolves to the
repo's real, non-overridden data/ directory (i.e. this would touch the
live app.db a running `dl.py` may have open), the script refuses to run
unless --i-know-this-is-live is passed, and even then makes a timestamped
backup copy of app.db first and prints its path before writing anything.

Usage:
    py -3.11 app/scripts/import_hentai_viewer.py
        [--hv-dir PATH]           # default: the known hentaiViewer path
        [--download-dir PATH]     # default: app.config.paths.DOWNLOAD_DIR
        [--data-dir PATH]         # default: app.config.paths.DATA_DIR
        [--i-know-this-is-live]   # required only when --data-dir is unset
                                   # AND NS_MEDIA_HUB_DATA_DIR is unset
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_HV_DIR = Path("D:/backup/CSIA/python/.deprecated/hentaiViewer")

# Same leading-numeric-id convention already used by
# app.services.doujin_meta_service.extract_gallery_id — real nhentai/wnacg
# folder names put the gallery id as a leading run of digits separated by
# "_" or a space ("100873_[...]", "121697 [...]").
GALLERY_ID_RE = re.compile(r"^(\d+)[_ ]")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif", ".tif", ".tiff"}

# hentaiViewer code prefix -> this app's source/provider name (matches the
# top-level download/ folder name and app.config.gallery_modes.DOUJINSHI_SOURCES).
PREFIX_SOURCE = {"N": "nhentai", "W": "wnacg"}

THUMBNAIL_SUBDIR = "doujin_thumbnails"


# ──────────────────────────────────────────────────────────────────────────────
# Pure helpers — unit-tested directly, no DB/filesystem side effects.
# ──────────────────────────────────────────────────────────────────────────────


def split_hv_code(code: str) -> tuple[str, str]:
    """'N105189' -> ('nhentai', '105189'); 'W12345' -> ('wnacg', '12345').
    Raises ValueError on an unrecognized prefix so the caller can decide
    whether that is fatal."""
    if not code or code[0] not in PREFIX_SOURCE:
        raise ValueError(f"unrecognized hentaiViewer code prefix: {code!r}")
    numeric = code[1:]
    if not numeric.isdigit():
        raise ValueError(f"non-numeric id in hentaiViewer code: {code!r}")
    return PREFIX_SOURCE[code[0]], numeric


def scan_source_ids(source_dir: Path) -> dict[str, str]:
    """id -> folder name, for every immediate subdirectory of source_dir
    whose name starts with the gallery-id prefix convention. Missing
    source_dir returns {} rather than raising (a source may legitimately
    have zero downloaded books)."""
    ids: dict[str, str] = {}
    if not source_dir.is_dir():
        return ids
    with os.scandir(source_dir) as it:
        for entry in it:
            if entry.is_dir():
                m = GALLERY_ID_RE.match(entry.name)
                if m:
                    ids[m.group(1)] = entry.name
    return ids


def count_pages(folder: Path) -> int:
    n = 0
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_EXTS:
                    n += 1
    except OSError:
        pass
    return n


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_thumbnail_idempotent(src: Path, dst: Path) -> str:
    """Copy src -> dst only if dst is missing or its content (by MD5)
    differs from src. Returns one of 'copied' | 'skipped-identical' |
    'error'. Never touches src."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        try:
            if md5_of(dst) == md5_of(src):
                return "skipped-identical"
        except OSError:
            pass
    try:
        shutil.copy2(src, dst)
    except OSError:
        return "error"
    return "copied"


# ──────────────────────────────────────────────────────────────────────────────
# Result record
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ImportResult:
    total_records: int = 0
    matched: int = 0
    wanted: int = 0
    promoted: int = 0  # was a wanted-book on a prior run, now has a folder
    thumbnails_copied: int = 0
    thumbnails_skipped_identical: int = 0
    thumbnails_orphaned: int = 0  # no allData.json record references this file
    thumbnails_errors: list[str] = field(default_factory=list)
    unrecognized_codes: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Import — the only function that writes anything
# ──────────────────────────────────────────────────────────────────────────────


def run_import(*, hv_dir: Path, download_dir: Path, data_dir: Path) -> ImportResult:
    """Import allData.json + thumbnail/ from hv_dir into the doujin model,
    matching against download_dir, writing thumbnails under
    data_dir/doujin_thumbnails/. Caller is responsible for having already
    called app.storage.db.init_db() against the intended DB (respecting
    NS_MEDIA_HUB_DATA_DIR / an explicit patch in tests)."""
    from app.storage.repositories import doujin_repo

    result = ImportResult()

    all_data_path = hv_dir / "allData.json"
    data = json.loads(all_data_path.read_text(encoding="utf-8"))

    nhentai_ids = scan_source_ids(download_dir / "nhentai")
    wnacg_ids = scan_source_ids(download_dir / "wnacg")
    id_maps = {"nhentai": nhentai_ids, "wnacg": wnacg_ids}

    # ── thumbnails: copy ALL of them, including the 7 orphans with no
    # allData.json record — the copy loop is driven by the thumbnail/
    # directory listing, not by allData.json, precisely so an orphan is
    # never silently skipped.
    thumb_src_dir = hv_dir / "thumbnail"
    thumb_dst_dir = data_dir / THUMBNAIL_SUBDIR
    referenced_codes: set[str] = set()
    for artist_books in data.values():
        referenced_codes.update(artist_books.keys())

    thumb_dest_by_code: dict[str, str] = {}
    if thumb_src_dir.is_dir():
        with os.scandir(thumb_src_dir) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                code = Path(entry.name).stem
                dst = thumb_dst_dir / entry.name
                status = copy_thumbnail_idempotent(Path(entry.path), dst)
                if status == "copied":
                    result.thumbnails_copied += 1
                elif status == "skipped-identical":
                    result.thumbnails_skipped_identical += 1
                else:
                    result.thumbnails_errors.append(entry.name)
                    continue
                thumb_dest_by_code[code] = f"{THUMBNAIL_SUBDIR}/{entry.name}"
                if code not in referenced_codes:
                    result.thumbnails_orphaned += 1

    # ── records
    for artist, books in data.items():
        for code, info in books.items():
            result.total_records += 1
            try:
                source, gid = split_hv_code(code)
            except ValueError:
                result.unrecognized_codes.append(code)
                continue

            favorite = bool(info.get("favorite"))
            title = info.get("title") or None
            thumbnail_rel = thumb_dest_by_code.get(code)

            folder_name = id_maps[source].get(gid)
            if folder_name is not None:
                folder_path = f"{source}/{folder_name}"
                page_count = count_pages(download_dir / source / folder_name)
                doujin_repo.set_import_fields(
                    folder_path,
                    favorite=favorite,
                    thumbnail_path=thumbnail_rel,
                    title_fetched=title,
                    artist_fetched=artist or None,
                    seed_defaults={"page_count": page_count},
                )
                if doujin_repo.delete_wanted_book(source, gid):
                    result.promoted += 1
                result.matched += 1
            else:
                doujin_repo.upsert_wanted_book(
                    source,
                    gid,
                    title=title or "",
                    artist=artist or "",
                    favorite=favorite,
                    thumbnail_path=thumbnail_rel,
                )
                result.wanted += 1

    return result


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, bool]:
    """Returns (hv_dir, download_dir, data_dir, data_dir_was_overridden).

    NOTE on why this cannot just set os.environ and import app.config.paths
    afterward: `import app.scripts...` first runs app/__init__.py, which
    eagerly imports app.main and — transitively — app.config.paths, using
    whatever NS_MEDIA_HUB_DATA_DIR was in the environment at PROCESS START.
    By the time this function's body runs, app.config.paths.DATA_DIR is
    already a frozen Path object; setting os.environ afterward has zero
    effect on it (confirmed live: an earlier version of this script that did
    exactly that silently wrote to <cwd>/data/app.db instead of the intended
    --data-dir). --data-dir is therefore applied by directly patching the
    module-level DATA_DIR/DB_FILE attributes app.storage.db's _connect()
    reads at CALL time (see _apply_data_dir_override) — the same mechanism
    tests/conftest.py's tmp_db fixture already uses via unittest.mock.patch.
    """
    from app.config import paths as app_paths

    hv_dir = Path(args.hv_dir) if args.hv_dir else DEFAULT_HV_DIR
    download_dir = Path(args.download_dir) if args.download_dir else app_paths.DOWNLOAD_DIR

    data_dir_overridden = bool(args.data_dir) or bool(os.environ.get("NS_MEDIA_HUB_DATA_DIR"))
    data_dir = Path(args.data_dir) if args.data_dir else app_paths.DATA_DIR
    return hv_dir, download_dir, data_dir, data_dir_overridden


def _apply_data_dir_override(data_dir: Path) -> None:
    """Point app.storage.db's actual connection target at data_dir, in-place
    on the already-imported module (see _resolve_paths' docstring for why a
    plain os.environ assignment does not work here)."""
    from app.storage import db as db_module

    db_module.DATA_DIR = data_dir
    db_module.DB_FILE = data_dir / "app.db"


def _backup_live_db(data_dir: Path) -> Path | None:
    db_file = data_dir / "app.db"
    if not db_file.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = data_dir / f"app.db.bak-hv-import-{stamp}"
    shutil.copy2(db_file, backup_path)
    return backup_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hv-dir", help="Path to the legacy hentaiViewer folder")
    parser.add_argument("--download-dir", help="Override DOWNLOAD_DIR (default: app config)")
    parser.add_argument("--data-dir", help="Override DATA_DIR (default: app config)")
    parser.add_argument(
        "--i-know-this-is-live",
        action="store_true",
        help="Required to proceed when --data-dir is unset and NS_MEDIA_HUB_DATA_DIR "
        "is unset (i.e. this run would write the live app.db).",
    )
    args = parser.parse_args(argv)

    hv_dir, download_dir, data_dir, overridden = _resolve_paths(args)

    print(f"hentaiViewer source : {hv_dir}")
    print(f"download_dir (read) : {download_dir}")
    print(f"data_dir (write)    : {data_dir}")

    if not overridden and not args.i_know_this_is_live:
        print(
            "\nREFUSING TO RUN: --data-dir is unset and NS_MEDIA_HUB_DATA_DIR is not "
            "set — this would write the LIVE data/app.db, which a running dl.py may "
            "have open.\n"
            "Either point at a private copy (NS_MEDIA_HUB_DATA_DIR=... or --data-dir), "
            "or re-run with --i-know-this-is-live to proceed against the live DB "
            "(a timestamped backup is made automatically first).",
            file=sys.stderr,
        )
        return 2

    if not overridden and args.i_know_this_is_live:
        backup_path = _backup_live_db(data_dir)
        if backup_path:
            print(f"Live app.db backed up to: {backup_path}")

    if args.data_dir:
        _apply_data_dir_override(data_dir)

    from app.storage.db import init_db

    init_db()
    result = run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=data_dir)

    print()
    print(f"records total          : {result.total_records}")
    print(f"  matched to a folder   : {result.matched}  (promoted from wanted: {result.promoted})")
    print(f"  no folder (wanted)    : {result.wanted}")
    if result.unrecognized_codes:
        print(f"  UNRECOGNIZED codes    : {result.unrecognized_codes}")
    print(f"thumbnails copied       : {result.thumbnails_copied}")
    print(f"thumbnails unchanged    : {result.thumbnails_skipped_identical}")
    print(f"thumbnails orphaned     : {result.thumbnails_orphaned} (no allData.json record)")
    if result.thumbnails_errors:
        print(f"thumbnail COPY ERRORS   : {result.thumbnails_errors}")

    return 1 if (result.unrecognized_codes or result.thumbnails_errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
