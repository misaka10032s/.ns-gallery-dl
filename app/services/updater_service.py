from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta

# STALE_EXTRACTOR_SIGNATURES / is_stale_extractor_error moved to
# app.config.downloaders (2026-09-02, G4 layer-violation fix) — the two `as
# name` re-imports below are ruff/mypy's standard "intentional re-export"
# idiom (not a no-op), so `updater_service.is_stale_extractor_error(...)` /
# `updater_service.STALE_EXTRACTOR_SIGNATURES` keep resolving as module
# attributes for every existing caller (app.services.download_service,
# tests/test_updater_service.py, tests/test_gallery_dl_error_capture.py) with
# zero call-site changes — this module has no internal use of either name
# itself. See app/config/downloaders.py for the full docstring (signature
# list, gallery-dl/yt-dlp wording verification, why each phrase was chosen)
# and app/domain/auth_failure.py for the OTHER caller this move exists to
# unblock (it needed the same predicate but cannot import app.services —
# app.domain sits below it in the layers contract).
from app.config.downloaders import (
    DOWNLOADER_PACKAGES,
    PIP_UPDATE_TIMEOUT_SECONDS,
    UPDATE_COOLDOWN_SECONDS,
)
from app.config.downloaders import STALE_EXTRACTOR_SIGNATURES as STALE_EXTRACTOR_SIGNATURES
from app.config.downloaders import is_stale_extractor_error as is_stale_extractor_error
from app.storage.db import init_db
from app.storage.repositories import downloader_state_repo


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
    AFTER via `<package> --version` subprocess calls. The pip call is bounded by
    PIP_UPDATE_TIMEOUT_SECONDS (app/config/downloaders.py) — this runs
    synchronously inside the single queue worker thread, so an unbounded network
    hang would otherwise freeze the whole download queue.

    Returns {"package", "old_version", "new_version", "changed": bool,
    "timed_out": bool}. On a timeout: `changed` is always False (we don't know
    whether the upgrade actually landed, so we never claim/signal a version
    change) and `timed_out` is True so the caller can distinguish "confirmed
    already latest" from "couldn't even check".
    """
    old_version = _get_version(package)
    timed_out = False
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", package],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PIP_UPDATE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        timed_out = True

    new_version = _get_version(package)
    changed = not timed_out and new_version is not None and new_version != old_version
    return {
        "package": package,
        "old_version": old_version,
        "new_version": new_version,
        "changed": changed,
        "timed_out": timed_out,
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
      - Otherwise → run update_downloader():
          - if the pip call TIMED OUT → do NOT persist any state (a timeout is
            NOT "successfully confirmed latest" — persisting it would wrongly
            arm the cooldown and suppress a real check later); do NOT retry;
            return a clear zh-TW timeout message.
          - if the version actually changed → persist the freshly-checked
            version + timestamp, signal the caller to retry the job once.
          - if it did NOT change (already latest) → persist state (refreshing
            the cooldown) and return the "already latest" message instead of
            retrying (guards against an update→fail→update loop).

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

    if result["timed_out"]:
        # NOT persisted: a timeout means we never actually confirmed a version —
        # recording it now would incorrectly arm the cooldown and could suppress
        # a real check on the next failure. No retry either (we don't know if
        # anything changed).
        return {
            "retried": False,
            "changed": False,
            "message": f"更新 {package} 逾時（pip 安裝逾時，可能是網路問題），已略過重試，稍後可再試一次",
        }

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
