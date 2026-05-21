from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

from app.config.paths import ROOT_DIR, UI_DIR


FRONTEND_DIR = ROOT_DIR / "frontend"
FRONTEND_ENTRY = UI_DIR / "index.html"


def _source_paths() -> list[Path]:
    if not FRONTEND_DIR.exists():
        return []
    paths = [
        FRONTEND_DIR / "package.json",
        FRONTEND_DIR / "package-lock.json",
        FRONTEND_DIR / "vite.config.js",
        FRONTEND_DIR / "index.html",
    ]
    paths.extend(path for path in (FRONTEND_DIR / "src").rglob("*") if path.is_file())
    paths.extend(path for path in (FRONTEND_DIR / "public").rglob("*") if path.is_file())
    return [path for path in paths if path.exists()]


def _latest_source_mtime() -> float:
    return max((path.stat().st_mtime for path in _source_paths()), default=0.0)


def needs_build() -> bool:
    if not FRONTEND_DIR.exists():
        return False
    if not FRONTEND_ENTRY.exists():
        return True
    return _latest_source_mtime() > FRONTEND_ENTRY.stat().st_mtime


def ensure_frontend_ready() -> None:
    if not FRONTEND_DIR.exists():
        return

    npm = which("npm")
    if not npm:
        raise RuntimeError("npm is required to build the frontend, but it was not found in PATH.")

    print("[*] Checking frontend build state...")

    if not (FRONTEND_DIR / "node_modules").exists():
        print("[*] Frontend dependencies missing. Running npm install...")
        subprocess.run([npm, "install"], cwd=FRONTEND_DIR, check=True)

    if needs_build():
        print("[*] Frontend source changed. Running npm run build...")
        subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)
    else:
        print("[*] Frontend build is up to date.")
