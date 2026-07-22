from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta

from app.config.downloaders import DOWNLOADER_PACKAGES, UPDATE_COOLDOWN_SECONDS
from app.storage.db import init_db
from app.storage.repositories import downloader_state_repo

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


def _get_version(command: str) -> str | None:
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr or "").strip()
    if not output:
        return None
    return output.splitlines()[0].strip()


def get_installed_version(package: str) -> str | None:
    """Version of `package`'s CLI, via `<package> --version` (None if not resolvable)."""
    return _get_version(package)


def update_downloader(package: str) -> dict:
    """
    Upgrade one pip package via `python -m pip install -U <package>` (never `import
    pip` — pip is not a stable import API). Reads the tool's version BEFORE and
    AFTER via `<package> --version` subprocess calls.

    Returns {"package", "old_version", "new_version", "changed": bool}.
    """
    old_version = _get_version(package)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-U", package],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    new_version = _get_version(package)
    changed = new_version is not None and new_version != old_version
    return {
        "package": package,
        "old_version": old_version,
        "new_version": new_version,
        "changed": changed,
    }


def update_all_downloaders() -> list[dict]:
    """Update every registered downloader package (app.config.downloaders.DOWNLOADER_PACKAGES)."""
    return [update_downloader(package) for package in DOWNLOADER_PACKAGES.values()]


def package_for_provider(provider_value: str) -> str | None:
    return DOWNLOADER_PACKAGES.get(provider_value)


def maybe_reactive_update(provider_value: str) -> dict:
    """
    Anti-mindless-update guard for the on-error reactive hook.

    Called ONLY after a download failure was classified as a likely stale-extractor
    error for `provider_value`. Decides whether to actually run a pip upgrade:

      - If we're within the cooldown window AND the installed version still equals
        the version we last confirmed → SKIP the update entirely (no pip call, no
        retry) and return a clear "already latest, not a version problem" message.
      - Otherwise → run update_downloader(), persist the freshly-checked version +
        timestamp (refreshing the cooldown either way), and:
          - if the version actually changed → signal the caller to retry the job once.
          - if it did NOT change (already latest) → return the same "already latest"
            message instead of retrying (guards against an update→fail→update loop).

    Returns {"retried": bool, "changed": bool, "message": str}. `message` is only
    set on a non-retry outcome (empty string when `retried` is True) — the caller
    is expected to keep the original download error in that case.
    """
    package = package_for_provider(provider_value)
    if not package:
        return {"retried": False, "changed": False, "message": ""}

    init_db()
    state = downloader_state_repo.get_state(package)
    installed = get_installed_version(package)
    now = datetime.now()

    within_cooldown = False
    if state and state.get("last_checked_at"):
        try:
            last_checked_at = datetime.fromisoformat(state["last_checked_at"])
            within_cooldown = (now - last_checked_at) < timedelta(seconds=UPDATE_COOLDOWN_SECONDS)
        except ValueError:
            within_cooldown = False
    already_confirmed_latest = bool(state and installed and state.get("last_checked_version") == installed)

    if within_cooldown and already_confirmed_latest:
        return {
            "retried": False,
            "changed": False,
            "message": f"已是最新 {package} {installed},仍失敗(上游 extractor 可能已變動,非版本問題)",
        }

    result = update_downloader(package)
    downloader_state_repo.set_state(
        package,
        result["new_version"] or installed or "",
        now.isoformat(timespec="seconds"),
    )

    if result["changed"]:
        return {"retried": True, "changed": True, "message": ""}

    version_label = result["new_version"] or installed or "未知版本"
    return {
        "retried": False,
        "changed": False,
        "message": f"已是最新 {package} {version_label},仍失敗(上游 extractor 可能已變動,非版本問題)",
    }
