---
description: Review sattline-parser changes without editing
agent: parser-reviewer
---

Review `$ARGUMENTS`. If the argument is empty, review the uncommitted changes
and the current branch diff against `main`.

Report findings in severity order, with `file:line` references. Do not edit
files.

Check:

1. Boundary: does the change stay inside language infrastructure, or did it add
   analysis policy, consumer behaviour, or a consumer import?
2. Correctness: strict fallbacks, original-source spans, grammar canonicality,
   AST shape, and comment preservation.
3. Tests: is there a focused test, a corpus fixture, and a golden expectation
   for new syntax or rules?
4. Generated files: was `builtins/catalogue.json`, a build artifact, a coverage
   report, or `uv.lock` edited by hand?
5. Documentation: did the matching `docs/` page and `CHANGELOG.md` change?
6. Quality: Ruff, Pyright strict, Bandit, and coverage gates.
7. Public tree: third-party names, paths, build numbers, or dash punctuation in
   prose.

If something is clean, say so. If a check cannot be run, say what is missing.
