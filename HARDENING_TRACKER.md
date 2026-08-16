# sattline-parser Hardening Pass — Tracking

> Comprehensive hardening pass closing the gap between documented/claimed guarantees
> and what the implementation and CI actually guarantee.

Legend: `[ ]` pending · `[~]` in progress · `[x]` done · `[x]` (verified) done + verified

---

## Priority 1 — Source Provenance / Source Spans
- [x] Audit preprocessor transformations for full source-map coverage
- [x] Introduce `SourceDocument`/provenance abstraction (original + normalized + source map)
- [x] Source map maps normalized ranges back to original source for ALL transforms
- [x] Generated text gets explicit (non-misleading) provenance semantics
- [x] Replace `SourceSpan(line, column)` with real `SourceSpan(start, end)` (char offsets + line/col)
- [x] AST spans refer to ORIGINAL source coordinates
- [x] Parser diagnostics map back to original source for compressed input
- [x] `parse_source_text()` / `parse_source_file()` consistent provenance semantics
- [x] End-to-end tests: original -> preprocess -> parse -> AST span -> slice original source
- [x] Tests: normal/compressed/substituted/inserted/deleted/comments/multiline/errors

## Priority 2 — Preprocessor Correctness
- [x] Audit every regex transform for opaque-region (string/comment/quoted-id) damage
- [x] Make preprocessing lexically aware or protect opaque regions
- [x] Regression tests: syntax-looking text inside strings/comments not transformed
- [x] Unknown compressed markers never silently become spaces (raise `PreprocessError`)
- [~] Update tests/docs for the chosen unknown-marker behavior (tests done; docs pending)

## Priority 3 — Fuzzing Correctness
- [x] Real hard timeout (subprocess, not ThreadPoolExecutor-with-context-wait)
- [x] Atheris parser target lets unexpected exceptions escape
- [x] Distinguish expected parse errors from internal bugs (no broad ValueError/SyntaxError)
- [x] Keep random/human harness separate from Atheris target
- [x] Reuse executor/process across inputs (high throughput)
- [x] Regression tests: timeout, unexpected internal exception, expected syntax error, propagation, no swallowing

## Priority 4 — CI Enforces Quality
- [x] CI runs: Ruff lint, Ruff format, Pyright, pytest, coverage, Bandit, pip-audit, build validation
- [x] Tools actually executed (not merely installed)
- [x] Explain + schedule any tool not suitable for every PR

## Priority 5 — Full Test Suite in CI
- [x] CI runs the complete configured test suite (not just `tests/parser`)
- [x] Coverage covers the entire suite
- [x] Regression test ensuring non-`tests/parser` tests are executed (`tests/test_packaging.py`)

## Priority 6 — Coverage Quality
- [x] Evaluate branch coverage; enable where practical
- [x] Targeted semantic tests: provenance, decoding, diagnostics, comments, transformer, packaging
- [x] Keep 100% line coverage requirement
- [x] Branch coverage measured + gated (93%) via `scripts/check_branch_coverage.py`

## Priority 7 — Fuzz Corpus in CI
- [x] Deterministic corpus regression runs in normal CI
- [x] Random fuzz smoke kept separate
- [x] CI/docs distinguish deterministic regression vs PR smoke vs long-running ClusterFuzzLite

## Priority 8 — Real Packaging Tests
- [x] Build wheel + sdist
- [x] Install each into clean env
- [x] Smoke/integration test against installed package (imports, grammar resources, parse, transform, API)
- [x] Build/package validation in normal CI (not only publishing)

## Priority 9 — Release Cannot Bypass CI
- [x] Release requires same critical checks (tests, typing, lint, build, install, smoke)
- [x] Tag/version consistency check (tag vX.Y.Z == package version)
- [x] Test wheel and sdist

## Priority 10 — Lock File / Reproducibility
- [x] Explicit dependency strategy: locked CI + compatibility job
- [x] CI uses uv.lock (`uv sync --frozen --all-extras`)

## Priority 11 — Lark Compatibility
- [x] Audit all Lark internal API usage
- [x] Narrow dependency range or add compatibility matrix
- [x] Test min + latest supported Lark (both 1.3.1 today; unlocked compat job + version-range guard test)

## Priority 12 — No Silent Data Drop
- [x] Audit if/elif chains for silent ignores
- [x] Raise/classify unexpected structures at semantic boundaries
- [x] Regression tests: unexpected structures cannot silently disappear
- [x] Fix graphics/interact data-loss bugs (types, flags, procedure names, tail dedup, moduledef opts, two_layers, combutproc assignments)

## Priority 13 — Transformer Intermediate Representation
- [x] Audit weak IR (object/Any/dicts/Trees/Tokens/AST)
- [x] Introduce typed internal models/protocols where materially improves safety (comments span, combutproc classification, `_CoordOwner` protocol, typed branch collection)
- [x] Reduce `Any`, make structural invariants explicit, unexpected nodes fail loudly

## Priority 14 — Strict Grammar Generation
- [x] Audit textual `.replace()` grammar derivation
- [x] Prefer structured generation; preserve behavior; add tests first
- [x] Added validation that comment rules cannot leak into the strict grammar + regression tests

## Priority 15 — Docs Match Implementation
- [x] README / CHANGELOG / docstrings / metadata audited
- [x] SourceSpan docs (start/end) vs impl fixed
- [x] Preprocessing mapping docs vs impl fixed
- [x] Strict/no-silent-fallback docs vs unknown-marker behavior fixed
- [x] parse_source_file/text equivalence docs fixed
- [x] Prefer fixing implementation over weakening docs

## Priority 16 — Parser Cache / Concurrency
- [x] Audit caching + custom lexer comment depth
- [x] Comment depth per-parse (not global mutable state)
- [x] Concurrency regression test (parallel nested-comment parses)

## Priority 17 — Parse Tree / AST Lifecycle
- [x] Audit `BasePicture.parse_tree` pickling behavior; document intent
- [x] Consider separating parse-result state from persistent AST state (documented; parse_tree is tooling state, stripped on pickle)

## Priority 18 — Platform Coverage
- [x] Decide OS-independence claim
- [x] Add lightweight Windows (and macOS if warranted) compatibility jobs

## Priority 19 — Parser Cache Robustness
- [x] Cache keys cover all compatibility dimensions (incl. Python version)
- [x] Corrupted/stale cache cannot cause incorrect behavior (Lark falls back; regression-tested)
- [x] Cache invalidation/regression test

## Priority 20 — Formatter Type Hacks
- [x] Audit `type(value).__name__ == "Variable"` style checks
- [x] Replace with imports/protocols/adapters (no circular imports — lazy import used)

---

## Cross-cutting

### Quality / Verification
- [x] Baseline: `pytest tests/parser` = 148 passed, 100% line coverage
- [x] Baseline: `ruff check`, `ruff format --check`, `pyright` all clean
- [x] Baseline: `bandit -r src` runs (B404/B603 skipped)
- [ ] Full `pytest` (entire suite) green
- [ ] `ruff check src tests` + `ruff format --check` green
- [ ] `pyright src tests` green (strict)
- [ ] `bandit` clean
- [ ] `pip-audit` clean
- [ ] Coverage 100% line + branch (where enabled)
- [ ] pre-commit run --all-files green

### Final review
- [ ] Adversarial review: guarantee -> code -> test -> CI gate for every claim
- [ ] Summary of changes, remaining issues, CI jobs, tests added, API changes, commands run

---

## Notes / Findings
(append as discovered)
