"""
app/scripts/check_hentai_viewer_import.py

Re-runnable, read-only checker for app/scripts/import_hentai_viewer.py. This
is the tool the user actually asked for: "a way to judge whether it is safe"
to delete the legacy hentaiViewer folder. It reads BOTH the old hentaiViewer
folder and the new DB / thumbnail store and reports, per category:

  1. allData.json records (593 expected) -> DB, checked PER RECORD (not just
     a total): matched-to-a-folder records must have a doujin_books row with
     the right imported_favorite/imported_thumbnail and a title/artist
     source (fetched, or a manual override that legitimately took
     precedence); no-folder records must have a doujin_wanted_books row with
     exact favorite/title/artist/thumbnail — and must NOT also exist as a
     doujin_books row (the two tables are mutually exclusive by
     construction).
  2. thumbnail/*.jpg (600 expected) -> data/doujin_thumbnails/, compared by
     per-file MD5 (never filename/size alone). Any mismatch is named.
  3. Everything else in the hentaiViewer folder, listed explicitly as
     "not imported — user's judgement" (size + one-line note). The three
     free-text files (Link.txt / LinkTmp.txt / 文字.txt) are named and
     sized only — their CONTENT is never read or characterised.
  4. An unambiguous VERDICT line. Any reconciliation failure -> loud FAIL,
     never a quiet "looks fine".

This script NEVER writes anything — it opens the SQLite DB with
sqlite3's read-only URI mode (mode=ro) and only ever os.scandir /
os.path.getsize / reads file bytes for MD5, never a write, rename, or
delete, anywhere, including inside hentaiViewer/.

Usage:
    py -3.11 app/scripts/check_hentai_viewer_import.py
        [--hv-dir PATH] [--download-dir PATH] [--data-dir PATH]
Exit code 0 = PASS, 1 = FAIL, 2 = could not run the check at all
(e.g. hv_dir already deleted).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.scripts.import_hentai_viewer import (
    DEFAULT_HV_DIR,
    THUMBNAIL_SUBDIR,
    scan_source_ids,
    split_hv_code,
)

# Known non-imported entries and a one-line note each. Anything found at the
# hv_dir top level that is NOT allData.json / thumbnail / one of these keys
# is still reported (never silently dropped) — just with a generic note
# instead of a curated one, so a folder change since this was written still
# surfaces instead of going unmentioned.
KNOWN_NOT_IMPORTED_NOTES = {
    "allData.index.json": "reverse index (code -> artist), derivable from allData.json; no independent information",
    "backup": "directory — historical snapshot(s) of allData.json",
    "template": "directory — old hentaiViewer UI (3 files: html/js)",
    "hentaiCollector.py": "old hentaiViewer scraper/collector script",
    "hentaiViewerServer.py": "old hentaiViewer local server script",
    "runserver.cmd": "launcher for the old server script",
    "Link.txt": "free-text file — content not read by this checker",
    "LinkTmp.txt": "free-text file — content not read by this checker",
    "文字.txt": "free-text file — content not read by this checker",
    "__pycache__": "directory — Python bytecode cache, not source data",
}


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


# ──────────────────────────────────────────────────────────────────────────────
# 1. Per-record check
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class RecordCheck:
    ok: int = 0
    failures: list[str] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)


def _ro_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def check_records(all_data: dict, download_dir: Path, data_dir: Path, db_path: Path | None = None) -> RecordCheck:
    """db_path defaults to data_dir/"app.db" (the real layout); tests that use
    a differently-named test DB file (see tests/conftest.py's tmp_db fixture)
    pass it explicitly."""
    result = RecordCheck()
    db_path = db_path if db_path is not None else data_dir / "app.db"
    if not db_path.exists():
        result.failures.append(f"DB not found at {db_path}")
        return result

    nhentai_ids = scan_source_ids(download_dir / "nhentai")
    wnacg_ids = scan_source_ids(download_dir / "wnacg")
    id_maps = {"nhentai": nhentai_ids, "wnacg": wnacg_ids}

    thumb_dir = data_dir / THUMBNAIL_SUBDIR

    conn = _ro_connect(db_path)
    try:
        for artist, books in all_data.items():
            for code, info in books.items():
                try:
                    source, gid = split_hv_code(code)
                except ValueError:
                    result.unrecognized.append(code)
                    continue

                favorite = 1 if info.get("favorite") else 0
                title = info.get("title") or ""
                expected_thumb_name = f"{code}.jpg"
                expected_thumb_rel = f"{THUMBNAIL_SUBDIR}/{expected_thumb_name}"
                thumb_exists_on_disk = (thumb_dir / expected_thumb_name).is_file()

                folder_name = id_maps[source].get(gid)
                if folder_name is not None:
                    folder_path = f"{source}/{folder_name}"
                    row = conn.execute(
                        "SELECT * FROM doujin_books WHERE folder_path = ?", (folder_path,)
                    ).fetchone()
                    if row is None:
                        result.failures.append(
                            f"{code}: matched folder '{folder_path}' but NO doujin_books row"
                        )
                        continue

                    row_fail = []
                    if row["imported_favorite"] != favorite:
                        row_fail.append(
                            f"imported_favorite={row['imported_favorite']!r} expected {favorite!r}"
                        )
                    if thumb_exists_on_disk and row["imported_thumbnail"] != expected_thumb_rel:
                        row_fail.append(
                            f"imported_thumbnail={row['imported_thumbnail']!r} expected {expected_thumb_rel!r}"
                        )
                    has_title_source = bool(row["title_override"]) or bool(row["title_fetched"])
                    if title and not has_title_source:
                        row_fail.append("title expected from import but title_override/title_fetched both empty")
                    has_artist_source = bool(row["artist_override"]) or bool(row["artist_fetched"])
                    if artist and not has_artist_source:
                        row_fail.append("artist expected from import but artist_override/artist_fetched both empty")

                    # mutual exclusivity: a matched record must not also linger in wanted
                    wanted_row = conn.execute(
                        "SELECT 1 FROM doujin_wanted_books WHERE source = ? AND code = ?",
                        (source, gid),
                    ).fetchone()
                    if wanted_row is not None:
                        row_fail.append("also present in doujin_wanted_books (should have been promoted/removed)")

                    if row_fail:
                        result.failures.append(f"{code} ({folder_path}): " + "; ".join(row_fail))
                    else:
                        result.ok += 1
                else:
                    row = conn.execute(
                        "SELECT * FROM doujin_wanted_books WHERE source = ? AND code = ?",
                        (source, gid),
                    ).fetchone()
                    if row is None:
                        result.failures.append(f"{code}: no folder, and NO doujin_wanted_books row")
                        continue
                    row_fail = []
                    if row["favorite"] != favorite:
                        row_fail.append(f"favorite={row['favorite']!r} expected {favorite!r}")
                    if row["title"] != title:
                        row_fail.append(f"title={row['title']!r} expected {title!r}")
                    if row["artist"] != artist:
                        row_fail.append(f"artist={row['artist']!r} expected {artist!r}")
                    expected_wanted_thumb = expected_thumb_rel if thumb_exists_on_disk else None
                    if row["thumbnail_path"] != expected_wanted_thumb:
                        row_fail.append(
                            f"thumbnail_path={row['thumbnail_path']!r} expected {expected_wanted_thumb!r}"
                        )
                    if row_fail:
                        result.failures.append(f"{code} (wanted): " + "; ".join(row_fail))
                    else:
                        result.ok += 1
    finally:
        conn.close()

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 2. Thumbnail MD5 check
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ThumbnailCheck:
    total_source: int = 0
    matched: int = 0
    missing: list[str] = field(default_factory=list)
    mismatched: list[str] = field(default_factory=list)


def check_thumbnails(hv_dir: Path, data_dir: Path) -> ThumbnailCheck:
    result = ThumbnailCheck()
    src_dir = hv_dir / "thumbnail"
    dst_dir = data_dir / THUMBNAIL_SUBDIR
    if not src_dir.is_dir():
        return result

    with os.scandir(src_dir) as it:
        for entry in it:
            if not entry.is_file():
                continue
            result.total_source += 1
            dst = dst_dir / entry.name
            if not dst.is_file():
                result.missing.append(entry.name)
                continue
            src_hash = md5_of(Path(entry.path))
            dst_hash = md5_of(dst)
            if src_hash == dst_hash:
                result.matched += 1
            else:
                result.mismatched.append(f"{entry.name} (src={src_hash} dst={dst_hash})")
    return result


# ──────────────────────────────────────────────────────────────────────────────
# 3. Not-imported inventory
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class NotImportedEntry:
    name: str
    kind: str  # "file" | "dir"
    size_bytes: int
    note: str


def list_not_imported(hv_dir: Path) -> list[NotImportedEntry]:
    entries: list[NotImportedEntry] = []
    with os.scandir(hv_dir) as it:
        for e in it:
            if e.name in ("allData.json", "thumbnail"):
                continue
            kind = "dir" if e.is_dir() else "file"
            size = _dir_size(Path(e.path)) if kind == "dir" else os.path.getsize(e.path)
            note = KNOWN_NOT_IMPORTED_NOTES.get(
                e.name, "UNEXPECTED entry — not accounted for in the import design, needs review"
            )
            entries.append(NotImportedEntry(name=e.name, kind=kind, size_bytes=size, note=note))
    entries.sort(key=lambda x: x.name)
    return entries


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    from app.config import paths as app_paths

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hv-dir", help="Path to the legacy hentaiViewer folder")
    parser.add_argument("--download-dir", help="Override DOWNLOAD_DIR (default: app config)")
    parser.add_argument("--data-dir", help="Override DATA_DIR (default: app config)")
    args = parser.parse_args(argv)

    hv_dir = Path(args.hv_dir) if args.hv_dir else DEFAULT_HV_DIR
    download_dir = Path(args.download_dir) if args.download_dir else app_paths.DOWNLOAD_DIR
    data_dir = Path(args.data_dir) if args.data_dir else app_paths.DATA_DIR

    print(f"hentaiViewer source : {hv_dir}")
    print(f"download_dir         : {download_dir}")
    print(f"data_dir              : {data_dir}")
    print()

    if not hv_dir.is_dir():
        print(
            f"hentaiViewer folder not found at {hv_dir} — already deleted?\n"
            "This checker compares the OLD folder against the DB; with the old "
            "folder gone there is nothing left to re-verify against. This is "
            "NOT a PASS — it means the check cannot run.",
            file=sys.stderr,
        )
        return 2

    all_data_path = hv_dir / "allData.json"
    all_data = json.loads(all_data_path.read_text(encoding="utf-8"))
    total_records = sum(len(books) for books in all_data.values())

    print(f"=== 1. allData.json records ({total_records} expected) ===")
    rec = check_records(all_data, download_dir, data_dir)
    print(f"OK (per-record verified): {rec.ok} / {total_records}")
    if rec.unrecognized:
        print(f"UNRECOGNIZED codes ({len(rec.unrecognized)}): {rec.unrecognized}")
    if rec.failures:
        print(f"MISMATCH / MISSING ({len(rec.failures)}):")
        for line in rec.failures:
            print(f"  - {line}")
    print()

    print("=== 2. thumbnail/ files (per-file MD5) ===")
    thumb = check_thumbnails(hv_dir, data_dir)
    print(f"source files: {thumb.total_source}")
    print(f"matched (MD5-identical copy present): {thumb.matched}")
    if thumb.missing:
        print(f"MISSING at destination ({len(thumb.missing)}): {thumb.missing}")
    if thumb.mismatched:
        print(f"MD5 MISMATCH ({len(thumb.mismatched)}):")
        for line in thumb.mismatched:
            print(f"  - {line}")
    print()

    print("=== 3. Not imported — user's judgement ===")
    not_imported = list_not_imported(hv_dir)
    unexpected = [e for e in not_imported if e.note.startswith("UNEXPECTED")]
    for e in not_imported:
        print(f"  [{e.kind}] {e.name}  ({e.size_bytes} bytes)  -- {e.note}")
    print()

    failed = bool(
        rec.failures
        or rec.unrecognized
        or thumb.missing
        or thumb.mismatched
        or thumb.total_source != 600
        or total_records != 593
    )

    print("=== VERDICT ===")
    if failed:
        print("FAIL — DO NOT DELETE hentaiViewer/. See the failures listed above.")
        if unexpected:
            print(
                f"NOTE: {len(unexpected)} unexpected top-level entr(y/ies) in hentaiViewer/ "
                "were not part of the original import design — review before deciding."
            )
        return 1

    print(
        f"PASS — all {total_records} allData.json records verified per-record in the DB, "
        f"all {thumb.total_source} thumbnails verified by MD5. "
        f"{len(not_imported)} other item(s) in hentaiViewer/ were deliberately not imported "
        "(listed above) — review those yourself; deleting hentaiViewer/ is safe with respect "
        "to everything this checker verifies."
    )
    if unexpected:
        print(
            f"NOTE: {len(unexpected)} unexpected top-level entr(y/ies) found — not a failure, "
            "but not covered by the original import design either. Review before deleting."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
