---
description: Run the sattline-parser verification ladder
---

Verify the current change in `sattline-parser`. Treat `$ARGUMENTS` as an
optional scope hint (a file, a test path, or a subsystem).

Run these checks in order. Use `.venv/bin/python` when the virtual environment
exists, otherwise use `uv run`.

1. Run the smallest focused test that covers the change.
2. Run `ruff check src tests scripts`.
3. Run `ruff format --check src tests scripts`.
4. Run `pyright src tests`.
5. Run `bandit -q -r src -x tests -c pyproject.toml`.
6. Run `scripts/check_branch_coverage.py`. This runs the full suite and both
   coverage gates.
7. If Markdown changed, run `scripts/check_docs.py`.

Report each command and its result. If a check fails, stop and report the
failure with the exact command and output. Do not fix unrelated failures.
