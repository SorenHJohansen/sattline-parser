# AGENTS.md

> AI control-plane entry for the standalone `sattline-parser` package.

## Quick Reference

**Purpose:** `sattline-parser` owns the SattLine grammar, AST models, and `SLTransformer`. It is the layer-0 parser core extracted from the SattLint repository.
**Boundary:** this package must NEVER import from `sattlint` or `sattlint_lsp`. It ships standalone on PyPI and is consumed by SattLint as an external dependency.
**Communication:** terse and concrete.

## Repo Map

| Path | Role |
| --- | --- |
| `src/sattline_parser/api.py` | Public entry points: `create_parser`, `parse_source_text/file`, `describe_parse_error`, decoding helpers |
| `src/sattline_parser/grammar/` | Lark grammar (`sattline.lark`), `constants.py`, `parser_decode.py` |
| `src/sattline_parser/models/` | AST models (`ast_model.py`) |
| `src/sattline_parser/transformer/` | Transformer mixins and `SLTransformer` |
| `src/sattline_parser/fuzz_harness.py` | Standalone fuzz harness |
| `tests/` | Parser-core tests including moved `tests/parser/` suite |
| `tests/fixtures/corpus/` | Corpus fixtures (`.s` sources only) for regression and fuzz seeding |

## Critical Invariants

- Strict single-source validation stays the default; no silent fallback behavior.
- Keep touched Python files Pyright strict-clean.
- Hard cap of 500 lines per checked-in file.
- Do not add imports back into `sattlint`; keep the layers clean.
- Use the grammar file `src/sattline_parser/grammar/sattline.lark` as canonical.

## Workflow

- Start from the owning file, symbol, or failing command.
- Smallest grounded edit that tests the current hypothesis, then the first focused validation immediately (`pytest tests/parser` or targeted file).
- Widen to Ruff, Pyright, or pre-commit only after the local check passes.

## Last Updated

2026-08-08
