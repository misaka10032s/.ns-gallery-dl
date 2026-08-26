#!/usr/bin/env python
"""G5 — diff coverage >= threshold (60% default, changed lines only).

Thin wrapper around `diff-cover` (reads Cobertura XML). Ported from learningMachine's
diff_coverage.py (verified recipe) unchanged except the docstring and the coverage.xml
producer command in quality-gates/run.py (`--cov=app` here vs `--cov=app` there too, matches).

Must run AFTER `pytest --cov=app --cov-report=xml` (see quality-gates/run.py's g5 command) —
reads coverage.xml, does not generate it. Testpaths are already pinned to tests/ only via
pyproject.toml's `[tool.pytest.ini_options]`, so the underlying coverage run inherits the same
gitignored-scratch-dir immunity as G3.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.git_diff import ensure_utf8_stdio, resolve_base_ref

ensure_utf8_stdio()

ROOT = Path(__file__).resolve().parent.parent
COVERAGE_XML = ROOT / "coverage.xml"
THRESHOLD = os.environ.get("QUALITY_DIFF_COVERAGE_THRESHOLD", "60")


def main() -> int:
    base_ref = resolve_base_ref(ROOT)

    if not COVERAGE_XML.exists():
        print(
            f"[G5] FAIL — {COVERAGE_XML} not found. Run "
            f'"pytest --cov=app --cov-report=xml" first (quality-gates/run.py g5 does this for you).',
            file=sys.stderr,
        )
        return 1

    diff_cover = shutil.which("diff-cover")
    if diff_cover is None:
        print("[G5] FAIL — diff-cover not installed.", file=sys.stderr)
        return 1

    cmd = [
        diff_cover,
        str(COVERAGE_XML),
        f"--compare-branch={base_ref}",
        f"--fail-under={THRESHOLD}",
        "--include-untracked",
        "--show-uncovered",
    ]
    print(f"[G5] $ {' '.join(cmd)} (cwd={ROOT})")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\n[G5] FAIL — diff coverage below {THRESHOLD}% vs {base_ref}.", file=sys.stderr)
        return result.returncode
    print(f"\n[G5] PASS — diff coverage >= {THRESHOLD}% vs {base_ref}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
