"""Enforce line AND branch coverage gates for the whole test suite.

Coverage's config file cannot express separate line/branch fail gates, so this
script is the authoritative branch gate used by CI. It runs the complete test
suite with branch measurement and asserts:

- line coverage >= 100 (the project's documented guarantee)
- branch coverage >= the configured minimum

Usage: ``python scripts/check_branch_coverage.py``
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

LINE_MIN = 100.0
# Branch coverage is measured as a depth complement to line coverage. The gate
# sits below the current level (93.12%) so it catches regressions without
# demanding coverage of purely-defensive branches.
BRANCH_MIN = 93.0

_REPO_ROOT = Path(__file__).resolve().parents[1]
_JSON_REPORT = _REPO_ROOT / "coverage-branch.json"


def main() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=src",
            "--cov-branch",
            "--cov-fail-under=0",
            f"--cov-report=json:{_JSON_REPORT}",
            "-q",
            "--no-cov-on-fail",
        ],
        cwd=_REPO_ROOT,
    )
    if result.returncode != 0:
        print("branch-coverage run failed (tests errored)", file=sys.stderr)
        return result.returncode

    with _JSON_REPORT.open(encoding="utf-8") as handle:
        totals = json.load(handle)["totals"]

    statements = int(totals["num_statements"])
    covered_lines = int(totals["covered_lines"])
    branches = int(totals["num_branches"])
    covered_branches = int(totals["covered_branches"])

    line_pct = (covered_lines / statements * 100) if statements else 100.0
    branch_pct = (covered_branches / branches * 100) if branches else 100.0

    print(f"line coverage:   {line_pct:.2f}% (min {LINE_MIN:.2f}%)")
    print(f"branch coverage: {branch_pct:.2f}% (min {BRANCH_MIN:.2f}%)")

    failures: list[str] = []
    if line_pct < LINE_MIN:
        failures.append(f"line coverage {line_pct:.2f}% < {LINE_MIN:.2f}%")
    if branch_pct < BRANCH_MIN:
        failures.append(f"branch coverage {branch_pct:.2f}% < {BRANCH_MIN:.2f}%")
    if failures:
        print("coverage gates failed: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("coverage gates OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
