#!/usr/bin/env python
"""G1 — ruff lint, baselined: FAIL only on NEW violations relative to a version-controlled
baseline (quality-gates/ruff-baseline.json). Same pattern as G2/G4, built on lib/baseline.py.

Why baselined rather than a bare `ruff check`: this tree already carries 49 pre-existing
findings across app/module/tests (measured 2026-08-27 with the select set below — mostly I001
unsorted-imports and F401 unused-import) — a bare pass/fail would make L0 permanently red on
the untouched tree. This gate does NOT fix those 49 — they stay in the baseline for a human to
burn down; --update-baseline is for a deliberate, reviewed cleanup (or knowingly accepting a
new one), never a blanket bypass.

SCOPE (explicit, not "."): only app/, module/, scripts/, tests/ are scanned — the exact same
list every OTHER gate in this recipe scans. This is a deliberate exclusion, not ruff's own
default excludes: `venv/`, `download/`, `save/`, `data/`, `cookies/`, `.pytest_cache/`,
`__pycache__/` all sit at the repo root and are gitignored working/scratch dirs (see
.gitignore) — a stray .py file dropped there must NEVER become a gate input. Proven both ways
(scratch dir ignored -> exit 0; same violation in a real scanned dir -> exit 1) — evidence in
.claude/CLAUDE.md -> `## Code quality gates`.

Identity key = "relative/file.py|CODE|message text" — deliberately excludes the line number
so a violation that merely shifted a few lines from an unrelated edit above it doesn't
register as new.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import baseline as baseline_lib
from lib.git_diff import ensure_utf8_stdio

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "ruff-baseline.json"
# `scripts/` is currently EMPTY (0 .py files; git does not track empty dirs, so it isn't even
# materialized in a fresh checkout — confirmed 2026-08-27) and would make ruff itself error
# ("file not found") if passed as a scan target. Add it back the moment it gains a .py file.
SCAN_DIRS = ["app", "module", "tests"]


def _run_ruff() -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *SCAN_DIRS, "--output-format=json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # ruff writes the JSON report to stdout regardless of exit code ([] + exit 0 when clean).
    return json.loads(proc.stdout or "[]")


def _identity(item: dict) -> str:
    rel = Path(item["filename"]).resolve().relative_to(ROOT).as_posix()
    return f"{rel}|{item['code']}|{item['message']}"


def main() -> int:
    update_mode = "--update-baseline" in sys.argv[1:]
    items = _run_ruff()
    current = sorted({_identity(i) for i in items})

    if update_mode:
        baseline_lib.write(BASELINE_PATH, current)
        print(f"[G1] baseline updated — {len(current)} violation(s) recorded at {BASELINE_PATH.name}.")
        return 0

    baseline = baseline_lib.load(BASELINE_PATH)
    new, resolved = baseline_lib.diff(current, baseline)

    if resolved:
        print(
            f"[G1] note: {len(resolved)} baseline violation(s) no longer exist — "
            "consider re-running with --update-baseline to shrink the baseline:"
        )
        for v in resolved:
            print(f"  - {v}")

    if new:
        print(f"[G1] FAIL — {len(new)} NEW ruff violation(s) not present in the baseline:", file=sys.stderr)
        for v in new:
            print(f"  - {v}", file=sys.stderr)
        print(
            f"\nBaseline: {BASELINE_PATH.name} ({len(baseline)} pre-existing violation(s), unaffected).",
            file=sys.stderr,
        )
        return 1

    print(f"[G1] PASS — {len(current)} total violation(s), 0 new vs baseline ({len(baseline)} pre-existing).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
