# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses calendar versioning (`YYYY.M.N`). The version orders
releases; it is not a compatibility contract. The public API and its stability
policy are documented in the README.

## [Unreleased]

### Removed

- **Singular module block fields.** `SingleModule`, `FrameModule`,
  `ModuleTypeDef` and `BasePicture` no longer store `moduledef` and
  `modulecode`. The names remain as read-only properties returning the last
  entry of `moduledefs` / `modulecodes`, so reading them still works and the two
  views cannot disagree. Construction through the singular keyword arguments,
  assignment to the properties, and the corresponding `moduledef` /
  `modulecode` keys in `sattline parse --tree` output are removed; use the
  block lists instead.

### Fixed

- **Multi-block identifier checks and counts.** Declaration identifier
  validation and the `parse` / `diff` structural counts now cover every
  `ModuleDef` and `ModuleCode` block instead of only the last one.

## [2026.11.3] - 2026-11-02

### Added

- **Internal builtin registrations.** 191 names the system binds for compiled
  programs but does not publish as language built-ins are carried in the
  catalogue under `meta.internal`. Calls to them now get arity and argument
  checks instead of passing silently; `documented_total` still counts only the
  manual-documented names.
- **Record field tables.** 27 configuration-defined system records are added
  (`StepStatus` family, `SchedulerObjectInfo`, `ScanGroupInfo`, `Semaphore`,
  `JChannelType`, `JournalInfo`, `EventInteract`, the serial/printer/task setup
  records and others), and eight incomplete tables are filled in: `Timer`,
  `AcofTimerType`, `RandomGenerator`, `EventSortRecType`, `SortedEventType`,
  `CalendarRecord`, `GroupData` and `AsyncOperation`. Only `tObject`,
  `ArrayObject` and `QueueObject` keep an empty spec, because they have no
  fields at all rather than an unknown shape.
- **Program-wide SFC element names.** A dotted runtime accessor may name a step
  or sequence from anywhere in the program, including a nested frame module.
- **Base-picture module parameters.** `BasePicture` now carries the
  `MODULEPARAMETERS` block it declares, and `sattline query symbols` lists them.
- **`--validate` flag.** `sattline project --validate invoked|full|none`
  selects the validation scope; `--no-validate` remains an alias for `none`.
- **`PARSE_FAILURES`.** One exception taxonomy for "this source could not be
  parsed", shared by `sattline check` and the project loader.

### Changed

- **Validation scope default.** `LoadValidation.INVOKED` is now the default for
  `SattLineProject.load` and `sattline project`: each target is validated in
  full, while a dependency file contributes only the module types the target
  invokes, transitively. `FULL` remains available for a whole-tree audit. On a
  138-program unit library this removed 183 dependency findings that had
  nothing to do with the selected programs.
- **`--fail-on` vocabulary.** `sattline check`, `corpus` and `project` share one
  set of values (`none`, `error`, `any`) and one implementation. The earlier
  `never` and `warning` spellings are still accepted as aliases.
- **`sattline graphics --json`** emits exactly one document; findings ride
  inside it instead of being printed as a second JSON document.
- **`sattline_parser.api` is a facade.** The parse pipeline moved to
  `sattline_parser.source_io` so the project layer no longer imports the public
  module back. `api` re-exports the same names. Identifier folding moved from
  `sattline_parser.validation.names` to `sattline_parser.names`. Both modules
  are outside the documented public surface.
- **`tObject` arguments** must now be a non-scalar. Passing an integer, real,
  boolean, string or time where an object handle is declared is a type
  mismatch again, as is passing one where `AnyType` is documented.
- **`fuzz_harness.TimeoutError`** is renamed to `FuzzTimeoutError` so it no
  longer shadows the builtin exception.
- **Artifact extensions** have one owner: `project/formats.py` now exposes the
  complete per-kind extension sets and the `.x` → `.y` companion rule that the
  discovery, graphics and CLI layers had each re-spelled.

### Fixed

- **False datecode conflicts.** Conflicting definitions were compared against
  every program loaded so far instead of the target's dependency closure, so
  unrelated programs that happened to declare the same module type reported
  drift. On the trial tree this was 237 false findings across 88 programs.
- **False undefined-variable findings for SFC elements.** A reference such as
  `Seq.Reset` or `Step.x` from a module whose element lives in a nested frame
  module was reported as an undefined variable (41 occurrences in one
  library).
- **Base-picture module parameters were undefined everywhere.** The transformer
  parsed the block and discarded it, so even the program's own module code
  could not reference its parameters.
- **Frame modules lost their declarations.** A frame module's parameter and
  local blocks were dropped when the AST was built.
- **Coded streams.** A stream whose header lost its CRLF terminator fell
  through to the plain-text decoder instead of reporting the framing error, and
  a legitimate NUL in source text was mistaken for an unrestored placeholder.
- **Compression detection** counted structural keywords inside strings and
  comments, so a comment could veto a correct classification.
- **`sattline project`** reported unexpected failures as findings (exit 1)
  instead of internal errors (exit 3), and treated a root that exists but is not
  a directory as an empty tree.
- **Two predicates for one question.** `is_numeric`/`is_numeric_datatype` and
  `is_boolean`/`is_boolean_datatype` disagreed on `None`; both pairs now share
  one implementation.
- **Datatype folding.** `Simple_DataType.from_any` used Unicode lowercasing
  while every other identifier folds through the CP1252 table.

### Removed

- The `_parser_core_*.py` test-module indirection: the tests are collectable by
  name and the wildcard aggregator is gone. Internal duplicates (the counter and
  IP4 signal field shape, the PID parameter block, the span-remapping helpers,
  the tentative-marking pass, the IF/ELSE printer, four copies of
  `_positive_int`) are collapsed.

## [2026.11.2] - 2026-11-01

### Added

- **Ambiguous SEQFORK targets.** A fork target that is declared more than once
  in a module now reports an ambiguous-target finding in addition to the
  duplicate element name. The target is not resolved by guessing a kind.
- **Grammar fingerprint module.** The resolved grammar and its SHA-256 are now
  available from `sattline_parser.grammar.resolved`, and the Lark cache uses the
  same fingerprint.

### Changed

- **AST cache identity.** Per-file AST cache keys and metadata now include the
  package version and grammar fingerprint, so an upgrade cannot serve an AST
  from an older parser or grammar. Entries built by another identity are pruned.
- **Dependency visibility.** Each program is validated against the datatypes and
  module types from its own transitive dependency closure, not every program
  loaded before it. A second target can no longer hide an unknown-name finding
  in an unrelated program.
- **Validation performance.** The type graph is built once per program
  validation instead of once per expression, and idle cache startup skips the
  full identity prune when the cache marker already matches. A warm 46-file
  project load with `INVOKED` validation dropped from about 216 seconds to
  about 10 seconds.
- **Invoked validation scope.** `LoadValidation.INVOKED` validates each target
  in full and limits a dependency file to the module types that target invokes,
  transitively. Unused library module types and their bodies are no longer
  checked.
- **Record ownership.** A consumer no longer reports field findings from a
  dependency's record definitions. Those findings stay with the defining
  program.
- **Field resolution.** Builtin record fields resolve through their field
  specifications. Unresolved fields on opaque or system record types, temporal
  component accessors, and SFC runtime accessors stay silent instead of being
  reported as undefined variables.
- **Imported version drift.** Datecode conflicts are reported for explicitly
  selected programs, not for library files pulled in as dependencies.
- **Opaque system datatypes.** System datatype names that no loaded source
  declares are accepted as opaque declarations. Field access on them stays
  silent because their shape is not known.
- **Coverage reporting.** The coverage gate prints how many executable lines the
  exclusion rules keep outside the 100% line gate. The dead grammar-promotion
  probe and its exclusions are gone.
- **Versioning policy.** The changelog now states calendar versioning, and the
  README defines the supported public surface and its stability expectations.
- **Dependency floor.** The `regex` lower bound is relaxed to `2023.12.25`, the
  first declared release with the Python 3.12 wheels used by CI. No parser
  feature needs a newer release.
- **Parity manifest stability.** Parse failures are recorded as a stable marker
  instead of the exception text, whose expected-token list is unordered and
  changed between runs.
- **Project-layer mapping coverage.** Tests now pin that a module instance may
  omit every parameter mapping and that a mapping target field resolves through
  a datatype declared in a loaded dependency.

### Removed

- **Consumer parity mode.** The parity exporter no longer builds a SattLint
  manifest, and the historical known-differences file is removed. SattLint
  consumes parser diagnostics directly, so the parser manifest is the only
  oracle.
- **Unused datatype usage fields.** `DataType.read`, `DataType.written` and
  `DataType.usage_locations` are removed; consumers keep usage in their own
  models.
- **Dead lexer probe.** The `MODULE_TYPE_NAME` promotion branch and its helpers
  are removed. The grammar has no such terminal, so the branch could never run.

### Deprecated

- **AST graphics transport fields.** `BasePicture` still declares the
  consumer-owned graphics lists and `library_dependencies` so existing consumers
  keep working, but the parser never writes them. Graphics data is on
  `SattLineProgram.graphics`; the fields carry deprecation metadata and will be
  removed once consumers move that state into their own graph model.

## [2026.11.1] - 2026-11-01

### Added

- **Picture display path row lines.** `GraphicsPictureDisplayRecord` now
  carries `path_row_lines`, the one-based lines of the record's path-row
  section. It includes rows that do not parse into a `GraphicsPathRow`, so a
  consumer can tell section rows apart from other binding lines.

### Fixed

- **Builtin call arity and handle types.** The trailing `AsyncOperation` and
  `DebugStatus` parameters are now marked optional, so calls may omit them.
  A `tObject` parameter accepts object handles such as file handles, and an
  `AsyncOperation` parameter accepts its integer-backed handle.
- **Datatype declarations and transfers.** `AnyType` and builtin record names
  count as declared datatypes, and moduletype transfers use the shared builtin
  compatibility rule so string families are interchangeable.
- **Project cycles.** Projects assembled from programs directly now compute
  cycle paths as well.
- **Record field helpers.** The helpers accept a structural field graph, so
  consumers can supply their own implementation without subclassing.

## [2026.11.0] - 2026-10-31

### Added

- **`sattline_parser.builtins`.** A language-data package with the documented
  builtin function signatures (`functions.py`, generated `catalogue.json`) and
  the builtin record field specifications (`records.py`). The catalogue is
  regenerable with `scripts/gen_builtin_catalogue.py` and records the manual
  edition, the documented total, and the names it carries without a public
  source.
- **Graphics structural records.** `GraphicsModel` now carries
  `composite_records` and `picture_display_records`, and the companion scanner
  reports an unterminated record and a missing trailing `KeepPictureShape` flag
  as structural messages. `parse_graphics_text`, `parse_graphics_file` and
  `resolve_graphics_companion_path` are re-exported from
  `sattline_parser.api`.
- **Project load validation.** `SattLineProject.load` takes
  `validate=FULL|NONE`, runs the single-file validator per program with the
  definitions visible from already-loaded dependencies, and stores the findings
  on `SattLineProgram.diagnostics`. Programs now carry `library`,
  `resolved_base`, and `origin_file`/`origin_lib` provenance. The loader marks
  external-dependent findings `tentative` when a non-strict load skips part of
  the closure, reports definition datecode conflicts, and exposes
  `SattLineProject.cycles()` and `libraries()` as data. `sattline project`
  reports validation findings and accepts `--fail-on` and `--no-validate`.

### Changed

- **Validation rule engine.** `validate_basepicture` now checks the full
  documented builtin registry instead of the eight-entry subset: arity,
  variable-reference requirements for `in var`/`out`/`inout` parameters, and
  argument datatypes. It also applies identifier limits and reserved keywords,
  logical-operand and unary-operand typing, equality compatibility, ternary
  branch compatibility, module-type parameter mappings, and step/sequence
  runtime accessor availability (`.Hold`, `.Reset`, `.T`). Record field
  resolution moved to `validation/type_graph.py`; scalar rules and literal
  inference live in `validation/typing.py`.
- **Validation parity manifest.** `tests/fixtures/validation/expectations.json`
  records the code, severity, and span of every diagnostic for every corpus
  fixture. `tests/fixtures/validation/known-differences.json` records the
  intentional differences from the previous consumer-layer validator, with a
  reason per entry. The exporter is `scripts/export_parity_expectations.py`.

## [2026.10.1] - 2026-10-29

### Added

- **`sattline` command line.** A JSON-first CLI over the library, with one
  entry point (`sattline` and `python -m sattline_parser`) and nine
  subcommands:
  `check` (decode + parse + validate, one finding shape for parse errors,
  decoder refusals and validator diagnostics, with `--json`/`--jsonl`,
  `--severity`/`--rule`/`--max-findings` filters and `--fail-on`),
  `parse` (summary or depth-bounded AST as JSON), `query` (symbols,
  references, writers, callers, graph/interact objects and sequences, filterable
  by name, module path and limit), `project` (load a tree, list programs and
  artifacts, walk `--graph`/`--of`/`--reverse`/`--depth`, report `--cycles`),
  `graphics` (companion bindings and scan messages),
  `decode` (coded source to plain text,
  `--report`/`--json`), `diff` (findings and structural counts between two
  units), `corpus` (parallel tree triage with a rule histogram and
  `--fail-on`) and `version` (tool plus schema ids). Every payload is tagged
  `"schema": "sattline.v1.<command>"`. Exit codes are the contract — `0` clean,
  `1` findings, `2` usage/input, `3` internal — and a traceback is only printed
  under `--debug`. Findings never print internal rule ids as text; the JSON
  carries them for baselines and diffs. Commands are read-only: no `--fix`, no
  `--write`, no network, no watch mode. Source files are read exactly like
  `parse_source_file`: plain Windows-1252, marker-compressed text and the binary
  `\x80 3.1` `.x` framing all decode transparently (undefined cp1252 bytes stay
  refused outside comments), for files and stdin alike. The entry point is
  registered as the `sattline` console script next to
  `python -m sattline_parser`; `scripts/smoke_installed.py` exercises both from
  the built wheel and sdist.

- **Builtin catalogue.** `validation/builtin_catalogue.json` carries the eight
  builtin signatures the validator checks (`CopyTime`, `CopyVariable`,
  `CopyString`, `Equal`, `EqualStrings`, `GetStringPos`, `SetStringPos`,
  `StringLength`) with their arity and write-like argument positions. Names
  outside the catalogue stay unchecked, which is deliberate: a complete
  namespace would need every user library, so a false reject there is worse
  than a missed one.

- **Compact-source honesty check.** A header-flagged compact file (`C` in the
  syntax-version line) that spells a keyword as a raw word is refused with
  `Raw keyword 'SeqControl' at line N in compact source`. In coded mode raw
  words are identifiers and never keywords, so promoting them (which expanding
  codes and re-lexing does) would accept a unit the tool rejects. Editor-produced
  compact files never spell keywords raw (verified against the
  compressed/uncompressed golden twins), so real files are unaffected.

- **SL-V036 `SEQUENCE_POSITION_INVALID`** with the S/T/M position model in
  `validation/sequences.py`: closed bodies are `(S T | M)+`, alternate branches
  and `SUBSEQTRANSITION` bodies are `T (S T | M)*`, parallel branches and
  `SUBSEQSTEP` bodies are `M* S (T M* S)*`, and `OPENSEQUENCE` uses the open
  variant. `SL-V016`/`SL-V023`/`SL-V024`/`SL-V033` now all come from that single
  walk. This reproduces the probe verdicts for `EdgeSeqAlt`,
  `ValidSubSeqTransB` and `ValidOpenSeqSeq`; those corpus fixtures had encoded
  the rejected shapes and were corrected.

- **SL-V035 `OLD_STATE_NOT_WRITABLE`**: writing to `:Old` is a compiler check
  (expression error `0x14`) for assignment targets and for reference-required
  built-in arguments; reads and `:New` writes stay legal.

- **`DateCode_` is a fixed keyword** (scanner token 0x89/137) instead of `NAME`
  plus an integer, so `Bogus_ 5` is rejected; the attribute is optional on
  records, module definitions and module types, and `BasePicture.datecode` now
  preserves the root stamp.

- **`validation/datecode.py`**: `normalized_datecode` (non-negative
  `n % 2 000 000 000`; negatives refused rather than given Python's modulo sign)
  and `compute_datecode` (the clock formula), deliberately separate from
  parsing.

- **`validation/names.py`**: identifier identity now uses a fixed CP1252
  upper-byte table instead of `str.casefold`, so `Straße`/`STRASSE` and
  `ﬁle`/`FILE` no longer resolve to the same symbol. The table maps `a-z` to
  `A-Z`, `9A` to `8A`, `9C` to `8C`, `E0-F6` to `C0-D6`, `F8-FE` to `D8-DE` and
  `FF` to `9F`. Filesystem identity in the project layer keeps `casefold`.

- **SL-V037 `SEQUENCE_FORK_TARGET_KIND`**: a fork hosted on a step must name
  transitions and a fork hosted on a transition must name steps; the existing
  `SL-V017` still reports genuinely unknown names.

- **`SEQFORK` is accepted on `SEQINITSTEP`** as well as `SEQSTEP`, and on
  `SEQTRANSITION` after its optional guard.

- **`Module_In_View = True|False [: tail]`** is an explicit invocation-header
  property (scanner token 0xA4) stored as `ModuleHeader.module_in_view`,
  distinct from `Enable_`; it accepts `True`/`False` only, not `On`/`Off`.

- **`EQUATIONS`** is accepted as an alias of `EQUATIONBLOCK`.

- **`On`/`Off` typed as boolean literals** in expression analysis, so `Num = On`
  and `Flag = Num > Off` are now rejected like the real compiler rejects them.

- **Keywords are matched case-insensitively**, as the scanner setup does:
  `moduledefinition`, `enddef`, `true`, `:old` and
  `seqcontrol` all parse like their canonical spellings. Lark 1.3.1 has no
  `case_insensitive` option, so `grammar/keywords.py` rewrites the resolved
  grammar - letter-bearing string terminals become `/(?i:…\b)/` regexes, and
  regex terminals (including `NAME`'s keyword exclusion list and
  `STATE_SUFFIX`) gain a `(?i:…)` scope. Punctuation terminals are untouched.

- **`EQUATIONBLOCK`/`EQUATIONS` name and coordinate metadata are optional**:
  `Equation.name`, `.position` and `.size` are `None` when the source omits
  them, instead of being rejected.

- Validation rule **SL-V027 `PARAM_TRANSFER_TYPE_MISMATCH`**: a module-type
  instance whose parameter transfer supplies an incompatible variable type is
  now flagged (real-parser confirmed: `Submodule Child, parameter EnableFlag:
  Variable CounterValue is an invalid type`). Implemented in
  `sattline_parser.validation.transfers`; GLOBAL/literal sources, undeclared
  sources, unknown target parameters, `AnyType` formals, numeric widening
  (integer↔real), and record-typed transfers are handled.

- **PEP 561 typing marker.** The package now ships `py.typed`, so downstream
  type checkers use the inline annotations instead of treating the package as
  untyped (`[tool.setuptools.package-data]` ships it, and
  `tests/test_packaging.py` asserts it in the installed artifact).

### Changed

- **Findings always carry a location.** Every sequence element now keeps its
  source span (`SFCStep`, `SFCTransition`, `SFCTransitionSub`, the
  alternate-branch node, `SFCParallel`, `SFCSubsequence`; one `seq_element`
  transformer hook attaches it), and the
  position/fork/duplicate-name diagnostics report it. All 75 findings produced
  over the two fixture corpora are now locatable; before, 13 (17 %) were
  message-only, which forced a reader to search the unit.

- **Parse errors read as sentences about the source.** `describe_parse_error` no
  longer forwards Lark's dump (`Unexpected token Token('NAME', 'is') ... Expected
  one of: COMMENT_START, INVOCATION`). It reports what was found, what was
  expected in source spellings (terminal names are rendered through the resolved
  grammar: `';'`, `'ENDDEF'`, `a name`, `a number`), drops always-legal comment
  terminals, caps the list at five, and adds an actionable `help:` line for
  recognised shapes (end of file before a required `';'`, a unit missing its
  quoted header lines, a near-miss keyword). `ParseErrorDetails` additionally
  exposes `found`, `expected`, `hint` and `source_line` so tools do not have to
  parse prose.

- **Composite markers take only the layer clause.** `composite_object` was
  `COMPOSITEOBJECT common_properties`, so a marker accepted `Enable_`, colour
  assignments and connection nodes that the documented rule rejects. It is now
  `COMPOSITEOBJECT comments? layer_info?`, and `GraphObject` for a marker keeps
  the `Layer_` clause under the same `layer` key other objects use. The recorded
  "LALR rejects real files" note was stale: the narrowed rule parses the corpus
  identically and rejects the extra properties.

- **`On`/`Off` are value literals.** `value` now accepts `ON_KW`/`OFF_KW`
  alongside `BOOL`, so expressions and initializers take `On`/`Off` as booleans
  (they previously bound as `VarRef`s). The graphics/interact property readers
  keep their `True`/`False`-only `BOOL`, `BOOL_NOTAIL` and `plain_value`
  allowlists, as the documented readers require. The contextual lexer keeps
  `On`/`Off` usable as ordinary names elsewhere.

- **Interactor clauses: `Relative_`/`Abs_` and `IntObjPickButton`.** Both bare
  selectors are now distinct productions (`interact_scale_selector`, scale mode
  `relative`/`abs`) instead of anonymous `NAME` flags, and the shared interactor
  property clause `IntObjPickButton "=" STRING [VarName]` is
  modelled as `interact_pick_button` with `is_reference` set from the postfix
  `VarName`. The interact body is still an unordered repetition, so the slot
  position is not enforced.

- **`Equation.kind` records the `EQUATIONS`/`EQUATIONBLOCK` spelling.** The two
  keywords set different flags, and their effect is not documented, so the model
  preserves which one was written.

- **Coded-mode lexing keeps raw words as identifiers.** The decoder no longer
  refuses a compact file that spells a keyword raw; instead the lexer consults the
  source-map provenance per token: a keyword token is only a keyword when the
  decoder produced its characters (they are `GENERATED` in the map), so a raw word
  is `NAME` exactly as the grammar describes. Literal spellings the compressor
  writes unencoded (`True`/`False`/`On`/`Off`/`Default`) stay literals. The old
  `Raw keyword ...` decode error is gone; `CodedRawKeyword.s` is now a syntax
  error like the real tool reports.

- **`GraphObject.span`.** Graph objects carry their source span, taken from the
  `graph_object` rule meta.

- **Sequence syntax aligned with the documented readers.** `SEQFORK` is no
  longer a sequence element: it is a suffix of its host
  `SEQSTEP`/`SEQTRANSITION`, reads one or more comma-separated targets and may
  end with `SEQBREAK`. `SFCFork` now carries `has_break`, lives on
  `SFCStep.fork` / `SFCTransition.fork`, and `SFCBreak` is gone: a standalone
  `SEQBREAK` is rejected at parse time, like the real tool. Sequence bodies must
  be non-empty, `SEQTRANSITION` may omit both its name and `WAIT_FOR`
  (`condition is None` preserves the omission), `SUBSEQUENCE`/`SUBSEQSTEP` names
  are optional, and `SFCSubsequence` distinguishes `kind="sequence"` (structural
  position) from `kind="substep"` (step position).

- **Statement semicolons are optional** in code blocks, so
  `Flag = True` followed by a newline terminates a statement.

- **Source files are now decoded strictly as Windows-1252 (cp1252)** — the only
  encoding the real SattLine parser accepts. `read_text_with_fallback` (which
  tried utf-8, then cp1252, then latin-1) is replaced by `read_text_cp1252`,
  which has **no encoding fallback**: bytes that are not valid Windows-1252
  (`0x81 0x8D 0x8F 0x90 0x9D`) now raise `UnicodeDecodeError` instead of being
  silently re-read as latin-1. This removes a silent-fallback path that could
  decode a mis-encoded file into plausible but wrong text. (Breaking rename of
  the public `read_text_with_fallback` export; behavior of `load_source_text`,
  `parse_source_file`, and the project loader is otherwise unchanged.)

- **Packaging metadata follows PEP 639.** `project.license` is the SPDX
  expression `MIT` and the licence text ships through `license-files`, so the
  setuptools deprecation warning for the TOML-table form is gone. The built
  distributions are otherwise unchanged.

### Fixed

- **Compressed-source marker table replaced by a data file.**
  `preprocessing/compressed.py` no longer carries the 172-entry sample-derived
  `SEED_MAPPING`. The compact-code table now ships as
  `preprocessing/scanner_tokens.json`, keyed by scanner ordinal (id `n` encoded
  as `'#' + chr(48 + n // 16) + chr(48 + n % 16)`). Four entries the old table
  got wrong are corrected against the checked-in compressed/uncompressed pair:
  `#1=` is `On` (was `True`), `#1>` is `Off` (was `False`), `#9<` is
  `Module_In_View` (was `Enable_`), `#:=` is `Relative_` (was `Abs_`).
  `SCANNER_TOKENS` is the canonical name, `SEED_MAPPING` remains as an alias.

- **A dependency sidecar is read at the selected body's own prefix.** The
  loader used to resolve code and `.l`/`.z` through two independent whole-root
  scans, so `A/Lib.x` could be paired with `B/Lib.z` and that library's own
  dependencies then resolved relative to `B`. `ProjectLookup.find_deps_beside`
  now resolves the sidecar only beside the chosen body (LIB-05); a sidecar that
  exists elsewhere becomes a
  `LoadDiagnosticKind.SIDECAR_ELSEWHERE` diagnostic instead of being paired.

- **Missing and empty sidecars are visible.** `SattLineProgram` gained
  `deps_path` and `sidecar` (`SidecarState.ABSENT / EMPTY / PRESENT`), and
  `SattLineProject.diagnostics()` reports absent / empty / stray sidecars plus
  dependency cycles. These are the conditions the loader reports and an operator
  may continue past, so they are surfaced rather than raised; the `strict=True`
  contract for missing *bodies* is unchanged.

- **Warm and cold lookups now agree on extension precedence.** A cached `.x`
  no longer shadows a `.s` that appeared later at the same prefix (gap P10);
  the cached base is still trusted, but extensions are tried in preference
  order.

- **A partial project load is never silent.** `SattLineProject.load(strict=False)`
  now records every program it had to leave out as
  `LoadDiagnosticKind.LOAD_SKIPPED` (`load-skipped`) instead of only omitting it
  from the result, and `sattline project --lenient` reports those diagnostics and
  exits `1` rather than pretending the tree was complete. A declared dependency
  that could not be loaded keeps its edge and appears in the diagnostics.

- **`sattline project` roots follow the loader's model.** Target discovery now
  looks at the artifacts directly inside each root, matching the ordered
  lookup — a directory that merely *contains* libraries is refused with
  `no source files directly under <root>; pass each library directory as a root`
  instead of silently loading nothing.

### Security

- **Locked development dependencies refreshed.** `certifi`, `filelock`,
  `msgpack`, `urllib3` and `virtualenv` were upgraded in `uv.lock`, so
  `pip-audit` over the locked environment reports no known vulnerabilities.

## [2026.9.2] - 2026-09-22

### Added

- Phase 4 of the project-layer plan: graphics companion parsing. The loader
  resolves each program's same-directory `.g` / `.y` companion via
  `resolve_graphics_companion_path` (draft prefers `.g`, falls back to `.y`;
  official and `.x` code only accept `.y`; a `.g` / `.y` input resolves to
  itself) and scans it into a `GraphicsModel` on `SattLineProgram.graphics`.
  `parse_graphics_text` / `parse_graphics_file` read `Var` / `Lit` / `Expr`
  bindings, including Lark-parsed expression bindings with source-span
  offsetting. Binding problems become `GraphicsMessage` values (`errors` /
  `warnings` properties); companion read failures map to `ArtifactLoadError` /
  `DependencyParseError` honoring the existing strict/non-strict behavior.

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

### Documentation

- README: new "Project layer" usage section covering `SattLineProject.load`,
  casefolded identity, `.l`/`.z` dependency resolution, `.g`/`.y` companions,
  structured load errors, and hermetic `cache_dir=None` loads.

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
