"""Generic version-controlled baseline-diff helper, shared by every gate that needs
"fail only on NEW findings relative to what already existed on this tree" (G1 ruff, G2 mypy).

Ported from learningMachine's api/quality-gates/lib/baseline.py (verified recipe) — identical
in behavior, only the docstring is repo-specific.

A baseline is a JSON array of violation *identity strings* — a stable key built by the caller
from fields that survive line drift (e.g. "relative/file.py|CODE|message text"), deliberately
EXCLUDING the line number so a violation that merely moved a few lines because of an unrelated
edit above it doesn't register as "new". Two violations with the same identity are
indistinguishable and collapse to one baseline entry — acceptable for this recipe's scale (tens
of pre-existing findings, not hundreds).
"""
from __future__ import annotations

import json
from pathlib import Path


def load(path: Path) -> list[str]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, violations: list[str]) -> None:
    path.write_text(json.dumps(sorted(set(violations)), indent=2) + "\n", encoding="utf-8")


def diff(current: list[str], baseline: list[str]) -> tuple[list[str], list[str]]:
    """Returns (new_violations, resolved_violations), both sorted.

    new = present now, absent from the baseline (blocks the gate).
    resolved = present in the baseline, absent now (informational only — a pre-existing
    violation that got fixed as a side effect; never blocks, just suggests shrinking the
    baseline via --update-baseline).
    """
    baseline_set = set(baseline)
    current_set = set(current)
    new = sorted(v for v in current if v not in baseline_set)
    resolved = sorted(v for v in baseline if v not in current_set)
    return new, resolved
