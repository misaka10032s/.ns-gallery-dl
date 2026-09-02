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

# Moved here from app.services.updater_service (2026-09-02, G4 layer-violation
# fix): app.domain.auth_failure.classify() needs this predicate (an extractor
# bug is confidently NOT a credential problem, so it's checked before the AUTH
# signals), and app.domain sits BELOW app.services in the layers contract
# (pyproject.toml [tool.importlinter]), so app.domain cannot import
# app.services without creating an illegal upward edge. app.config is the
# BOTTOM layer, so both app.domain.auth_failure and app.services.updater_service
# (which still owns the real reactive-update behaviour and re-imports this pair
# below exactly like DOWNLOADER_PACKAGES/UPDATE_COOLDOWN_SECONDS/
# PIP_UPDATE_TIMEOUT_SECONDS above) can both import it downward, legally.
#
# app.config was NOT the only legal destination, and this comment used to
# imply it was — it isn't a forced move. app.services -> app.domain is ALSO a
# legal downward edge under this same contract (this branch's own
# app.services.cookie_service imports app.domain.auth_cooldown that way), so
# is_stale_extractor_error() below — a 3-line predicate reading only its own
# neighbouring constant — could equally have lived in app/domain/ with
# app.services.updater_service importing it downward instead, keeping all
# behaviour out of the config layer entirely. STALE_EXTRACTOR_SIGNATURES
# itself genuinely is downloader configuration and belongs here regardless of
# where the predicate goes; only the predicate's placement was a choice, not
# a requirement.
#
# Conservative, low-false-positive "stale extractor" signatures. Matched case-
# insensitively against a FAILED download's error message. Kept centralized and
# tight on purpose — a broad match would trigger pointless pip upgrades on
# unrelated failures (auth walls, network errors, cookie problems, ...).
#
#   - "cannot parse data" — yt-dlp's extractor-broke phrasing.
#   - "unable to extract" — shared: yt-dlp's phrasing AND gallery-dl's
#     `exception.AbortExtraction` messages (verified in gallery-dl's own extractor
#     source, e.g. patreon.py "Unable to extract bootstrap data", pixiv.py
#     "Unable to extract Ugoira URL", bilibili.py "Unable to extract INITIAL_STATE
#     data" — all raised when a site's page/API structure changed).
#   - "failed to parse json data"   — gallery-dl's JSONDecodeError catch-all
#     (job.py: `log.error("Failed to parse JSON data:  %s: %s", ...)`); the
#     classic "site's API response shape changed" symptom.
#   - "an unexpected error occurred" — gallery-dl's generic per-extractor
#     exception catch-all (job.py: `log.error("An unexpected error occurred: %s
#     - %s. Please run gallery-dl again with --verbose ...")`) — fires on ANY
#     unhandled exception while an extractor runs (KeyError/AttributeError/...),
#     which in practice is overwhelmingly "the site changed and the extractor's
#     assumptions broke", not a gallery-dl bug.
#
# Verified live against the installed gallery-dl CLI: `[gallery-dl][error]
# Unsupported URL '...'` / `[danbooru][error] HttpError: '404 Not Found' for
# '...'` — confirming gallery-dl's real wording is `[<name>][error] <message>`,
# printed to stderr (gallery_dl/output.py LOG_FORMAT). Deliberately NOT matched:
# "unsupported url" (ambiguous — could just be a genuinely unsupported site, not
# staleness) and "no results" (that's an INFO-level log for a legitimately empty
# gallery, not a FAILED-path error — never reaches this classifier in practice).
STALE_EXTRACTOR_SIGNATURES: tuple[str, ...] = (
    "cannot parse data",
    "unable to extract",
    "failed to parse json data",
    "an unexpected error occurred",
)


def is_stale_extractor_error(error: str | None) -> bool:
    """Classify a download failure's error text as a likely stale-extractor issue."""
    if not error:
        return False
    lowered = error.lower()
    return any(signature in lowered for signature in STALE_EXTRACTOR_SIGNATURES)
