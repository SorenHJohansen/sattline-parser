## Summary

Describe what changed and why.

## Boundary check

- [ ] This change stays inside language infrastructure (parsing, AST,
      transformation, provenance, validation, discovery, loading, graphics
      parsing, CLI introspection).
- [ ] No analysis policy, lint rule, metric, refactoring, code generation,
      graphics correlation, rendering, or consumer behaviour was added.
- [ ] No consumer tool is imported.

## Verification

- [ ] Focused test for the changed subsystem
- [ ] `ruff check src tests scripts benchmarks`
- [ ] `ruff format --check src tests scripts benchmarks`
- [ ] `pyright src tests benchmarks`
- [ ] `bandit -q -r src -x tests -c pyproject.toml`
- [ ] `python scripts/check_branch_coverage.py`
- [ ] `python scripts/check_docs.py` when Markdown changed

## Tests and fixtures

- [ ] New syntax has a corpus fixture under `tests/fixtures/corpus/`.
- [ ] New validation rules have a fixture and an expectation in
      `tests/fixtures/validation/expectations.json`.
- [ ] New CLI behaviour has a CLI test.
- [ ] New builtin data comes from `scripts/builtin_catalogue_source.json`, not a
      hand edit of `builtins/catalogue.json`.

## Documentation

- [ ] The matching `docs/` page is updated.
- [ ] `CHANGELOG.md` has an entry.
- [ ] No dash punctuation was added to prose.
- [ ] No third-party names, paths, or build numbers were added.

## Generated files

- [ ] No build output, coverage report, or `uv.lock` was edited by hand.
- [ ] The builtin catalogue was regenerated with the script when it changed.
