from __future__ import annotations

# Central registry: EVERY downloader tool this app manages, keyed by its provider
# identifier (matches app.domain.enums.Provider.value where one exists).  Value is the
# pip package name — which today is also the CLI command name (`<value> --version`),
# true for every entry below.  Adding a future downloader (e.g. a new site-specific
# CLI tool) is ONE line here; app.services.updater_service, the manual API endpoint,
# and the launcher scripts all derive from this dict — nothing else needs editing.
DOWNLOADER_PACKAGES: dict[str, str] = {
    "ytdlp": "yt-dlp",
    "gallery-dl": "gallery-dl",
}

# Reactive-update guard (anti-mindless-update): after a "stale extractor" failure
# triggers an update check for a package, if the installed version still equals what
# we last confirmed AND we're within this cooldown window, skip re-checking/updating
# again — the failure is treated as a non-version upstream issue instead of retried
# in a loop.  Default 6 hours.
UPDATE_COOLDOWN_SECONDS = 6 * 60 * 60

# `python -m pip install -U <package>` timeout. The reactive hook runs this
# synchronously inside the single queue worker thread — with NO timeout, a
# network hang (registry unreachable, slow mirror, ...) would block the entire
# download queue indefinitely. 300s is generous for a single small package.
PIP_UPDATE_TIMEOUT_SECONDS = 300
