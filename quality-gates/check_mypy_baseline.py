#!/usr/bin/env python
"""G2 — mypy typecheck, baselined: FAIL only on NEW errors relative to a version-controlled
baseline (quality-gates/mypy-baseline.json). Same pattern as G1/G4.

This tree carries 15 pre-existing mypy errors in 8 files (measured 2026-08-27, non-strict
profile — see pyproject.toml `[tool.mypy]` for why this is NOT strict mode) — not fixed by
this gate, recorded in the baseline for a human to burn down.

SCOPE: `app/` ONLY, not module/scripts/tests. `module/` is a thin legacy compat re-export
shim (see .claude/CLAUDE.md `## Project structure`) whose only content is re-exporting names
from `app.*` — mypy's default `--follow-imports=normal` means checking `module/` also
re-reports every `app/` error a second time under the `module` invocation, which is pure
duplication, not new signal. `scripts/` is currently empty. `tests/` is covered by G3
(pytest itself catches real breakage there); typing test fixtures is not this gate's job.

Identity key = "relative/file.py|CODE|message text", same line-drift-tolerant shape as G1.
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
BASELINE_PATH = Path(__file__).resolve().parent / "mypy-baseline.json"


def _run_mypy() -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "app", "--output=json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    items = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a non-JSON summary/crash line — ignore rather than crash the gate
    return [item for item in items if item.get("severity") == "error"]


def _identity(item: dict) -> str:
    rel = Path(item["file"]).as_posix()
    return f"{rel}|{item['code']}|{item['message']}"


def main() -> int:
    update_mode = "--update-baseline" in sys.argv[1:]
    items = _run_mypy()
    current = sorted({_identity(i) for i in items})

    if update_mode:
        baseline_lib.write(BASELINE_PATH, current)
        print(f"[G2] baseline updated — {len(current)} error(s) recorded at {BASELINE_PATH.name}.")
        return 0

    baseline = baseline_lib.load(BASELINE_PATH)
    new, resolved = baseline_lib.diff(current, baseline)

    if resolved:
        print(
            f"[G2] note: {len(resolved)} baseline error(s) no longer exist — "
            "consider re-running with --update-baseline to shrink the baseline:"
        )
        for v in resolved:
            print(f"  - {v}")

    if new:
        print(f"[G2] FAIL — {len(new)} NEW mypy error(s) not present in the baseline:", file=sys.stderr)
        for v in new:
            print(f"  - {v}", file=sys.stderr)
        print(
            f"\nBaseline: {BASELINE_PATH.name} ({len(baseline)} pre-existing error(s), unaffected).",
            file=sys.stderr,
        )
        return 1

    print(f"[G2] PASS — {len(current)} total error(s), 0 new vs baseline ({len(baseline)} pre-existing).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
