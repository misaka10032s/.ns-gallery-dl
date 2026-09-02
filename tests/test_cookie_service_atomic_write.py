"""
tests/test_cookie_service_atomic_write.py

app.services.cookie_service._atomic_write_text / save_cookie — the atomic
write from dispatch item 5 (phase 1a). gallery-dl and yt-dlp both rewrite
these SAME cookie files after every run (gallery-dl's own `cookies_store()`,
gallery_dl/extractor/common.py, already uses `os.replace()` for exactly this
reason), so a crash mid-write via the OLD `path.write_text()` could leave a truncated
jar that `http.cookiejar` silently treats as empty — the exact silent
downgrade-to-guest-session failure this whole phase exists to catch.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from app.services import cookie_service


class TestAtomicWriteUsesReplace:
    def test_save_cookie_calls_os_replace_not_a_direct_truncate(self, tmp_cookie_dir):
        # wraps=os.replace: still performs the REAL rename (so the rest of
        # save_cookie's pipeline — scan_cookie_files(), read_cookie() — sees
        # a genuine file at `path`), while still letting us assert the call.
        with patch("app.services.cookie_service.os.replace", wraps=os.replace) as mock_replace:
            cookie_service.save_cookie("example.com", "Cookie: a=1; b=2")
        mock_replace.assert_called_once()
        # the replace target must be the FINAL cookie path, never left as a
        # dangling .tmp — the literal `assert` this repo's own G3(b) gate
        # requires, on top of the mock-call check above.
        replace_args = mock_replace.call_args[0]
        assert replace_args[1].name == "cookies-example-com.txt"

    def test_no_leftover_temp_file_after_a_successful_save(self, tmp_cookie_dir):
        cookie_service.save_cookie("example.com", "Cookie: a=1; b=2")
        leftovers = list(tmp_cookie_dir.glob("*.tmp"))
        assert leftovers == []

    def test_content_is_correct_after_atomic_save(self, tmp_cookie_dir):
        record = cookie_service.save_cookie("example.com", "Cookie: a=1; b=2")
        content = Path(record["file_path"]).read_text(encoding="utf-8")
        assert "# Netscape HTTP Cookie File" in content
        assert "\ta\t1" in content
        assert "\tb\t2" in content


class TestOriginalFileSurvivesAFailedWrite:
    def test_a_write_that_dies_mid_way_leaves_the_original_content_intact(self, tmp_cookie_dir):
        """The whole point of atomicity: if the process dies WHILE writing
        the temp file (before os.replace() ever runs), the file at `path`
        must still hold its PREVIOUS good content — never a truncated
        half-write. Simulated by making the temp-file write itself raise
        partway through, on the SECOND save."""
        first_record = cookie_service.save_cookie("example.com", "Cookie: a=1; b=2")
        first_path = Path(first_record["file_path"])
        first_content = first_path.read_text(encoding="utf-8")

        class _DyingHandle:
            """Mimics the REAL os.fdopen(fd, ...)'s context-manager contract
            (closes the underlying fd on __exit__, exception or not) so this
            test's Windows behavior matches production: a real os.fdopen
            wrapper always closes its fd before _atomic_write_text's except
            block tries to os.unlink() the temp file — Windows refuses to
            delete a file that still has an open handle, so skipping this
            close (as a naive full-mock of os.fdopen would) produces a
            Windows-only false failure that has nothing to do with the
            production code path being tested."""

            def __init__(self, fd):
                self._fd = fd

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                os.close(self._fd)
                return False

            def write(self, _data):
                raise OSError("simulated crash mid-write")

        with patch("app.services.cookie_service.os.fdopen", side_effect=lambda fd, *a, **kw: _DyingHandle(fd)):
            try:
                cookie_service.save_cookie("example.com", "Cookie: a=1; b=999")
            except OSError:
                pass

        assert first_path.read_text(encoding="utf-8") == first_content
        # the doomed temp file must not survive either
        assert list(tmp_cookie_dir.glob("*.tmp")) == []


class TestLineEndingAndHeaderFormatPreserved:
    def test_netscape_header_survives_a_full_content_passthrough_save(self, tmp_cookie_dir):
        """A Netscape cookie jar's header must never be mangled by the
        write mechanism change — a bad header is silently ignored by the
        tools that read it (gallery-dl/yt-dlp), which is exactly the
        failure class this phase exists to catch."""
        full_jar = "# Netscape HTTP Cookie File\n\n.example.com\tTRUE\t/\tTRUE\t0\tauth_token\tSECRETVALUE\n"
        record = cookie_service.save_cookie("example.com", full_jar)
        content = Path(record["file_path"]).read_text(encoding="utf-8")
        assert content == full_jar
