"""Generic version-controlled baseline-diff helper, shared by every gate that needs
"fail only on NEW findings relative to what already existed on this tree" (G1 ruff, G2 mypy,
G4 import-linter).

Ported from learningMachine's api/quality-gates/lib/baseline.py (verified recipe) — `load`/
`write`/`diff` identical in behavior, only the docstring is repo-specific. `report_and_decide`
(below) is new to this repo (2026-08-27 ordering fix, see each checker's "ORDERING FIX"
docstring) and is NOT part of the ported recipe.

A baseline is a JSON array of violation *identity strings* — a stable key built by the caller
from fields that survive line drift (e.g. "relative/file.py|CODE|message text"), deliberately
EXCLUDING the line number so a violation that merely moved a few lines because of an unrelated
edit above it doesn't register as "new". Two violations with the same identity are
indistinguishable and collapse to one baseline entry — acceptable for this recipe's scale (tens
of pre-existing findings, not hundreds).
"""
from __future__ import annotations

import json
import sys
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
    resolved = present in the baseline, absent now (a pre-existing violation that got fixed as
    a side effect — as of the 2026-08-27 ordering fix this ALSO blocks the gate, see
    `report_and_decide` below; it is never silently ignorable).
    """
    baseline_set = set(baseline)
    current_set = set(current)
    new = sorted(v for v in current if v not in baseline_set)
    resolved = sorted(v for v in baseline if v not in current_set)
    return new, resolved


def report_and_decide(
    *,
    gate_tag: str,
    noun: str,
    profile_desc: str,
    current: list[str],
    baseline_path: Path,
    update_mode: bool,
    update_baseline_cmd: str,
    extra_on_fail: str = "",
) -> int:
    """Single decision function shared IDENTICALLY by G1/G2/G4's baselined-finding gates, so
    the three scripts cannot drift back apart on this logic (2026-08-27 ordering fix — see each
    checker's "ORDERING FIX" docstring for the concrete reproduction that made this the shared
    shape). `new`/`resolved` are computed ONCE here and both are always evaluated before any
    return — the ORIGINAL bug evaluated `resolved` alone and returned before `new` was ever
    checked in the plain-run path, AND separately ran `--update-baseline` (writing `current`
    straight to the baseline file) BEFORE the diff against the existing baseline was even
    computed — so `--update-baseline` never saw `new` at all, let alone acted on it. Either
    path meant a commit that simultaneously fixed one baselined finding AND introduced an
    unrelated new one could end up told ONLY about the resolved finding, and the gate's own
    `--update-baseline` remedy then silently baked the unreviewed new finding into the
    baseline, hiding it permanently.

    `--update-baseline` now computes `new`/`resolved` FIRST, always, and REFUSES to write
    (exit 1, zero file change) ONLY when BOTH are non-empty — that is the one state where a
    plain re-snapshot is genuinely ambiguous: the operator asked to shrink the baseline for a
    vanished finding, and a blind re-snapshot would ALSO silently accept the new, unreviewed
    finding as if it were the same kind of reviewed decision. This is a hard refusal rather
    than "print a warning and write anyway" — a printed warning can go unread in a
    non-interactive/CI invocation (a scripted `--update-baseline && git commit`), where a
    refusal cannot be missed.

    A new-only run (deliberately accepting a new finding as debt) or a resolved-only run
    (shrinking for a genuine fix) still PROCEEDS — this is a real, documented, legitimate use
    of --update-baseline (see e.g. check_ruff_baseline.py's module docstring: "a deliberate,
    reviewed cleanup (or knowingly accepting a new one)") — but now prints every finding it is
    about to accept or remove BY NAME, not just a count, so the operator sees exactly what the
    snapshot is about to do.

    gate_tag: e.g. "[G1]". noun: e.g. "ruff violation" / "mypy error" / "import violation" (an
    "(s)" is appended by the caller-facing messages below). profile_desc: e.g. "lint profile" /
    "type-check profile" / "layers contract", used in the vanished-only message.
    update_baseline_cmd: the exact command to suggest, e.g.
    "py -3.11 quality-gates/run.py g1 --update-baseline". extra_on_fail: appended verbatim to
    stderr on a normal-run FAIL only (e.g. G4's full import-linter output) — never printed on
    PASS or on the --update-baseline refusal.
    """
    baseline = load(baseline_path)
    new, resolved = diff(current, baseline)

    if update_mode:
        if new and resolved:
            print(
                f"{gate_tag} FAIL — refusing --update-baseline: {len(new)} NEW {noun}(s) AND "
                f"{len(resolved)} vanished baseline entry/entries are BOTH present in this run "
                "— a plain re-snapshot here would ALSO silently accept the NEW finding(s) as "
                "if they were reviewed debt. No baseline file was written.",
                file=sys.stderr,
            )
            for v in new:
                print(f"  - NEW: {v}", file=sys.stderr)
            for v in resolved:
                print(f"  - VANISHED: {v}", file=sys.stderr)
            print(
                "\nAccepting a new finding as debt and shrinking the baseline for a vanished "
                "one are two different decisions — this gate refuses to make both at once "
                "silently. Fix the NEW finding(s) first (then re-run --update-baseline to "
                "shrink for the vanished entries only), or handle them in separate runs once "
                "only one side is present.",
                file=sys.stderr,
            )
            return 1
        if new:
            print(f"{gate_tag} accepting {len(new)} NEW {noun}(s) into the baseline as reviewed debt:")
            for v in new:
                print(f"  - {v}")
        if resolved:
            print(f"{gate_tag} shrinking baseline — {len(resolved)} vanished {noun}(s) removed:")
            for v in resolved:
                print(f"  - {v}")
        write(baseline_path, current)
        print(f"{gate_tag} baseline updated — {len(current)} {noun}(s) recorded at {baseline_path.name}.")
        return 0

    if new or resolved:
        if new:
            print(f"{gate_tag} FAIL — {len(new)} NEW {noun}(s) not present in the baseline:", file=sys.stderr)
            for v in new:
                print(f"  - {v}", file=sys.stderr)
        if resolved:
            print(f"{gate_tag} FAIL — {len(resolved)} baselined {noun}(s) no longer exist:", file=sys.stderr)
            for v in resolved:
                print(f"  - {v}", file=sys.stderr)
        if new and resolved:
            print(
                f"\nBoth NEW {noun}s and vanished baseline entries were found in this run. "
                f"`--update-baseline` REFUSES while both are present — it will not silently "
                f"accept the NEW {noun}(s) as part of a baseline shrink. Deal with the NEW "
                f"{noun}(s) first (fix them, or re-run once only they remain to explicitly "
                "accept them as debt via --update-baseline), then re-run --update-baseline "
                "separately to shrink the baseline for the vanished entries.",
                file=sys.stderr,
            )
        elif resolved:
            print(
                f"\nA vanished baseline {noun} means either a genuine fix or that the "
                f"{profile_desc} silently stopped applying (the fail-open hole this check "
                "exists to close). If you confirmed this is a deliberate improvement, run "
                f"`{update_baseline_cmd}` to shrink the baseline — never run it just to make "
                "this pass without checking why the finding vanished.",
                file=sys.stderr,
            )
        else:
            print(
                f"\nBaseline: {baseline_path.name} ({len(baseline)} pre-existing {noun}(s), "
                "unaffected).",
                file=sys.stderr,
            )
        if extra_on_fail:
            print(extra_on_fail, file=sys.stderr)
        return 1

    print(f"{gate_tag} PASS — {len(current)} total {noun}(s), 0 new vs baseline ({len(baseline)} pre-existing).")
    return 0
