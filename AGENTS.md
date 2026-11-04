# AGENTS.md

> AI control-plane entry for the standalone `sattline-parser` package.

## Quick Reference

**Purpose:** `sattline-parser` owns the SattLine grammar, AST models, and `SLTransformer`. It is a standalone parser core for the SattLine language.
**Scope:** language infrastructure only. It owns grammar and tokenization, compressed-source preprocessing and provenance, AST models and transformation, syntax diagnostics, graphics companion parsing, project discovery, draft/official resolution, dependency resolution and loading, language-level structural validation, and generic parser/project introspection. It does **not** own analysis policy, lint rules, metrics, refactoring, code generation, graphics correlation, rendering, or consumer-specific behaviour.
**Boundary:** this package is self-contained and standalone; it must never import from or depend on other tooling packages. It ships standalone on PyPI as an external dependency.
**Documentation:** `docs/README.md` is the index. Read it before changing an unfamiliar subsystem.
**Communication:** terse and concrete.

## Repo Map

| Path | Role |
| --- | --- |
| `docs/README.md` | Documentation index and responsibility boundary |
| `docs/architecture.md` | Layers, module map, import rules, request flow |
| `docs/parse-pipeline.md` | Bytes to `BasePicture`, failure taxonomy |
| `docs/grammar.md` | Grammar template, lexer, comments, name folding |
| `docs/source-provenance.md` | `SourceDocument`, coded streams, marker decoding |
| `docs/ast.md` | AST model hierarchy and invariants |
| `docs/transformer.md` | Transformer mixins and construction |
| `docs/validation.md` | Strict single-source rules and diagnostic codes |
| `docs/project.md` | Discovery, formats, loading, caches, reachability |
| `docs/graphics.md` | `.g` / `.y` companion parsing |
| `docs/cli.md` | Commands, exit codes, findings, JSON schemas |
| `docs/builtins.md` | Builtin catalogue and record field tables |
| `docs/api.md` | Public import surface and stability boundary |
| `docs/testing.md` | Suites, coverage, fuzzing, CI |
| `docs/development.md` | Setup, workflow, conventions, release |
| `docs/glossary.md` | Terms and file-extension table |
| `.opencode/skills/sattline-parser/SKILL.md` | Repo-local skill: map, invariants, recipes, verification |
| `.opencode/commands/` | Repo-local commands: `verify`, `release`, `review` |
| `.opencode/agents/parser-reviewer.md` | Read-only review subagent |
| `.github/pull_request_template.md` | PR checklist for boundary, tests, docs, generated files |
| `scripts/check_docs.py` | Link, prose, and Mermaid checks for the docs set |
| `.github/workflows/docs.yml` | Docs CI: links, prose, and Mermaid rendering |
| `src/sattline_parser/api.py` | Public façade: re-exports the parse pipeline from `source_io` and `validate_basepicture` |
| `src/sattline_parser/ast.py` | Supported AST surface: every node, clause, tail, `SourceSpan`, and the walker |
| `src/sattline_parser/source_io.py` | Parser cache, source decoding, and the source→`BasePicture` pipeline |
| `src/sattline_parser/names.py` | Identifier identity: the CP1252 fold table used by every layer |
| `src/sattline_parser/grammar/` | Lark grammar (`sattline.lark`), `constants.py`, `sattline_lexer.py` |
| `src/sattline_parser/models/` | AST models (`ast_model.py`) |
| `src/sattline_parser/transformer/` | Transformer mixins and `SLTransformer` |
| `src/sattline_parser/fuzz_harness.py` | Standalone fuzz harness |
| `src/sattline_parser/cli/` | Read-only `sattline` command line: one module per subcommand in `cli/cmds/` |
| `src/sattline_parser/project/` | Project layer: discovery, resolution, `.g`/`.y` companions, per-program validation, provenance, caches, `SattLineProject` |
| `src/sattline_parser/builtins/` | Builtin function signatures and record field specs (generated catalogue) |
| `src/sattline_parser/validation/` | Validator rules, diagnostics, type graph, builtin call checks |
| `src/sattline_parser/source_document.py` | Source provenance: original/normalized text + source map, span remapping |
| `tests/` | Full suite: `tests/parser/`, `tests/project/`, `tests/cli/`, `tests/builtins/`, packaging tests |
| `benchmarks/` | pytest-benchmark timings for parse, validation, and traversal |
| `tests/fixtures/corpus/` | Corpus fixtures (`.s` sources only) for regression and fuzz seeding |
| `tests/fixtures/validation/` | Golden validation manifest and documented behavior differences |

## Critical Invariants

- Strict single-source validation stays the default; no silent fallback behavior.
- Keep touched Python files Pyright strict-clean.
- Prefer splitting a file when it makes architectural sense (separate
  responsibility). Do **not** split purely to stay under a line budget or into
  mechanical `_part1`/`_part2` files; a cohesive module may exceed 500 lines.
- Do not add imports back into consumer tooling; keep the layers clean.
- Use the grammar file `src/sattline_parser/grammar/sattline.lark` as canonical.
- Update `docs/` in the same change as the behavior it describes. A diagram that
  no longer matches the import graph is a defect.
- Keep the responsibility boundary explicit: this package is language
  infrastructure, not analysis. A new analysis feature belongs in a consumer.
- No deprecation windows and no compatibility shims. A superseded field, alias,
  or name is removed in the same breaking release that replaces it. Do not add
  `metadata={"deprecated": ...}`, an alias kept for old callers, or a fallback
  reader for an earlier cache shape.
- Cache formats are versioned. Bump the cache version and discard older entries;
  never decode an older payload into the current model.

## Documentation Rules

- `docs/README.md` is the index and the responsibility statement. Start there.
- Each document owns one subject and links to the others instead of duplicating
  a fact.
- Use tables for anything a future agent will look up: modules, flags, exit
  codes, rules, fields, extensions.
- Use Mermaid for graphs that actually exist in the code: layers, pipelines,
  load order, lexer states. Keep them in sync with the import graph.
- Record behavior, not origin. Keep the public tree free of third-party names,
  paths, and build numbers.

## AI Workspace Tooling

- Load the `sattline-parser` skill before an unfamiliar subsystem. It holds the
  map, recipes, and verification ladder.
- Use `/verify` for the full check ladder, `/review` for a read-only review, and
  `/release` for the release checklist.
- `parser-reviewer` is a read-only subagent. It reports findings, it does not
  edit files.
- Major work gets one `parser-reviewer` pass, not a review loop. Treat a
  multi-file change, a new public API, or a behavior change as major. Apply the
  findings, re-run the verification ladder, and stop; request a second review
  only when the user asks for one.
- The pull request template is the smallest checklist a change must satisfy.
- `scripts/check_docs.py` checks relative links and dash punctuation, and
  extracts Mermaid blocks for rendering. The Docs workflow renders every block.

## Public Tree Rule

This repository is public. Describe behavior, not origin.

- Say what the syntax or tool does ("the syntax accepts `X`"), never where it
  was learned. Keep out code addresses, third-party build numbers, and the
  names of customer libraries, projects or people.
- Back every new rule or data table with something reproducible: a fixture, a
  public manual, or a black-box check against the real tool. Never add data
  extracted from third-party binaries.
- This project is unofficial. Use "SattLine" only to name the file format; do
  not imply affiliation with ABB.

## Workflow

- Start from the owning file, symbol, or failing command.
- Smallest grounded edit that tests the current hypothesis, then the first focused validation immediately (`pytest tests/parser` or targeted file).
- Widen to Ruff, Pyright, or pre-commit only after the local check passes.
- Never commit directly to `main`. Always work on a feature branch and land
  changes through a pull request; `main` only ever receives merges.
- Never commit, push, tag, merge, open a PR or delete a branch without explicit
  permission for that specific action. Propose the command, then wait. Reading
  files, running tests and inspecting git state need no permission.

## Last Updated

2026-11-04
