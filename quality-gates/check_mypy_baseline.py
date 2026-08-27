#!/usr/bin/env python
"""G2 — mypy typecheck, baselined: FAIL only on NEW errors relative to a version-controlled
baseline (quality-gates/mypy-baseline.json). Same pattern as G1/G4.

This tree carries 12 pre-existing mypy errors in 8 files (measured 2026-08-27, non-strict
profile — see pyproject.toml `[tool.mypy]` for why this is NOT strict mode) — not fixed by
this gate, recorded in the baseline for a human to burn down.

SCOPE: `app/` ONLY, not module/scripts/tests. `module/` is a thin legacy compat re-export
shim (see .claude/CLAUDE.md `## Project structure`) whose only content is re-exporting names
from `app.*` — mypy's default `--follow-imports=normal` means checking `module/` also
re-reports every `app/` error a second time under the `module` invocation, which is pure
duplication, not new signal. `scripts/` is currently empty. `tests/` is covered by G3
(pytest itself catches real breakage there); typing test fixtures is not this gate's job.

Identity key = "relative/file.py|CODE|message text", same line-drift-tolerant shape as G1.

FAIL-OPEN FIX (2026-08-27 — cross-repo defect, see
D:/backup/CSIA/@PM/state/runs/CROSS-REPO-mypy-failopen.md): mypy does NOT crash on a broken or
missing `[tool.mypy]` config — it silently falls back to bare defaults and keeps running.
Reproduced HERE, concretely: adding a syntactically-valid-but-unrecognized key under
`[tool.mypy]` (e.g. `not_a_real_mypy_option = true`) made mypy print
`pyproject.toml: [mypy]: Unrecognized option: ...` to STDERR while this script — which only
ever read stdout — kept parsing the (unaffected, in that specific case) findings and reported
a clean PASS, never surfacing the warning at all. A more severe corruption (an actual TOML
syntax error, or deleting pyproject.toml outright) makes mypy fall back to COMPLETE bare
defaults; in THIS repo's config that happens to ADD 9 spurious `import-untyped` findings
(losing `ignore_missing_imports = true`) rather than hide any of the 12 baselined ones, so
those two specific corruptions were already visible as an (accidental, unexplained) FAIL — but
relying on that coincidence is exactly the fragility this fix removes. Two parts, both
required:
  1. `_validate_config()` — a static, tool-independent check (stdlib `tomllib`) that the
     config file exists, parses as TOML, and carries a `[tool.mypy]` table, BEFORE mypy is
     even invoked. Also pass `--config-file` explicitly so mypy raises a hard, visible error
     if the path vanishes between this check and the subprocess call, instead of silently
     re-discovering nothing and using defaults.
  2. `_config_problem_in_stderr()` — mypy prefixes every config-loading diagnostic with the
     config file's own name (`pyproject.toml: ...`); on a clean run stderr is empty (measured
     2026-08-27), so ANY such line is real signal. This is what static TOML validation cannot
     see, because a bad *option value* (as opposed to bad syntax) is valid TOML — only mypy's
     own semantic check catches it, and only reading stderr surfaces that check's result.
  3. Vanished baseline findings now FAIL instead of printing an ignorable note (see `main()`)
     — the durable half: it catches ANY future mechanism that silently disables the profile,
     not just a broken TOML.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import baseline as baseline_lib
from lib.git_diff import ensure_utf8_stdio

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "mypy-baseline.json"
CONFIG_PATH = ROOT / "pyproject.toml"


def _validate_config() -> str | None:
    """Confirm CONFIG_PATH exists, parses as TOML, and carries a `[tool.mypy]` table. Returns
    an error message if not, else None. Does NOT prove every option was honoured — a
    syntactically valid but semantically bad option (e.g. a typo'd key) passes this check and
    is caught instead by `_config_problem_in_stderr()` after mypy actually runs."""
    if not CONFIG_PATH.exists():
        return f"config file not found: {CONFIG_PATH} (mypy would silently fall back to bare defaults)"
    try:
        data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return f"{CONFIG_PATH.name} is not valid TOML: {exc}"
    if not isinstance(data.get("tool", {}).get("mypy"), dict):
        return f"{CONFIG_PATH.name} has no [tool.mypy] table"
    return None


def _run_mypy() -> tuple[list[dict], str, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "app", "--output=json", f"--config-file={CONFIG_PATH}"],
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
    errors = [item for item in items if item.get("severity") == "error"]
    return errors, proc.stderr, proc.returncode


def _identity(item: dict) -> str:
    rel = Path(item["file"]).as_posix()
    return f"{rel}|{item['code']}|{item['message']}"


def _config_problem_in_stderr(stderr: str) -> str | None:
    """mypy prefixes every config-loading diagnostic with the config file's own name, e.g.
    `pyproject.toml: [mypy]: Unrecognized option: not_a_real_mypy_option = True` or
    `pyproject.toml: Cannot declare ('tool', 'mypy') twice`. Measured 2026-08-27: stderr is
    empty on a clean run, so any line naming the config file is real signal, never noise —
    this is what actually closes the fail-open hole `_validate_config()` cannot: a
    syntactically valid but unrecognized/invalid option is valid TOML and passes static
    validation, yet mypy still rejects it (and, depending on the corruption, may silently fall
    back to bare defaults while doing so). Substring match, not startswith: when
    `--config-file` is passed as an ABSOLUTE path (as `_run_mypy()` does), mypy echoes that
    same absolute path verbatim in the diagnostic instead of the bare filename mypy's own
    auto-discovery would have used — caught by testing this exact fix (2026-08-27): an
    earlier `startswith(f"{CONFIG_PATH.name}:")` version missed every hit because the line
    actually started with the full absolute path, not the bare name."""
    marker = f"{CONFIG_PATH.name}:"
    hits = [line for line in stderr.splitlines() if marker in line]
    return "\n".join(hits) if hits else None


def main() -> int:
    update_mode = "--update-baseline" in sys.argv[1:]

    config_error = _validate_config()
    if config_error:
        print(f"[G2] FAIL — mypy config problem: {config_error}", file=sys.stderr)
        return 2

    items, stderr, returncode = _run_mypy()

    config_problem = _config_problem_in_stderr(stderr)
    if config_problem:
        print(
            f"[G2] FAIL — mypy reported a config-parse error loading {CONFIG_PATH.name} "
            "(findings below, if any, may be under- or over-reported as a result — fix the "
            "config and re-run):",
            file=sys.stderr,
        )
        print(config_problem, file=sys.stderr)
        return 2

    if returncode not in (0, 1) and not items:
        print(
            f"[G2] FAIL — mypy exited {returncode} unexpectedly (crash / CLI-usage error) "
            "with no findings — refusing to treat that as '0 errors':",
            file=sys.stderr,
        )
        print(stderr or "(no stderr captured)", file=sys.stderr)
        return 2

    current = sorted({_identity(i) for i in items})

    if update_mode:
        baseline_lib.write(BASELINE_PATH, current)
        print(f"[G2] baseline updated — {len(current)} error(s) recorded at {BASELINE_PATH.name}.")
        return 0

    baseline = baseline_lib.load(BASELINE_PATH)
    new, resolved = baseline_lib.diff(current, baseline)

    if resolved:
        print(f"[G2] FAIL — {len(resolved)} baselined mypy error(s) no longer exist:", file=sys.stderr)
        for v in resolved:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nA vanished baseline finding means either a genuine fix or that the type-check "
            "profile silently stopped applying (the fail-open hole this check exists to "
            "close). If you confirmed this is a deliberate improvement, run "
            "`py -3.11 quality-gates/run.py g2 --update-baseline` to shrink the baseline — "
            "never run it just to make this pass without checking why the finding vanished.",
            file=sys.stderr,
        )
        return 1

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
