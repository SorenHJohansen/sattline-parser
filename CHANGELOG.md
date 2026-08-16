# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
