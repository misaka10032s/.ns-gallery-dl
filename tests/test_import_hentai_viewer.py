"""
tests/test_import_hentai_viewer.py

Covers app/scripts/import_hentai_viewer.py and
app/scripts/check_hentai_viewer_import.py against a small SYNTHETIC
hentaiViewer source + download tree (never the real 593-record library —
fast, deterministic, and every assertion traces to a value this test itself
wrote). Real-data numbers (593 records / 232 matched / 361 wanted / 600
thumbnails / 7 orphans) were verified separately during development and are
reported in the blueprint entry + commit message, not re-asserted here.

Covers:
- split_hv_code: the code -> (source, id) split
- scan_source_ids: matching a record to an existing download/ folder
- the no-folder path (doujin_wanted_books)
- manual-edit-wins (title_override) + not clobbering an existing site fetch
- idempotency (run twice, no duplication, no re-copy)
- orphan thumbnails (copied even with no allData.json record)
- promotion (a wanted record whose folder later appears gets migrated)
- the checker's per-record / per-file MD5 verification, including that it
  actually FAILS loudly on an injected mismatch
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scripts import check_hentai_viewer_import as checker
from app.scripts import import_hentai_viewer as importer
from app.storage.repositories import doujin_repo


# ──────────────────────────────────────────────────────────────────────────────
# Fixture builder — a small synthetic hentaiViewer source + download tree
# ──────────────────────────────────────────────────────────────────────────────

RECORDS = {
    "artist one": {
        "N100001": {"title": "Title A", "favorite": 1},   # matched
        "N100002": {"title": "Title B", "favorite": 0},   # no folder -> wanted
    },
    "artist two": {
        "W200001": {"title": "Title C", "favorite": 1},   # matched
    },
}
ORPHAN_CODE = "N999999"  # thumbnail with no allData.json record


def _build_hv_dir(tmp_path: Path) -> Path:
    hv_dir = tmp_path / "hentaiViewer"
    (hv_dir / "thumbnail").mkdir(parents=True)
    (hv_dir / "allData.json").write_text(json.dumps(RECORDS, ensure_ascii=False), encoding="utf-8")
    for artist, books in RECORDS.items():
        for code in books:
            (hv_dir / "thumbnail" / f"{code}.jpg").write_bytes(f"thumb-{code}".encode())
    (hv_dir / "thumbnail" / f"{ORPHAN_CODE}.jpg").write_bytes(b"thumb-orphan")
    return hv_dir


def _build_download_dir(tmp_path: Path, *, with_matches: bool = True) -> Path:
    download_dir = tmp_path / "download"
    if with_matches:
        n1 = download_dir / "nhentai" / "100001_Something Great [Chinese]"
        n1.mkdir(parents=True)
        (n1 / "001.jpg").write_bytes(b"page1")
        (n1 / "002.jpg").write_bytes(b"page2")

        w1 = download_dir / "wnacg" / "200001_Other Thing"
        w1.mkdir(parents=True)
        (w1 / "001.png").write_bytes(b"page1")
        (w1 / "002.png").write_bytes(b"page2")
        (w1 / "003.png").write_bytes(b"page3")
    else:
        download_dir.mkdir(parents=True)
    return download_dir


# ──────────────────────────────────────────────────────────────────────────────
# split_hv_code
# ──────────────────────────────────────────────────────────────────────────────


class TestSplitHvCode:
    def test_nhentai_prefix(self):
        assert importer.split_hv_code("N105189") == ("nhentai", "105189")

    def test_wnacg_prefix(self):
        assert importer.split_hv_code("W12345") == ("wnacg", "12345")

    def test_unknown_prefix_raises(self):
        with pytest.raises(ValueError):
            importer.split_hv_code("X123")

    def test_non_numeric_id_raises(self):
        with pytest.raises(ValueError):
            importer.split_hv_code("Nabc")

    def test_empty_code_raises(self):
        with pytest.raises(ValueError):
            importer.split_hv_code("")


# ──────────────────────────────────────────────────────────────────────────────
# scan_source_ids — matching a record to an existing folder
# ──────────────────────────────────────────────────────────────────────────────


class TestScanSourceIds:
    def test_matches_underscore_and_space_prefix(self, tmp_path):
        d = tmp_path / "nhentai"
        (d / "111_Underscore Name").mkdir(parents=True)
        (d / "222 Space Name").mkdir(parents=True)
        (d / "NoPrefixHere").mkdir(parents=True)
        ids = importer.scan_source_ids(d)
        assert ids == {"111": "111_Underscore Name", "222": "222 Space Name"}

    def test_missing_dir_returns_empty(self, tmp_path):
        assert importer.scan_source_ids(tmp_path / "does-not-exist") == {}

    def test_ignores_files(self, tmp_path):
        d = tmp_path / "nhentai"
        d.mkdir(parents=True)
        (d / "111_stray.txt").write_text("x")
        assert importer.scan_source_ids(d) == {}


# ──────────────────────────────────────────────────────────────────────────────
# copy_thumbnail_idempotent
# ──────────────────────────────────────────────────────────────────────────────


class TestCopyThumbnailIdempotent:
    def test_first_copy_reports_copied(self, tmp_path):
        src = tmp_path / "src.jpg"
        src.write_bytes(b"hello")
        dst = tmp_path / "out" / "src.jpg"
        assert importer.copy_thumbnail_idempotent(src, dst) == "copied"
        assert dst.read_bytes() == b"hello"

    def test_second_copy_same_content_is_skipped(self, tmp_path):
        src = tmp_path / "src.jpg"
        src.write_bytes(b"hello")
        dst = tmp_path / "out" / "src.jpg"
        importer.copy_thumbnail_idempotent(src, dst)
        assert importer.copy_thumbnail_idempotent(src, dst) == "skipped-identical"

    def test_differing_destination_is_overwritten(self, tmp_path):
        src = tmp_path / "src.jpg"
        src.write_bytes(b"hello")
        dst = tmp_path / "out" / "src.jpg"
        dst.parent.mkdir(parents=True)
        dst.write_bytes(b"stale-different-content")
        assert importer.copy_thumbnail_idempotent(src, dst) == "copied"
        assert dst.read_bytes() == b"hello"


# ──────────────────────────────────────────────────────────────────────────────
# run_import — matched / wanted / manual-edit-wins / idempotency / orphans /
# promotion
# ──────────────────────────────────────────────────────────────────────────────


class TestRunImport:
    def test_matched_record_writes_fetched_fields_favorite_and_thumbnail(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)
        data_dir = tmp_path  # tmp_db already points DATA_DIR/DB_FILE here

        result = importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=data_dir)

        assert result.total_records == 3
        assert result.matched == 2
        assert result.wanted == 1

        book = doujin_repo.get_book("nhentai/100001_Something Great [Chinese]")
        assert book is not None
        assert book["title_fetched"] == "Title A"
        assert book["artist_fetched"] == "artist one"
        assert book["title_override"] is None  # never written into the manual channel
        assert book["imported_favorite"] == 1
        assert book["imported_thumbnail"] == "doujin_thumbnails/N100001.jpg"
        assert book["page_count"] == 2  # real on-disk page count, not a guess

        w1 = doujin_repo.get_book("wnacg/200001_Other Thing")
        assert w1["imported_favorite"] == 1
        assert w1["page_count"] == 3

    def test_unmatched_record_creates_wanted_book(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)
        importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)

        wanted = doujin_repo.get_wanted_book("nhentai", "100002")
        assert wanted is not None
        assert wanted["title"] == "Title B"
        assert wanted["artist"] == "artist one"
        assert wanted["favorite"] == 0
        assert wanted["thumbnail_path"] == "doujin_thumbnails/N100002.jpg"

        # a wanted record must never also appear as a doujin_books row
        assert doujin_repo.get_book("nhentai/100002") is None

    def test_manual_override_is_never_overwritten(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)
        folder_path = "nhentai/100001_Something Great [Chinese]"

        doujin_repo.ensure_book(folder_path, {"page_count": 2})
        doujin_repo.update_book(folder_path, {"title_override": "USER TITLE"}, {"page_count": 2})

        importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)

        book = doujin_repo.get_book(folder_path)
        assert book["title_override"] == "USER TITLE"
        assert book["title_fetched"] is None  # import declined to write it
        # import-owned columns still get written even when override is set
        assert book["imported_favorite"] == 1

    def test_existing_site_fetch_is_never_overwritten(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)
        folder_path = "nhentai/100001_Something Great [Chinese]"

        doujin_repo.ensure_book(folder_path, {"page_count": 2})
        doujin_repo.update_book(
            folder_path,
            {"title_fetched": "REAL SITE FETCH TITLE", "artist_fetched": "REAL SITE ARTIST"},
            {"page_count": 2},
        )

        importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)

        book = doujin_repo.get_book(folder_path)
        assert book["title_fetched"] == "REAL SITE FETCH TITLE"
        assert book["artist_fetched"] == "REAL SITE ARTIST"

    def test_orphan_thumbnail_is_copied_with_no_book_or_wanted_row(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)
        result = importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)

        assert result.thumbnails_orphaned == 1
        orphan_dst = tmp_path / importer.THUMBNAIL_SUBDIR / f"{ORPHAN_CODE}.jpg"
        assert orphan_dst.is_file()
        assert orphan_dst.read_bytes() == b"thumb-orphan"
        assert doujin_repo.get_wanted_book("nhentai", "999999") is None

    def test_running_twice_is_idempotent(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)

        first = importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)
        assert first.thumbnails_copied == 4  # 3 records + 1 orphan

        book_before = doujin_repo.get_book("nhentai/100001_Something Great [Chinese]")
        wanted_before = doujin_repo.list_wanted_books()

        second = importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)

        assert second.matched == first.matched
        assert second.wanted == first.wanted
        assert second.thumbnails_copied == 0
        assert second.thumbnails_skipped_identical == 4

        book_after = doujin_repo.get_book("nhentai/100001_Something Great [Chinese]")
        wanted_after = doujin_repo.list_wanted_books()
        # updated_at legitimately advances on every write (same convention as
        # the rest of doujin_repo) even when the written value is unchanged —
        # idempotency means no duplicate ROWS and no VALUE drift, not a frozen
        # timestamp, so compare everything else and the timestamp separately.
        assert {k: v for k, v in book_after.items() if k != "updated_at"} == {
            k: v for k, v in book_before.items() if k != "updated_at"
        }
        assert len(wanted_after) == len(wanted_before)
        for before, after in zip(wanted_before, wanted_after):
            assert {k: v for k, v in after.items() if k != "updated_at"} == {
                k: v for k, v in before.items() if k != "updated_at"
            }

    def test_wanted_record_promoted_once_a_folder_appears(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)

        first = importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)
        assert first.promoted == 0
        assert doujin_repo.get_wanted_book("nhentai", "100002") is not None

        # the user downloads it — a matching folder now exists
        n2 = download_dir / "nhentai" / "100002_Newly Downloaded"
        n2.mkdir(parents=True)
        (n2 / "001.jpg").write_bytes(b"page1")

        second = importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)
        assert second.promoted == 1
        assert second.wanted == 0
        assert doujin_repo.get_wanted_book("nhentai", "100002") is None
        promoted_book = doujin_repo.get_book("nhentai/100002_Newly Downloaded")
        assert promoted_book["title_fetched"] == "Title B"
        assert promoted_book["imported_favorite"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Checker — per-record / per-file verification, incl. that it actually fails
# ──────────────────────────────────────────────────────────────────────────────


class TestChecker:
    def test_passes_after_a_clean_import(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)
        importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)

        from app.storage import db as db_module

        all_data = json.loads((hv_dir / "allData.json").read_text(encoding="utf-8"))
        rec = checker.check_records(all_data, download_dir, db_module.DATA_DIR, db_path=db_module.DB_FILE)
        assert rec.failures == []
        assert rec.ok == 3

        thumb = checker.check_thumbnails(hv_dir, db_module.DATA_DIR)
        assert thumb.missing == []
        assert thumb.mismatched == []
        assert thumb.matched == 4

    def test_missing_db_row_is_reported_by_name(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)
        importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)

        from app.storage.db import execute
        from app.storage import db as db_module

        # simulate a broken import: delete the row for the matched N100001 book
        execute(
            "DELETE FROM doujin_books WHERE folder_path = ?",
            ("nhentai/100001_Something Great [Chinese]",),
        )

        all_data = json.loads((hv_dir / "allData.json").read_text(encoding="utf-8"))
        rec = checker.check_records(all_data, download_dir, db_module.DATA_DIR, db_path=db_module.DB_FILE)
        assert rec.ok == 2
        assert len(rec.failures) == 1
        assert "N100001" in rec.failures[0]

    def test_thumbnail_content_mismatch_is_reported_by_name(self, tmp_path, tmp_db):
        hv_dir = _build_hv_dir(tmp_path)
        download_dir = _build_download_dir(tmp_path)
        importer.run_import(hv_dir=hv_dir, download_dir=download_dir, data_dir=tmp_path)

        from app.storage import db as db_module

        corrupted = db_module.DATA_DIR / importer.THUMBNAIL_SUBDIR / "N100001.jpg"
        corrupted.write_bytes(b"CORRUPTED CONTENT")

        thumb = checker.check_thumbnails(hv_dir, db_module.DATA_DIR)
        assert thumb.matched == 3
        assert len(thumb.mismatched) == 1
        assert "N100001.jpg" in thumb.mismatched[0]

    def test_list_not_imported_names_every_other_entry(self, tmp_path):
        hv_dir = _build_hv_dir(tmp_path)
        (hv_dir / "Link.txt").write_bytes(b"")
        (hv_dir / "backup").mkdir()
        (hv_dir / "backup" / "old.json").write_text("{}")

        entries = {e.name: e for e in checker.list_not_imported(hv_dir)}
        assert set(entries) == {"Link.txt", "backup"}
        assert entries["Link.txt"].size_bytes == 0
        assert entries["backup"].kind == "dir"
        assert not entries["Link.txt"].note.startswith("UNEXPECTED")

    def test_unknown_entry_is_flagged_unexpected(self, tmp_path):
        hv_dir = _build_hv_dir(tmp_path)
        (hv_dir / "some_new_file.dat").write_bytes(b"???")
        entries = {e.name: e for e in checker.list_not_imported(hv_dir)}
        assert entries["some_new_file.dat"].note.startswith("UNEXPECTED")
