# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Source provenance architecture** (`sattline_parser.source_document`):
  - `SourceSpan` is now a real span: `start`/`end` character offsets plus
    `line`/`column`, always referring to the *original* source.
  - `SourceDocument` carries the original text, the normalized/decoded text,
    and a per-character map back to the original source.
  - AST spans and `describe_parse_error` locations map through the source map,
    including for compressed input; `parse_source_text` and `parse_source_file`
    share the same provenance semantics.
- **Lexically aware compressed-source decoding**: string literals and
  `(* ... *)` comments are protected before any transformation, so
  syntax-looking text inside them is never rewritten.
- `PreprocessError` for unknown compressed markers — never silently converted
  to whitespace.
- `preprocess_source()` returning a `SourceDocument` with original-source
  provenance.
- **Fuzz hardening**: hard subprocess timeouts (worker killed on timeout and
  reused across inputs), and strict classification of expected invalid-input
  errors (`UnexpectedInput`, `PreprocessError`) vs. internal bugs — an internal
  `ValueError`/`TypeError` is now a fuzz failure, not ordinary invalid input.
- **No silent data loss** in the transformer: unexpected `modulecode`,
  `equationblock`, `code_blocks`, `seqalternative`/`seqparallel` structures
  raise; interactor types, flag names, procedure names, ModuleDef options
  (`Zoomable`, `ZoomLimits`, `Grid`, `Two_Layers_`), and ComButProc assignment
  lines are preserved instead of silently dropped.
- Per-parse comment depth in the custom lexer (concurrent parses of
  nested-comment sources can no longer interfere).
- CI now enforces the project's quality claims: Ruff lint + format, Pyright
  strict, full test suite, 100% line coverage plus a branch-coverage gate,
  Bandit, pip-audit, wheel/sdist build + install + smoke, deterministic corpus
  regression, a Lark compatibility job, and a Windows compatibility job.
- Release workflow enforces a git-tag == package-version consistency check and
  re-runs the critical validation before publishing.
- `tests/test_packaging.py` outside `tests/parser` verifies installed-package
  behavior (imports, grammar resources, parse, transform, public API).

### Changed

- `SourceSpan` semantics changed from a (line, column) position to a real
  span; consumers reading `span.line`/`span.column` still work, and
  `span.start`/`span.end` are new.
- `describe_parse_error` accepts an optional `source_document` to map error
  locations back to the original source.
- `parse_source_file` reads the raw file and hands the original text to
  `parse_source_text`, so compression/provenance happen exactly once and
  consistently.
- Fuzz harness no longer uses `ThreadPoolExecutor`; timeouts are real.
- **Single authoritative grammar**: `sattline.lark` is the only grammar; the
  generated comment-free "strict" grammar and all `text.replace()`-based
  grammar manipulation are removed. Comments remain explicit grammar elements
  at the exact syntactic positions SattLine defines and are preserved as
  `CodeComment` nodes, and are still rejected inside expressions.
- The `strict` parameter is removed from `build_lark_parser`, `create_parser`,
  and `create_sl_parser`: there is one authoritative parser that accepts
  comments exactly where the grammar permits them.
- Source-map boundary semantics: `SourceDocument.map_position` maps offsets at
  or past the end of the normalized text to the original end-of-input boundary
  (a valid half-open `end`), never to the position of the final character;
  `map_range` maps empty ranges to zero-width original ranges.
- Coverage measurement now includes branch coverage (`scripts/check_branch_coverage.py`),
  gated at 93% while line coverage stays gated at 100%.

## [2026.8.1] - 2026-08-16

### Added

- Source spans (`SourceSpan` with start/end character offsets) on every typed
  expression and statement AST node and on `ParameterMapping`, set
  deterministically by the transformer from Lark `meta`.
- Repo-wide Pyright strict-clean status: zero errors and zero warnings.

### Changed

- Transformer expression/statement methods now receive `meta` from Lark and
  pass the resulting span through to the AST.
- `moduletype_par_transfer` raises on unexpected sources instead of coercing.
- `ModuleCode.__str__` renders through `render_module_code`.

### Removed

- All legacy fallback forms from the parser core:
  - dict-based variable references and `ParameterMapping.__post_init__` target
    coercion (`_normalize_variable_ref`, `_variable_ref_name`),
  - legacy tuple/dict/`Tree` statement handling in the formatter
    (`_statement_children`, `_var_name`, `_object_list`, `_object_list_or_none`,
    `_statement_branches`, `_ternary_branches`, `_comparison_pairs`),
  - `_unwrap_statement_node` and the `statement_key` rendering plumbing,
  - the legacy `Tree(KEY_STATEMENT)` branch in equation blocks.

## [2026.8] - 2026-08-12

### Added

- Typed expression/statement AST nodes (`VarRef`, `BoolOp`, `NotOp`, `Compare`,
  `BinOp`, `UnaryOp`, `FuncCall`, `TernaryOp`, `Assignment`, `FuncCallStmt`,
  `IfStmt`) and `ParameterMapping` with `VarRef` target/source.
- NNELib-style comment grammar (`change_description`, `module_typedescription`)
  and the `comment_stmt` rule for null statements in code blocks.
- CalVer versioning (`YEAR.MONTH`).

### Changed

- `variable_name` transformer returns `VarRef` instead of a dict; statements are
  returned directly without the `Tree(KEY_STATEMENT)` wrapper.
- `Equation`/`Sequence`/`SFCCodeBlocks` code lists are typed with
  `CodeItem`/`SFCBodyItem`.

### Removed

- Legacy `comments_with_opt_semi` and `code_comments_with_opt_semi` grammar
  rules.

## [0.1.0] - 2026-08-08

### Added in 0.1.0

- Initial standalone release of the SattLine parser core:
  - Lark grammar for SattLine `.s`/`.g`/`.l` sources.
  - AST models (`sattline_parser.models`).
  - `SLTransformer` tree transformer (`sattline_parser.transformer`).
  - Strict single-source parsing entry points (`sattline_parser.api`).
  - Compressed-source decoding helpers.
  - Standalone fuzz harness with corpus regression.
