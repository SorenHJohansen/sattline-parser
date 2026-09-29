# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Source files are now decoded strictly as Windows-1252 (cp1252)** — the only
  encoding the real SattLine parser accepts. `read_text_with_fallback` (which
  tried utf-8, then cp1252, then latin-1) is replaced by `read_text_cp1252`,
  which has **no encoding fallback**: bytes that are not valid Windows-1252
  (`0x81 0x8D 0x8F 0x90 0x9D`) now raise `UnicodeDecodeError` instead of being
  silently re-read as latin-1. This removes a silent-fallback path that could
  decode a mis-encoded file into plausible but wrong text. (Breaking rename of
  the public `read_text_with_fallback` export; behavior of `load_source_text`,
  `parse_source_file`, and the project loader is otherwise unchanged.)

### Added

- Validation rule **SL-V027 `PARAM_TRANSFER_TYPE_MISMATCH`**: a module-type
  instance whose parameter transfer supplies an incompatible variable type is
  now flagged (real-parser confirmed: `Submodule Child, parameter EnableFlag:
  Variable CounterValue is an invalid type`). Implemented in
  `sattline_parser.validation.transfers`; GLOBAL/literal sources, undeclared
  sources, unknown target parameters, `AnyType` formals, numeric widening
  (integer↔real), and record-typed transfers are handled.

### Documentation

- README: new "Project layer" usage section covering `SattLineProject.load`,
  casefolded identity, `.l`/`.z` dependency resolution, `.g`/`.y` companions,
  structured load errors, and hermetic `cache_dir=None` loads.

### Added

- Phase 4 of the project-layer plan: graphics companion parsing. The loader now
  resolves each program's same-directory `.g` / `.y` companion via
  `resolve_graphics_companion_path` (draft prefers `.g`, falls back to `.y`;
  official and `.x` code only accept `.y`; a `.g` / `.y` input resolves to
  itself) and parses it into a `GraphicsModel` on `SattLineProgram.graphics`.
  `parse_graphics_text` / `parse_graphics_file` scan composite records (families
  `1`/`2`/`4`/`5`), picture-display records (`9031`, keep-shape flag, variable /
  literal path rows), and `Var`/`Lit`/`Expr` bindings — including Lark-parsed
  expression bindings with source-span offsetting. Graphics content problems
  become `GraphicsMessage` values (`errors` / `warnings` properties); companion
  read failures map to `ArtifactLoadError` / `DependencyParseError` honoring the
  existing strict/non-strict behavior.
- Phase 3 of the project-layer plan: `SattLineProject.load` is now wired end to
  end. `read_dependency_names` parses `.l` / `.z` dependency files, `ProjectLoader`
  recursively resolves dependencies requester-relative to the declaring file with
  casefolded identity memoization (each program visited and parsed exactly once;
  cycles resolve as edges in the derived graph, never raised), and loads can store
  results in the parser-owned `FileLookupCache` plus a new HMAC-signed pickle
  `FileASTCache` (`FILE_AST_CACHE_VERSION = 1`, stat-snapshot validated) under a
  caller-supplied `cache_dir`. Structured failures map to `DependencyNotFoundError`,
  `DependencyParseError`, and `ArtifactLoadError`, and `strict=False` skips failing
  programs instead of aborting.
- Phase 2 of the project-layer plan: `ArtifactKind`, the extension helpers
  (`code_ext`/`deps_ext`/`graphics_ext`, `*_ext_candidates`,
  `preferred_extension`, `candidate_extensions`), the per-root `SourceIndex`,
  requester-relative ordered lookup (`ordered_lookup_bases`,
  `shared_lookup_root_for`, `ProjectLookup` with `find`/`find_code`/`find_deps`),
  and the parser-owned, versioned `FileLookupCache`
  (`LOOKUP_CACHE_VERSION = 1`). Artifact extension/draft-fallback rules and
  per-artifact discovery now live in the parser; loading behavior still lands in
  later phases.
- New `sattline_parser.project` layer (Phase 1 of the project-layer plan):
  `LoadMode`, `ProgramFormat`, the graphics companion model (`GraphicsModel`,
  `GraphicsMessage`, `GraphicsCompositeRecord`, `GraphicsPictureDisplayRecord`),
  `SattLineProgram`, `SattLineProject`, `DependencyGraph`, and the structured
  load errors (`ProjectLoadError` and subclasses). Additive only — artifact
  discovery and loading behavior land in later phases.

## [2026.9.1] - 2026-09-06

### Changed

- `parse_source_text` / `parse_source_file` no longer attach the Lark parse tree
  to the returned `BasePicture` by default. Pass `retain_parse_tree=True` to
  keep the tree; the default now avoids retaining hundreds of MB of parse-tree
  nodes for large programs.
- Identity `SourceDocument`s (plain, un-preprocessed text) no longer
  materialize the per-character `char_map`; positions map directly, saving a
  `tuple(range(len(text)))` allocation that could reach hundreds of MB.

### Performance

- `SourceDocument._line_starts` now locates line breaks with `str.find` instead
  of a per-character loop (~20x faster on large sources).
- `_token_span` reads token positions via direct attribute access instead of
  `getattr` (slightly cheaper per numeric/boolean literal).

## [2026.8.4] - 2026-08-27

### Added

- `Variable.has_explicit_default` to distinguish `:= Default` from omitted
  initializers; transpilers now know when an explicit default was written.
- `ModuleTypeDef.is_private` and `ModuleHeader.enable` tri-state (`None` absent,
  `True`/`False` explicit) so the AST preserves the exact source intent.
- `Equation.layer_info` (int) retained on the AST instead of being silently
  discarded during transformation.
- Polygon type list stored in `GraphObject.properties["polygon_type"]` and
  segment endpoint coordinates stored as `"segment_point"` so geometry data is
  no longer lost.
- `SymbolModule` and `Non_Zoomable` markers propagated into
  `invocation_arguments`.
- Grammar terminals `SYMBOLMODULE`, `NON_ZOOMABLE`, `PRIVATE_KW`, `LITSTRING`,
  and `FORMATSTRING` with dedicated regex patterns.
- Numeric bounds checking: `INT_MIN`/`INT_MAX` and `REAL_MAX` constants; out-of-
  range integer and real literals are clamped to ABB limits with a warning.
- Compression detection now reads the header flag (`C`/`N`) on the first line;
  the flag is authoritative and overrides the marker heuristic.
- Lexer lookahead for `MODULE_TYPE_NAME` verified correct across all edge cases
  (comments, nested comments, keyword casing, trailing-junk rejection).
- `SUBSEQSTEP`/`ENDSUBSEQSTEP` grammar terminals and `seqsubstep` rule so SFC
  subsequence step blocks parse and transform into `SFCSubsequence` nodes.
- `seqtransitionsub` now accepts an optional `NAME`, allowing unnamed nested
  `SUBSEQTRANSITION` blocks that appear in real ABB libraries.
- `SFCTransitionSub.name` widened from `str` to `str | None` for unnamed
  transitions.
- Four new compressed markers: `#2;`→`SUBSEQSTEP`, `#2<`→`ENDSUBSEQSTEP`,
  `#3:`→`SUBSEQUENCE`, `#3;`→`ENDSUBSEQUENCE`.
- Golden-file parse and decode tests for `CompressedFullGrammar.s` and
  `UnCompressedFullGrammar.s`.
- 15 new coverage-edge tests driving 100% line coverage (299 total).

### Changed

- Grammar literals replaced with `GRAMMAR_VALUE_*` constants for single-source
  truth on token strings.
- Modifier keywords (`Secure`, `State`, `Const`, `OpSave`) resolved through
  `constants.GRAMMAR_VALUE_*` instead of hardcoded strings.
- `ModuleHeader.layer_info` type narrowed from `str | None` to `int | None`.
- `read_text_with_fallback` preserves original CRLF line endings by reading in
  binary mode and decoding manually.
- Removed redundant `"ClippingBounds"` literal from `coord_clippingbounds`
  grammar rule.
- `ProcedureInteract` moved from `interact_type_simple` to `combutproc_item`
  so its procedure-call arguments parse correctly (fixed 3 UnSupported*.x
  real-library files).
- SEED_MAPPING deduplicated (removed stale `#;5`/`#;6`/`#;7` entries).

### Fixed

- Typo `"ModulType{"` corrected to `"ModuleType{"` in AST display string.
- Dead chained-comparison code and its test removed from
  `_expressions_mixin.py`.
- Test fixture `CompressedSequenceBasic.s` header corrected from `N` to `C` to
  match its actual compressed content.

## [2026.8.3] - 2026-08-24

### Added

- Source provenance tracking with `SourceDocument` and `SourceSpan` mappings
  back to the original source, including compressed input.
- Support for decoding coded `.x` streams used by ABB/SattLine.
- End-to-end parsing and transformation of real `ControlLib.x` and `BatchLib.x`
  libraries.
- Corpus regression tests covering real SattLine constructs and edge cases.
- Stronger fuzzing infrastructure with deterministic corpus regression,
  subprocess timeouts, and better failure classification.

### Changed

- Hardened preprocessing so syntax-looking text inside strings and comments is
  never rewritten.
- Reworked preprocessing into explicit decoding and normalization stages with
  source-map preservation.
- Refactored the grammar to use `sattline.lark` as the single authoritative
  grammar.
- Improved source-position mapping, including end-of-input boundaries.
- Preserved multi-layer `ModuleDef` blocks and unnamed SFC steps.
- Added support for additional SattLine/ABB constructs including module
  definition options, layer information, enable-expression tails, and
  optional SFC names.
- Strengthened transformer validation to prevent unexpected structures from
  silently disappearing.
- Improved concurrent parsing by making comment-depth state local to each parse.
- Expanded CI to enforce linting, formatting, strict typing, coverage,
  security checks, packaging, compatibility, and installed-package tests.

### Fixed

- Prevented compressed-source detection from being triggered by markers inside
  strings or comments.
- Fixed silent data loss for interactor types, flag names, procedure names,
  module options, communication procedure assignments, and duplicated enable
  tails.
- Fixed parser type-safety issues and removed unnecessary `Any`/`cast` usage.

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
- Extended comment grammar (`change_description`, `module_typedescription`)
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
