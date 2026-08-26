from __future__ import annotations

# Which top-level download sources are presented in "doujinshi" (本子) mode: one
# subfolder = one book -> cover wall -> page-by-page reader, with editable book
# fields. Every other source stays in "general" mode (thumbnail wall, at most
# grouped by artist folder — unchanged).
#
# This is the ONLY place that decides source -> mode. Adding a future
# doujinshi-shaped source (e.g. a fifth site) is ONE line here; nothing in
# app/services/doujin_service.py, app/api/routes/gallery.py, or the frontend
# needs to change.
MODE_GENERAL = "general"
MODE_DOUJINSHI = "doujinshi"

DOUJINSHI_SOURCES: frozenset[str] = frozenset({"wnacg", "nhentai", "18comic", "exhentai"})


def resolve_mode(source: str) -> str:
    """Return which gallery presentation mode a top-level download source uses."""
    return MODE_DOUJINSHI if source in DOUJINSHI_SOURCES else MODE_GENERAL
