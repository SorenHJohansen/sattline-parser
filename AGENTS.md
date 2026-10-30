# AGENTS.md

> AI control-plane entry for the standalone `sattline-parser` package.

## Quick Reference

**Purpose:** `sattline-parser` owns the SattLine grammar, AST models, and `SLTransformer`. It is a standalone parser core for the SattLine language.
**Boundary:** this package is self-contained and standalone; it must never import from or depend on other tooling packages. It ships standalone on PyPI as an external dependency.
**Communication:** terse and concrete.

## Repo Map

| Path | Role |
| --- | --- |
| `src/sattline_parser/api.py` | Public entry points: `create_parser`, `parse_source_text/file`, `describe_parse_error`, decoding helpers |
| `src/sattline_parser/grammar/` | Lark grammar (`sattline.lark`), `constants.py`, `sattline_lexer.py` |
| `src/sattline_parser/models/` | AST models (`ast_model.py`) |
| `src/sattline_parser/transformer/` | Transformer mixins and `SLTransformer` |
| `src/sattline_parser/fuzz_harness.py` | Standalone fuzz harness |
| `src/sattline_parser/cli/` | Read-only `sattline` command line: one module per subcommand in `cli/cmds/` |
| `src/sattline_parser/project/` | Project layer: discovery, resolution, `.g`/`.y` companions, caches, `SattLineProject` |
| `src/sattline_parser/validation/` | Validator rules, diagnostics, builtin catalogue |
| `src/sattline_parser/source_document.py` | Source provenance: original/normalized text + source map, span remapping |
| `tests/` | Full suite: `tests/parser/`, `tests/project/`, `tests/cli/`, packaging tests |
| `tests/fixtures/corpus/` | Corpus fixtures (`.s` sources only) for regression and fuzz seeding |

## Critical Invariants

- Strict single-source validation stays the default; no silent fallback behavior.
- Keep touched Python files Pyright strict-clean.
- Prefer splitting a file when it makes architectural sense (separate
  responsibility). Do **not** split purely to stay under a line budget or into
  mechanical `_part1`/`_part2` files; a cohesive module may exceed 500 lines.
- Do not add imports back into consumer tooling; keep the layers clean.
- Use the grammar file `src/sattline_parser/grammar/sattline.lark` as canonical.

## Public Tree Rule

This repository is public.

- Describe behavior, never origin: "the syntax accepts `X`" is correct, "the
  reader at `<address>` accepts `X`" is not.
- Keep out code addresses, build or version numbers, library, unit, project and
  person names, and any note about probing, disassembly or how a rule was
  found.
- This applies to comments, docstrings, test names, fixture headers, the
  changelog, commit messages, branch names, PR text and issues.

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

2026-10-30
