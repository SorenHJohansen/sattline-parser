# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Compressed-source marker table replaced by the recovered scanner token
  table.** `preprocessing/compressed.py` no longer carries the 172-entry
  sample-derived `SEED_MAPPING`. The compact-code table now ships as
  `preprocessing/scanner_tokens.json` — the 206-entry `.SCANNER` enum extracted
  from the workstation's 3.1 configuration container (scanner ordinal `n` encoded
  as `'#' + chr(48 + n // 16) + chr(48 + n % 16)`, ids 9–214, dense). Four
  entries the old table got wrong are corrected: `#1=` is `On` (was `True`),
  `#1>` is `Off` (was `False`), `#9<` is `Module_In_View` (was `Enable_`, which
  collided with `#64`), `#:=` is `Relative_` (was `Abs_`). 34 codes that used to
  raise `PreprocessError` now decode, including `PUBLIC_`, `EQUATIONS`,
  `Invisible_`, `Non_Expandable_`, `Disable_`, `Der`, `Der2`, `RealVar`,
  `xCoord`, `yCoord`, `AutoMan`, `SeqTimerCheck` and `**`. The special-case
  `#01…`/`#0<…` prefix rewrite is gone; `SCANNER_TOKENS` is the canonical name,
  `SEED_MAPPING` remains as an alias. New test proves
  `CompressedFullGrammar.s` decodes to `UnCompressedFullGrammar.s` token for
  token, which the old table could not.

### Fixed

- **A dependency sidecar is read at the selected body's own prefix.** The
  loader used to resolve code and `.l`/`.z` through two independent whole-root
  scans, so `A/Lib.x` could be paired with `B/Lib.z` and that library's own
  dependencies then resolved relative to `B`. `ProjectLookup.find_deps_beside`
  now resolves the sidecar only beside the chosen body (native LIB-05,
  `00589be0`); a sidecar that exists elsewhere becomes a
  `LoadDiagnosticKind.SIDECAR_ELSEWHERE` diagnostic instead of being paired.
- **Missing and empty sidecars are visible.** `SattLineProgram` gained
  `deps_path` and `sidecar` (`SidecarState.ABSENT / EMPTY / PRESENT`), and
  `SattLineProject.diagnostics()` reports absent / empty / stray sidecars plus
  dependency cycles. These are the conditions the native loader reports and an
  operator may continue past, so they are surfaced rather than raised — the
  `strict=True` contract for missing *bodies* is unchanged.
- **Warm and cold lookups now agree on extension precedence.** A cached `.x`
  no longer shadows a `.s` that appeared later at the same prefix (gap P10);
  the cached base is still trusted, but extensions are tried in preference
  order.

### Added

- **Graphics companion correlation.** `graphics_parsing.correlate_composites`
  binds each source `CompositeObject` marker to the next companion record by
  ordinal — the native rule (`00665fc0`, no name lookup) — and reports markers or
  records left over as `GraphicsMessage` values. `GraphicsCompositeRecord.ordinal`
  and `GraphicsCompositeBinding` expose the pair.

- **Native builtin catalogue.** `validation/builtin_catalogue.json` carries the
  492 usable registrations extracted from the workstation's builtin table,
  reduced to arity plus write-like argument positions using the recovered mode
  enum mapping (`00711af0`: `1,2,22→0x01; 4,24→0x02; 6,26→0x03; 8,28→0x08;
  9,29→0x04; 10,30→0x0C; 11,31→0x10`, write-like `0x0A`). Probe-confirmed
  signatures in `_build_builtin_functions` override the extracted ones. Names
  outside the catalogue stay unchecked, which is a deliberate divergence from
  native expression errors 5/6 (a complete namespace would need every user
  library, so a false reject there is worse than a missed one).
- **Compact-source honesty check.** A header-flagged compact file (`C` in the
  syntax-version line) that spells a keyword as a raw word is refused with
  `Raw keyword 'SeqControl' at line N in compact source`. In coded mode raw
  words are identifiers and never keywords (`0062cbc0`), so promoting them —
  what expanding codes and re-lexing does — would accept a unit the tool
  rejects. Editor-produced compact files never spell keywords raw (verified
  against the compressed/uncompressed golden twins), so real files are
  unaffected.

### Changed

- **Companion records are read by their recovered grammar, not by blank
  lines.** `project/graphics_records.py` replaces the line heuristic that ended a
  record at a `0` line followed by a blank line. Each family is consumed field by
  field (`I`/`H`/`F`/`D`/`END`/`MARK`/`WORD`/`WORD2`/`LINE`/`COUNTED`, binding
  reader `004a72d0`, families 1/2/4 and family-5 subtypes 1/2 including the
  version-dependent shape byte and pre-qualifier layouts), so a record boundary
  follows from the record's own structure. Measured on the 743 companion files
  under `~/Projects/Libs`: 727 read to completion (12 535 records, 11 967
  PictureDisplay records, 1 936 indexed path rows) and removing blank lines no
  longer moves any boundary — the 83 files that still differ do so because a
  subtype-1 record stores an empty title/default `LINE()`, which *is* an empty
  line. `GraphicsRecordError` surfaces a structural failure as a `GraphicsMessage`
  instead of mis-splitting, and a family-1/2 payload sub-reader that was never
  transcribed (`004dcc30`, `004f1950`, `004d1fc0`, `00417930`) stops the scan with
  a warning rather than guessing a boundary — 16 corpus files do, and
  `docs/graphics_parity.md` records why.

- **Sequence syntax aligned with the native readers.** `SEQFORK` is no longer a
  sequence element: it is a suffix of its host `SEQSTEP`/`SEQTRANSITION`, reads
  one or more comma-separated targets and may end with `SEQBREAK`
  (`006f9850`, `0070a100`, `0070d180`). `SFCFork` now carries `has_break`, lives
  on `SFCStep.fork` / `SFCTransition.fork`, and `SFCBreak` is gone — a standalone
  `SEQBREAK` is rejected at parse time, like the real tool. Sequence bodies must
  be non-empty, `SEQTRANSITION` may omit both its name and `WAIT_FOR`
  (`condition is None` preserves the omission), `SUBSEQUENCE`/`SUBSEQSTEP` names
  are optional, and `SFCSubsequence` distinguishes `kind="sequence"` (structural
  position) from `kind="substep"` (step position).
- **Statement semicolons are optional** in code blocks (`0072b660`), so
  `Flag = True` followed by a newline terminates a statement.

### Added

- **SL-V036 `SEQUENCE_POSITION_INVALID`** with the native S/T/M position model in
  `validation/sequences.py`: closed bodies are `(S T | M)+`, alternative branches
  and `SUBSEQTRANSITION` bodies are `T (S T | M)*`, parallel branches and
  `SUBSEQSTEP` bodies are `M* S (T M* S)*`, and `OPENSEQUENCE` uses the open
  variant. `SL-V016`/`SL-V023`/`SL-V024`/`SL-V033` now all come from that single
  walk. This reproduces the probe verdicts for `EdgeSeqAlt`,
  `ValidSubSeqTransB` and `ValidOpenSeqSeq`; those corpus fixtures had encoded
  the rejected shapes and were corrected.
- **SL-V035 `OLD_STATE_NOT_WRITABLE`**: writing to `:Old` is a compiler check
  (native `00485470`, expression error `0x14`) for assignment targets and for
  reference-required built-in arguments (`004748b0`); reads and `:New` writes
  stay legal.
- **`DateCode_` is a fixed keyword** (`005ab1b0`, scanner token 0x89/137) instead
  of `NAME` + integer, so `Bogus_ 5` is rejected; the attribute is optional on
  records, module definitions and module types (`005d6170`, `005ccaa0`,
  `005dc3f0`), and `BasePicture.datecode` now preserves the root stamp.
- **`validation/datecode.py`**: `normalized_datecode` (non-negative
  `n % 2 000 000 000`; negatives refused rather than given Python's modulo sign)
  and `compute_datecode` (the `005cb910` clock formula), deliberately separate
  from parsing.
- **`validation/names.py`**: identifier identity now uses the recovered CP1252
  upper-byte table from `00806168` (a–z→A–Z, `9A→8A`, `9C→8C`, `E0–F6→C0–D6`,
  `F8–FE→D8–DE`, `FF→9F`) instead of `str.casefold`, so `Straße`/`STRASSE` and
  `ﬁle`/`FILE` no longer resolve to the same symbol. Filesystem identity in the
  project layer keeps `casefold`.
- **SL-V037 `SEQUENCE_FORK_TARGET_KIND`**: a fork hosted on a step must name
  transitions and a fork hosted on a transition must name steps (native
  `00703430`); the existing `SL-V017` still reports genuinely unknown names.
- **`SEQFORK` is accepted on `SEQINITSTEP`** as well as `SEQSTEP`
  (`0070a100` is a caller of `006f9850` for both) and on `SEQTRANSITION` after
  its optional guard.
- **`Module_In_View = True|False [: tail]`** is an explicit invocation-header
  property (native token 0xA4, reader `00665970`/`00631940`) stored as
  `ModuleHeader.module_in_view`, distinct from `Enable_`; it accepts `True`/
  `False` only, not `On`/`Off`.
- **`EQUATIONS`** is accepted as an alias of `EQUATIONBLOCK` (`00726030`).
- **`On`/`Off` typed as boolean literals** in expression analysis (`00487a60`,
  lowered by `0047d720`), so `Num = On` and `Flag = Num > Off` are now rejected
  like the real compiler rejects them.
- **Keywords are matched case-insensitively**, as the recovered scanner setup
  does (`00626850`/`0062e3d0`): `moduledefinition`, `enddef`, `true`, `:old` and
  `seqcontrol` all parse like their canonical spellings. Lark 1.3.1 has no
  `case_insensitive` option, so `grammar/keywords.py` rewrites the resolved
  grammar - letter-bearing string terminals become `/(?i:…\b)/` regexes, and
  regex terminals (including `NAME`'s keyword exclusion list and
  `STATE_SUFFIX`) gain a `(?i:…)` scope. Punctuation terminals are untouched.
- **`EQUATIONBLOCK`/`EQUATIONS` name and coordinate metadata are optional**
  (`00726030`): `Equation.name`, `.position` and `.size` are `None` when the
  source omits them, instead of being rejected.

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
