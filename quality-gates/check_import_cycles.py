#!/usr/bin/env python
"""G4 — "no NEW import-linter contract violation relative to a version-controlled baseline."

Tool: import-linter (`[tool.importlinter]` in pyproject.toml — a `layers` contract). Ported
from learningMachine's check_import_cycles.py (verified recipe) unchanged except the docstring.

Unlike learningMachine's from-scratch clean layering, this repo's `app.providers` and
`app.services` genuinely import each other (see pyproject.toml's `[tool.importlinter]` comment
for the concrete edges) — so this repo's baseline is NOT empty at adoption time, unlike the
exemplar's. That is exactly the scenario this baselined design exists for: "a Python family
member that already has violations when this recipe is copied in can still adopt the gate."

This does NOT clean up pre-existing violations — it only blocks NEW ones relative to
`import-cycle-baseline.json`.

VACUOUS-GATE FINDING (2026-08-27, found during this gate's own proof-of-failure pass — same
failure class as the cluster's documented `vue-tsc --noEmit` case): before this gate could see
anything, it silently PASSED with "0 total violation(s)" on every run, always — because
`app/api`, `app/config`, `app/domain`, `app/providers`, `app/services`, `app/storage` (and
`app/providers/*`) had NO `__init__.py` (PEP 420 implicit namespace packages). grimp 3.15
(import-linter's analysis engine) only descends into a subpackage that HAS `__init__.py`; the
raw import-linter CLI output for the un-fixed tree was literally
`Missing layer 'app.api': module app.api does not exist.` — an ERROR, not "0 violations" — but
this script's `_parse_violations` only looks for a "not allowed to import" header, so it read
that error text, found no match, and reported a clean PASS. Fixed by adding empty
`__init__.py` to all 11 subpackages that were missing one (zero behavior change — nothing in
this codebase relies on namespace-package semantics, verified via
`grep -rn "pkgutil|__path__|iter_modules" app` = 0 hits; `python -c "import app.main"` and the
full pytest suite both still pass after the addition). Do not remove those `__init__.py`
files — doing so silently reintroduces this exact vacuous-PASS bug.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.git_diff import ensure_utf8_stdio

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "import-cycle-baseline.json"

_HEADER_RE = re.compile(r"^\S+ is not allowed to import \S+:$")
_EDGE_RE = re.compile(r"^- (\S+ -> \S+)")


def _run_lint_imports() -> str:
    # Invoked via `sys.executable -c ...` (not the `lint-imports` console script) so this
    # works regardless of whether the Scripts/bin dir is on PATH — the only requirement is
    # the same interpreter this gate script itself is running under.
    code = (
        "import sys; from importlinter.cli import lint_imports; "
        "sys.exit(lint_imports(config_filename='pyproject.toml', no_cache=True))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    output = proc.stdout + proc.stderr
    # Guard against the exact vacuous-PASS class documented in this module's docstring: a
    # "Missing layer '<x>': module <x> does not exist" is a CONFIGURATION/DISCOVERY error, not
    # "0 violations" — it must never be allowed to fall through _parse_violations() and read as
    # a clean run. Fail loud instead.
    if "does not exist" in output and "Missing layer" in output:
        print(f"[G4] FAIL — import-linter could not resolve a configured layer (contract misconfigured or a package lost its __init__.py):\n{output}", file=sys.stderr)
        sys.exit(1)
    return output


def _parse_violations(output: str) -> list[str]:
    violations: list[str] = []
    in_violation_block = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if _HEADER_RE.match(line):
            in_violation_block = True
            continue
        m = _EDGE_RE.match(line)
        if m and in_violation_block:
            violations.append(m.group(1))
    return sorted(set(violations))


def _load_baseline() -> list[str]:
    if not BASELINE_PATH.exists():
        return []
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def main() -> int:
    update_mode = "--update-baseline" in sys.argv[1:]
    output = _run_lint_imports()
    current = _parse_violations(output)

    if update_mode:
        BASELINE_PATH.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"[G4] baseline updated — {len(current)} violation(s) recorded at {BASELINE_PATH.name}.")
        return 0

    baseline = _load_baseline()
    new = [v for v in current if v not in baseline]
    resolved = [v for v in baseline if v not in current]

    if resolved:
        print(f"[G4] note: {len(resolved)} baseline violation(s) no longer exist — consider re-running with --update-baseline to shrink the baseline:")
        for v in resolved:
            print(f"  - {v}")

    if new:
        print(f"[G4] FAIL — {len(new)} NEW import violation(s) not present in the baseline:", file=sys.stderr)
        for v in new:
            print(f"  - {v}", file=sys.stderr)
        print(f"\nBaseline: {BASELINE_PATH.name} ({len(baseline)} pre-existing violation(s), unaffected).", file=sys.stderr)
        print(f"\nFull import-linter output:\n{output}", file=sys.stderr)
        return 1

    print(f"[G4] PASS — {len(current)} total violation(s), 0 new vs baseline ({len(baseline)} pre-existing).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
