---
description: Prepare a sattline-parser release
---

Prepare release `$ARGUMENTS` for `sattline-parser`. Treat the argument as the
calendar version (`YYYY.M.N`). If it is empty, derive the next version from
`src/sattline_parser/__version__.py` and `CHANGELOG.md`, then propose it before
changing files.

Checklist:

1. Read `AGENTS.md`, `docs/development.md`, and the current `CHANGELOG.md`.
2. Confirm the version is not already released.
3. Update `src/sattline_parser/__version__.py`.
4. Move the `Unreleased` entries in `CHANGELOG.md` under the new version and
   date, and leave a fresh `Unreleased` section.
5. Regenerate `uv.lock` with `uv lock` only if dependencies changed.
6. Run the full verification ladder from `/verify`.
7. Run `python scripts/gen_builtin_catalogue.py --check`.
8. Build the artifacts with `python -m build`.
9. Run `python -m twine check dist/*`.
10. Run `python scripts/smoke_installed.py` against the built artifacts if the
    release workflow does not already cover it.

Do not commit, push, tag, publish, or create a GitHub release without explicit
permission for that specific action. Propose the exact commands, then wait.
