# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses calendar versioning (`YYYY.M.N`). The version orders
releases; it is not a compatibility contract. The public API and its stability
policy are documented in the README.

## [Unreleased]

## [2026.11.8] - 2026-11-20

### Added

- **`FrozenMapping` is importable from `sattline_parser.ast`.** A read-only mapping a frozen tree carries is a public type, so a consumer can name it and check it without importing a `models` submodule. It is a `collections.abc.Mapping`, so reading through the abstract class stays valid.

- **`parse_source_bytes` on the top-level package.** `from sattline_parser import parse_source_bytes` now resolves to the same function as `sattline_parser.api.parse_source_bytes`, as the public API table documents.

- **Procedures used as values.** A call to a known procedure now reports `SL-V060` wherever a value is required: an assignment source, a condition, an arithmetic or logical operand, a ternary branch, and a call argument. The catalogue already separated a normal function from a procedure, so `CopyString(S1, S2, I)` in a value position is no longer read as an unproven type. The statement form stays clean and an unknown callee stays silent.

- **Graphics refusal is part of the project surface.** `GraphicsParseError` and `MAX_GRAPHICS_COMPANION_BYTES` are exported from `sattline_parser.project`, so a caller can catch the error an oversized graphics companion raises without importing an internal module.

- **Sequence `Disable` accessor.** A sequence that enables `SeqControl` exposes `.Disable` alongside `.Hold` and `.Reset`. `SL-V019` no longer reports it in module code or in a mapping source, and `SL-V051` reports a missing `SeqControl` for it.

### Changed

- **The invalid-source contract is public and diagnostics keep their line.** `PARSE_FAILURES` is exported from `sattline_parser.api` and documented, a project load failure keeps the underlying parse error's sentence, line, column, and hint, and the CLI excerpt uses the library's line split so a lone CR inside a string no longer shifts `source_line`. `describe_parse_error` now accepts `source_text=None` when only the exception position is known, and `source_line_at` is the public excerpt helper.

- **Bare `ConnectionNode`.** A `ConnectionNode` marker written in an object's `common_properties` is modelled as a `GraphObject` under `properties["connection_node"]` instead of being dropped, so it survives the walk, the serializer, and the formatter. The bare marker is accepted because `common_properties` accepts it in every object; only the positioned form is established for a text object. A text object that writes both forms is rejected as ambiguous rather than resolving one of them.

- **Read-only builtin registries.** `BUILTIN_FUNCTIONS`, `BUILTIN_ALIASES`, `CATALOGUE_META`, and `BUILTIN_RECORD_SPECS` are read-only `FrozenMapping` values, so a caller cannot mutate the public table while validation keeps the table it read at import. Mutation raises `TypeError`, and both paths read one snapshot.

- **AST cache envelope header.** Each entry now starts with a signed JSON metadata header before the pickle. Pruning reads that header to drop an entry whose recorded source path has vanished without unpickling the payload or stat-ing a path from an unverified header.

- **AST cache identity covers the parser stack.** The key and identity marker now include the installed `lark` and `regex` versions and the interpreter version, and `FILE_AST_CACHE_VERSION` is 14. An upgrade inside a dependency pin is a cache miss instead of an AST parsed by one parser stack and served under another.

- **The decode report names the encoding.** `decode --report` and `decode --json` carry `encoding` with the same `plain`, `compressed`, or `coded` values as `parse`, instead of the boolean `coded`, which collapsed marker-compressed text into `coded`.

- **`parse --json` encoding values.** `encoding` is now `plain`, `compressed` (marker-compressed text), or `coded` (a byte-coded stream) instead of collapsing compressed text into `coded`.

- **CLI documents carry the finding envelope on both branches.** `parse --json` (summary and tree) and `query --json` now emit `ok` and `findings`, and query also emits `counts`, so a client reads success and a parse failure the same way. `check --json` `files` holds the display names the findings use, the `parse` and `query` `--jsonl` failure streams are documented, and a relative path outside the working directory becomes an absolute SARIF file URI instead of a `../` reference.

- **Two keywords have no scanner code.** `EQUATIONS` and `IntObjPickButton` have no row in `scanner_tokens.json` and no encoded form has been observed, so a compressed document cannot spell them: a raw spelling is an identifier in coded mode, and an unknown code raises `PreprocessError`. Both failures are clean, and a test pins the set so a future row or terminal keeps the documented limitation accurate. `NewWindow` is not in the set: it is a procedure name, and a compressed document writes it literally. The `NEWWINDOW` keyword terminal it used to carry was unreachable and is removed.

- **Unary sign over a literal.** `format_expr` writes a unary sign separated from a numeric operand, so a `UnaryOp("-", 5)` node is written `- 5` and parses back as the same node instead of collapsing into the signed literal `-5`.
- **Formatter fidelity harness.** A canonical token-stream comparison now runs over every valid and edge-case corpus fixture, so a construct the model drops fails with the fixture name and the missing token instead of passing an AST equality check. The same suite checks that every model field carrying written source is either emitted or listed as a deliberate omission.

- **LALR conflicts are pinned.** A test now asserts the exact shift/reduce conflict set the grammar leaves to Lark's default: 46 conflicts, 38 on `COMMENT_START` and 8 on `CONNECTIONNODE`, each resolved as a shift. A grammar or Lark change that alters a resolution fails the test instead of changing a parse silently.

- **Identifier boundaries follow the lexer everywhere.** An unquoted name may no longer begin with a digit, so `1E5` is always the number `100000.0` and a declaration named `1E5` is rejected with `expected a name`; the quoted form `'1E5'` still spells such a name. A quoted name may not span a line break, which is the rule the compressed-source scanner already applied, so a multi-line quoted spelling is now a parse error rather than a marker that decodes differently from the way the lexer reads it.

- **Project exports are lazy.** The graphics and distribution entry points on `sattline_parser` now resolve on first access, so `import sattline_parser.api` no longer loads the project layer.

- **The loading path holds one library per name.** A root whose directory name repeats an earlier root, folded with the language name table, is shadowed and contributes no units or targets. Library labels are therefore unique, and `SattLineProject.libraries()` reports each effective root once.

- **Literal leaves in a mapping payload.** `iter_literal_leaves` now reads the values of a mapping payload, so the text of a `Time_Value` initializer or parameter mapping is visible with a relation such as `init_value[Time_Value]`.
- **Literal spelling and the JSON view.** `to_jsonable` still emits a literal as its plain number; `span`, `clamped`, and `written` are model attributes for source text and provenance and are deliberately absent from the data view.

- **The module layer option is `ModuleDef.layer_limit`.** The field is renamed from `seq_layers` and narrowed to `float | None`. `Two_Layers_ LayerLimit_ = <real>` is the only layer form a module can write, and the field keeps the written number. What the value does at run time is not established, so the model carries no meaning for it. The unreachable `seq_layers` transformer method, the `SeqLayers` payload, and the named-layer formatting refusal are removed.

- **Projects own an immutable snapshot.** `SattLineProject.load` freezes the loaded trees and `from_programs` deep-copies before freezing, so `project.index` cannot go stale. Attached model nodes reject field assignment, and attached lists and mappings are read-only.

- **Breaking: project declaration validation.** All project validation scopes, including `NONE`, report unresolved declaration type references in every loaded file. `INVOKED` checks executable bodies only for targets and transitively invoked dependency module types.
- **Variable and datatype resolution.** Ordinary modules no longer inherit enclosing variable scopes; frame modules remain transparent. A declared record wins over a builtin transcription of the same name, because the transcription carries field datatypes but no `State`, `Const`, or `OpSave` modifier.

- **Sequence openers must match their closers.** `SEQUENCE` must end with `ENDSEQUENCE` and `OPENSEQUENCE` with `ENDOPENSEQUENCE`; a mismatched pair is now a parse error instead of a sequence whose type and closer disagree.

- **Sibling submodule identity.** A module-type instance is scoped by its module type, and a single module or frame module by kind, so one container may hold them under one label. `SL-V004` now fires only for siblings that share a label and a scope.

- **Source lines count every line terminator.** `SourceDocument.line_col`, the source excerpt every diagnostic renders, and the AST line and column of a plain CR-only document now treat CRLF, LF, and a lone CR as line breaks, the same definition the grammar, the compressed scanner, and `render_ide_text` use. A CR-only document reports the physical line and column of a position instead of keeping every position on line 1.

- **A repeated mapping target keeps its first entry.** `SL-V049` is retired: SattLine accepts one parameter target mapped more than once and uses the first entry. A later entry for the same target is discarded, and neither its source nor its datatype is checked.

- **`SL-V045` covers every string family.** A direct assignment to `IdentString`, `TagString`, `MaxString`, or `LineString` now reports the same finding as `String`: the value is copied with `CopyString` or `CopyVar`. The destination datatype decides, so a destination that does not resolve stays silent. A new fixture writes one assignment per family and keeps the copied form clean.

### Fixed

- **`AnyType` exemptions.** `AnyType` on the actual side of a builtin argument no longer reports `SL-V047`, and an `AnyType` coordinate tail no longer reports `SL-V032`. The type proves nothing about the value, matching the existing exemption for conditions, assignments, operands, and logical operators.

- **AST cache entry cap during a run.** The least-recently-used cap now runs at startup and again every `max_entries // 8` writes (at most 64), so one long process overshoots the cap by at most that many entries instead of leaving the directory at whatever it reached. The run count is documented.

- **A FIFO cache entry answers a miss instead of blocking.** An entry is opened with `O_NONBLOCK` before the regular-file check, so a FIFO named like a cache entry can no longer stall a load or a prune while the open waits for a writer.

- **AST cache identity and directory safety.** The cache key now covers every shipped package file, including grammar sources and `scanner_tokens.json`. Every write revalidates the cache directory, entry files are created `0600`, and an unreadable key or payload is a miss rather than a load failure.

- **Cache maintenance.** The HMAC key is now published atomically, so a concurrent writer reads a complete key instead of a partial one and no writer deletes a key it does not own. The envelope version is part of the entry key, entry file names carry the cache identity so a prune compares names and never unpickles an entry, and the lookup cache enforces its entry cap on every write as well as at startup.

- **Out-of-range literal messages.** `SL-V059` now quotes the numeric literal as the source wrote it, so a normalised `2147483648` is reported as `2147483648` rather than as the stored `2147483647`. `IntLiteral` and `FloatLiteral` expose the written text as `written`. The normalisation to the 32-bit bound is the parser's own; the release does not claim it is what the language stores.

- **A coded source behind a byte-order mark is reported as `coded`.** The CLI strips a leading UTF-8 byte-order mark before classifying the input, the same slice the decoder reads, so `decode --report` and `parse --json` no longer call a marked coded file `plain`.

- **CLI output and exit-code contracts.** A closed stdout now exits `2` instead of `3` or `120`, `diff` reports no count changes when a side does not parse, `graphics` applies the shared `--stdin-name` rule, exits `1` on a scan message, and prints one sentence instead of the expression parser's token dump, and `--max-findings` notes the withheld count once under `--json`.

- **`graphics` enforces the companion size limit before reading.** A companion over 4 MiB is refused as an input problem from its size, so the CLI path cannot read a pathological file that the loader would reject afterwards.

- **A negative `--max-findings` is a usage error.** The cap now validates like the other count flags instead of silently disabling itself; `0` still prints no finding and keeps the exit code.

- **A decode failure and a narrow stdout no longer become internal errors.** A malformed coded stream is reported as one sentence without the library logger's traceback, and a character the output stream cannot encode is escaped instead of raising, so a cp1252 stdout still prints the finding and keeps the content exit code.

- **Closed output pipe on Windows.** A consumer that closes the pipe now stops
  the report with the content exit code instead of reporting an internal error,
  because the Windows `EINVAL` spelling of a closed stream is handled.

- **A raw `DateCode_` prefix keeps its datecode pair in a coded document.** When a digit follows the raw prefix, the lexer keeps `DATECODE_PREFIX` as the keyword half of `DATECODE_PREFIX SL_DATECODE`, so the compact twin of a datecode parses exactly like the plain form.

- **Datatype typo suggestions.** A name that is equally close to two builtin datatypes now gets no suggestion instead of whichever candidate the caller happened to list first. `suggest_datatype_name` returns `None` on a tie, and the declaration is reported as an unknown datatype name.

- **Documentation matches the caches.** The Windows cache paragraph now describes the security-descriptor check instead of claiming there is no owner check, the entry-cap and pruning guarantees state what the code enforces, `sattline_parser.models` is described as internal everywhere, and the README names the three runtime distributions an install receives.

- **Repeated singular clauses are rejected.** A second `Layer_`, `Enable_`, `Module_In_View`, `ZoomLimits`, `Width_`, `ColourStyle`, `ValueFraction`, `Format_String_`, or `ConnectionNode` in one invocation, object, colour block, or text object is now a transformer error instead of silently replacing the first value. Clause keys follow the language fold table, so a mixed-case repeat is the same clause.

- **Equation and sequence name findings carry a span.** `Equation` and `Sequence` now record their declaration span, so `SL-V038` and related name findings point at the declaration.

- **Compressed decoding carries region boundaries out of band.** Marker substitution now runs only on the text between strings, quoted identifiers, and comments instead of splicing placeholders and searching for them again, so a source that spells a placeholder-shaped sequence is decoded as text with linear output growth, cannot inject a protected region, and no longer raises `internal error: unknown placeholder`. Original-source spans and `char_map` are unchanged.

- **Written initializer and description fidelity.** A bare `Time_Value` no longer stores its keyword as the payload text, a bare `Duration_Value` keeps its marker instead of vanishing, a quoted `"Duration_Value"` is read as a literal rather than the keyword, and an empty datatype description is written as `""` instead of being dropped.

- **Formatter interactor and segment fidelity.** Literal interactor body lines stay values, simple interactors keep their coordinate tails, and `SegmentObject` tails are written at the position they were written instead of being duplicated or refused.

- **Formatter and model fidelity.** Two header description comments keep their positions, a root `(Frame_Module)` marker and a frame module's parameter mappings survive, an empty equation is written as its bare header instead of a synthetic `(* empty *)`, a written `Grid = 0.2` is no longer dropped as a default, and `to_jsonable` emits `StrEnum` members as plain values and keeps spans, paths, and byte strings out of the depth limit.

- **Formatter expression precedence.** Parenthesised boolean, comparison, arithmetic, unary, and ternary sub-expressions now round-trip through `format_expr` and `format_source` without changing meaning.

- **Interactor layer lines keep their keyword.** A parsed `Layer_ = 2` body line is stored as a plain `int` rather than the span-carrying `IntLiteral` the token produces, so `format_source` writes `Layer_ = 2` instead of the bare literal `2`, which is a different construct.
- **Reference state suffixes survive formatting.** `ModuleHeader.groupconn` and both sides of a `ParameterMapping` are rendered through the reference formatter, so `P:Old => Q:New` no longer loses its `:Old`/`:New` suffix and reparse no longer clears `VarRef.state`.
- **Mixed colour blocks keep their written order.** A tailed `OutlineColour` written before an untailed `FillColour` is no longer reordered into an untailed group followed by a tailed one.
- **Preserved comments and header lines keep their spelling.** A `CodeComment` continuation line is written verbatim instead of gaining the code indentation, and a header line's doubled inner quote is escaped again so the output reparses.

- **Frame-module parameter mappings.** A frame-module declaration's mapping tail is now validated like a single module's, so a type-incompatible source, a duplicate target, and an absent formal report `SL-V027`, `SL-V049`, and `SL-V048` instead of passing silently.

- **A frozen project tree stays renderable, picklable, and copyable.** The freeze boundary replaces a parsed `Time_Value` mapping with a read-only `FrozenMapping` instead of a `types.MappingProxyType`, so `format_source` writes `Time_Value "1h"` rather than Python dict syntax and a frozen graphics-bearing tree survives both `pickle` and `copy.deepcopy`.

- **The graphics refusal is documented on the public surface.** `GraphicsParseError` and `MAX_GRAPHICS_COMPANION_BYTES` appear in the project surface table together with the rule that an oversized graphics companion raises the error and a smaller one reports `GraphicsMessage` values.

- **IDE layout never splits a quoted identifier.** The line-breaking scan reuses the compressed-source region rule, so a space inside `'a name'` is not a break point and a rendered line is not cut into two tokens.

- **The parser floor no longer imports the validator.** `parse_and_validate` now lives in `sattline_parser.api`, so `source_io` stays parse-only and the documented downward import direction holds.

- **Interactor spelling, colour keys, and `VarName` binding.** `InteractObject.type` keeps the written keyword for every interactor, so `ProcedureInteract` no longer collapses to `ComButProc_`; colour `Width_`/`ColourStyle` clauses are matched through the identifier fold table; and a `VarName` marker binds only the text written immediately before it instead of raising or borrowing an earlier caption.

- **Lark parser cache writes are atomic.** The compiled-grammar cache is serialized to a staging file, flushed, and published with `os.replace`, so a worker never reads a partially written pickle. The file carries a header naming the grammar, start rule, position mode, Lark version, and interpreter version; a truncated, partial, or older-format file is discarded and rebuilt.

- **One line-terminator definition for string boundaries.** CRLF, LF, and a lone CR each end a line in the grammar's string terminals, the compressed-source scanner, the coded decoder, and `render_ide_text`. A CR inside a quoted string is now a syntax error rather than string content, and an unterminated description ends at a lone CR exactly as it does at LF. Line and column numbers still count LF.

- **`load_source_text` strips the byte-order mark before classifying.** A leading UTF-8 byte-order mark no longer hides a coded-stream header, so `load_source_text` and `parse_source_file` agree on the same file.

- **Lookup cache membership is lexical.** A cached resolution is matched against the configured roots by expanded, normalised text rather than by resolving the recorded `base_dir`, so a recorded base outside every configured root is discarded without being resolved, stat-ed, or opened. A planted UNC path in the cache can no longer make a lookup contact it on Windows, and relative, symlinked, and trailing-separator roots still hit.

- **Lookup-cache pruning no longer touches recorded paths.** Startup pruning keeps entries whose shape is usable and never stats a recorded base directory, so a planted UNC path cannot turn a prune into an outbound SMB connection. Resolution validates the base against the configured roots and forgets a foreign entry.

- **Nested `ClippingBounds` values are modelled.** A `ClippingBounds = <values>` annotation written after a coordinate value is kept as a `NestedClipping` on that value, so `format_source` writes every number and every value tail back instead of dropping the annotation. The grouping is exposed as `coord_clippings` on a graph or interact object, `x_clippings`/`y_clippings` on a `PolygonPoint`, `coordinate_clippings` on a `ModuleHeader`, and `corner_clippings` on a `ClippingClause`.

- **Out-of-range numeric literals are reported.** An integer or real literal that exceeds the supported 32-bit range now reports `SL-V059` at its source position instead of being clamped without a finding.

- **Out-of-range numeric literal sentence.** `SL-V059` no longer quotes the clamped value, which could be in range, for a source that wrote a larger number. The finding names the range and leaves the written value to the source span.

- **A parallel `--debug` load keeps a message for every file.** A worker collects a bounded number of parser progress messages and returns them with the outcome, and the parent replays them in plan order. A load with `workers` greater than 1 therefore reports the same per-file progress as a serial one without sending the callback across the process boundary.

- **Parameter-mapping targets.** A target that names no formal parameter is silent, because SattLine keeps an instance mapping after its parameter is removed and the clause has no effect. `SL-V048` now reports only field access on a scalar parameter and a field the resolved record does not declare.

- **Parameter-mapping sources.** A live mapping checks its source in the invoking scope, so an undeclared source variable reports `SL-V019` and an `:Old` or `:New` suffix on a non-State declaration reports `SL-V005` or `SL-V006`. A sequence control accessor such as `StateSequence.Reset` resolves through the program-wide SFC facts.

- **Datecode conflicts compare one unit's own declarations.** A declaration shadows a same-named declaration held by a dependency, so a program and its libraries may carry different revisions without a finding. `SL-V057` now fires only when one unit declares the same name twice with different datecodes.

- **A parse-error excerpt follows the reported line on a CR-only document.** The context window now splits at CRLF, LF, or a lone CR, the rule the reported line and column already use, so the quoted line and the caret no longer span several physical lines.

- **Parser diagnostics name what the source wrote.** An unknown compressed marker reports its offset in the original source rather than in the placeholder text the decoder substitutes, and a comment the grammar rejects is reported as `(*` or `*)` instead of the `*` that the multiplication operator matched.

- **Pool fallback warning.** A load that cannot create a worker pool logs a warning before parsing in the current process, so a silent serial load is visible without `--debug`.

- **A shared dependency is not reported as an unused alias.** A library reached twice, through a diamond or through two targets that share a dependency, read its sidecar on the first visit. `ALIAS_DECLARATIONS_UNUSED` now names only a sidecar at a different prefix, whose declarations really were not read.

- **An alias prefix no longer reads or discards a sidecar.** The planner resolves a body before its sidecar, so a spelling that reaches an already planned body contributes no dependencies and an unreadable file at that prefix cannot fail the load. A sidecar beside the alias spelling is reported as `ALIAS_DECLARATIONS_UNUSED`, naming the file whose declarations were not used.

- **Only regular files are project artifacts.** The stat fallback now requires a regular file, so a directory named like a body can no longer shadow a real body in a later root and a FIFO named like a body is never opened. A unit name is also no longer capped at 20 characters during resolution: the length rule is `SL-V038` at the declaration, so a 21-character unit loads.

- **Companion resolution is one scan per directory and follows language identity.** Graphics, distribution, and the sidecar family probe share a per-load directory index, so a large flat library no longer re-lists its root once per unit and role. A companion stem is compared with `fold_identifier`, the winner among case variants no longer depends on directory order, and a collision is reported with the winner.
- **A companion from the other artifact family is reported.** A `.y` beside a `.s` body, or a `.q` beside a `.s` body, is still never paired, but the load now reports `COMPANION_FAMILY_MISMATCH` so an unavailable `has_executing_system` answer is explained.

- **Project copies at the accepted depth.** `SattLineProject.from_programs` copies and freezes a tree in one iterative pass instead of calling `copy.deepcopy`, so a tree at the depth the parser accepts now attaches: a 249-term expression chain works, where 244 terms used to raise `RecursionError`.

- **Sidecar findings name the affected unit.** A non-fatal sidecar diagnostic is attributed to the library whose artifact is affected, not to each consumer that imported it. A warm lookup also re-stats its hit, and a symlinked body resolves the same way in the warm and cold paths.

- **A folded-name collision keeps both units addressable.** Two loaded units whose names share a casefold key, such as `Straße` and `STRASSE`, both stay in `programs()`: the shared key names no single unit, so each is keyed by its language identity. `get`, `dependencies_of`, `dependents_of`, and the graph now agree, and a declared dependency on either unit no longer retargets at the other.

- **A project load failure names its artifact.** `ProjectLoadError` and its subclasses now carry the failing artifact path and, when the raise site has the source at hand, the text of the failing line. A CLI load finding fills `file` and `source_line` from those fields, so a broken body is reported at its own path instead of a location with no file.

- **A code file the resolver cannot name is reported, not fatal.** Default target discovery and resolution share the identifier rule, so a tree holding a file such as `Pump.v2.s` loads and reports `SKIPPED_FILE` once instead of failing on an unresolvable target.
- **A root that is not a directory stops the load by name.** A file root, a missing root, or a root under a denied ancestor raises `ProjectLoadError` naming that root instead of being treated as an empty root and reporting a missing body.
- **A nested load does not start a second worker pool.** A load constructed inside another load, or running in a process that already belongs to a pool, parses in place and logs that decision once instead of multiplying processes.

- **Module-type recursion follows the referencing unit.** A module-type reference now binds to what the file that holds it can see, so a wrapper library that reuses a dependency's type name no longer captures the dependency's reference and no longer fails the load with a cycle the sources do not declare. A cycle inside the checked unit's own closure is still rejected.

- **Iterative planning and recorded aliases.** Discovery plans with an explicit stack, so a long dependency chain no longer raises `RecursionError` and a 400-unit cycle is reported as a cycle. One body reached under several names keeps every spelling as an alias, so a name `dependencies_of` returns resolves through `get` and every `graph()` endpoint is a node. `invoked_moduletypes` accepts the caller's own key space, including program spellings.

- **Project resolution uses language identity.** An artifact resolves only when its file stem matches the requested name under `fold_identifier`, so a dependency named `STRASSE` no longer loads `Straße.s`. `get` and `__contains__` apply the same rule, two files or two spellings that fold to one project key are reported as `FOLDED_NAME_COLLISION` instead of disappearing, and `LOOKUP_CACHE_VERSION` is bumped because the lookup cache key changed.

- **Linear provenance remapping.** Mapping a position or a span back to the original source now bisects a cached anchor index instead of walking a run of generated characters, so a marker-dense compressed file no longer costs quadratic time to remap.

- **`query --name` compares language identities.** The name filter folds with `fold_identifier` instead of Unicode case folding, so a unit that declares both `Straße` and `STRASSE` returns one row for either spelling rather than both.

- **Record shape provenance.** A record declared in a file with zero fields now has a known shape, so a field access through it reports `SL-V019` instead of staying silent. A datatype name declared twice leaves a field's datatype unproven, so an assignment through it is not type-checked, and a same-named dependency definition no longer marks the file's own record as duplicated.

- **`SetIoAttribute` and a Const argument.** The `Variable` parameter is the object member the call writes, so a `Const` value there no longer reports `SL-V007`. The exemption is per builtin parameter and does not relax the caller-write rule for any other output argument.

- **`SourceDocument` validates its character map.** A map whose real entries leave the original text, repeat an offset, or run backwards now raises `ValueError` at construction instead of producing an inverted or zero-width span. The public constructor is unchanged otherwise.

- **String-literal call arguments.** A string literal is now accepted where the resolved builtin signature documents an `in` parameter of a string datatype, so `LoggedIn("operator")` passes. A literal at a written position (`in var`, `out`, `inout`) and a literal passed to a callee with no known signature are still rejected by `SL-V015`.

- **Transformer rejections are parse failures.** An exception a transformer raises while building the tree is re-raised as its own error instead of Lark's `VisitError` wrapper, so `sattline check` and a project load report a rejected duplicate clause as a parse failure rather than an internal error. A `RuntimeError` stays wrapped and still marks a parser defect.

- **Manual trees past the validation bound.** `validate_basepicture` rejects a tree whose node nesting exceeds `MAX_VALIDATED_DEPTH` (256, the parser's own bound) with `SourceTooDeepError`, instead of letting a recursive expression rule raise a bare `RecursionError`. Parsed input never reaches the bound.

- **Windows cache privacy.** The ACL reader declares its Win32 prototypes, so a
  directory this user owns is recognised as private and the per-user cache is
  enabled again on Windows.

- **Worker error cause.** A parse failure raised in a worker keeps its `OSError` subclass, so a `PermissionError`, `FileNotFoundError`, or `IsADirectoryError` reaches the caller as the cause instead of a `RuntimeError`.

- **A worker's decode failure no longer copies the source buffer.** The failure record keeps the encoding, reason, and position but only the first 64 bytes of the buffer, so a failure on a large file crosses the process pipe as a small record instead of the whole file. The failure's source excerpt is also bounded.

- **Workers no longer touch the AST cache.** A worker process opens the cache through a read-only handle: it does not prune entries, rewrite the identity marker, move an entry's mtime, or write one. A parallel load leaves the cache file set, the marker bytes, and every mtime unchanged.

### Security

- **AST cache privacy boundary.** The cache now holds a directory descriptor opened `O_DIRECTORY | O_NOFOLLOW`, records its `(st_dev, st_ino)`, and performs every entry and key read or write relative to it with `O_NOFOLLOW`. The directory is revalidated before each load and save, so a cache root or `file_ast` directory renamed, replaced, symlinked, or widened after construction is refused instead of written into, and a removed directory is no longer recreated during the run. Every directory above the cache root is checked too: a root under a group-writable or foreign-owned parent disables the caches. The HMAC key is read only through the validated handle.

- **Windows cache privacy.** A cache directory on Windows is trusted only when its security descriptor proves that this user owns it and that its DACL grants write access to nobody else. A foreign write ACE, a missing DACL, a reparse point, or a failed security-descriptor read disables the pickle cache instead of being accepted, and a platform with no privacy check at all is refused.

## [2026.11.7] - 2026-11-17

### Fixed

- **SFC wrappers keep their own name namespace.** A `SUBSEQUENCE`, `SUBSEQSTEP`,
  or `SUBSEQTRANSITION` wrapper may reuse the name of an element inside its own
  body without a false `SL-V021` duplicate-name finding. Sibling step and
  transition names are still checked.

## [2026.11.6] - 2026-11-15

### Added

- **Public AST serializer.** `to_jsonable(value, *, depth=None)` turns any model
  value into JSON-friendly data and `to_json(...)` encodes it, both exported by
  `sattline_parser`. Every dataclass field is emitted under its own name, so a
  new model field needs no serializer change, and `depth` replaces a composite
  value with a placeholder at the limit instead of dropping it. The CLI now uses
  the same functions.

- **Coordinate tails keep their value.** A module header's coordinate tails are
  also grouped in `ModuleHeader.coordinate_tails`, a clipping clause's in
  `ClippingClause.corner_tails`, and a graphics or interact coordinate run in
  the `coord_tails` property key. Each group is index-aligned with the written
  values and holds the same tail objects as the flat view. The flat fields are
  unchanged, so existing readers and validation rules keep working.

- **Interactor property catalogue.** `interactor_property_catalogue` names the
  interactor property spellings the scanner defines but the grammar accepts as a
  generic flag or assignment. `find_interactor_property` classifies one spelling
  and `typed_interactor_properties` reads an interactor's properties in written
  order from either container shape. Parsing and the stored clauses are
  unchanged, and an unknown property still parses as a generic clause.

- **`parse_and_validate` accepts external definitions.** `external_datatypes`,
  `external_moduletype_defs`, and `allow_unresolved_external_datatypes` now pass
  through to `validate_basepicture`, so a single-source consumer with loaded
  dependency definitions does not have to call the validator itself.

- **Dependency cycles follow resolved artifacts.** The planner pushes the
  resolved body identity on its active stack instead of the folded name, so two
  names for one file (a symlink alias, for example) are a cycle even though no
  name repeats, and two units that merely share a spelling are not. The
  diagnostic still reports the logical names that formed the loop, folded.
- **Project identities are named.** `UnitIdentity` (language identity, CP1252
  `fold_identifier`) and `ArtifactIdentity` (filesystem identity, resolved path
  compared with `os.path.normcase`) are exported from `sattline_parser.project`
  so a consumer can apply the same rule as the loader. The project view keeps
  its `str.casefold` registry keys, documented alongside the other two.

- **Project symbol index.** `SattLineProject.index` answers which loaded unit
  defines a name and which loaded units use it. `definitions_of(name)` reports
  program, record, module-type, and variable declarations; `usages_of(name)`
  reports variable references and module-type instances. Names compare
  case-insensitively and the results are stable across runs. `invoked_moduletypes`
  is now exported from `sattline_parser.project` for consumers that want the
  loader's reachability answer directly.

- **SARIF output for code scanning.** `sattline check --sarif` and
  `sattline project --sarif` emit a SARIF 2.1.0 log. A validation finding uses
  its `SL-V###` id as the SARIF rule id and the registry supplies the rule
  descriptor; a parse, decode, project, or read finding keeps its own id. Each
  result carries the severity and, when the finding has one, a file location.
  `--sarif` is exclusive with `--json` and `--jsonl`.

- **Whole-file formatting.** `format_source(picture)` renders a parsed unit back
  to canonical SattLine source, and `format_module(module)` renders one
  `ModuleDef` block. The text parses back to an equal tree for every parsed
  corpus fixture, including graphics and interactor bodies. Each tail is written
  after the value it followed, using the new positional views
  `ModuleHeader.coordinate_tails`, `ClippingClause.corner_tails`, and the
  `coord_tails` property key. A hand-built model that carries a tail without its
  position raises `UnsupportedFormattingError` rather than moving it.

### Changed

- **`corpus --jobs` uses processes.** Each job is independent and returns only
  counts, so the scan now runs in a process pool shaped by the same start-method
  rule as the project loader rather than sharing one cached Lark parser across
  threads. Order and output are unchanged. A pool that cannot start, or one
  whose worker dies, falls back to scanning in this process with a warning.

- **A 21-character declared identifier is a friendly finding.** The lexer accepts
  an identifier of any length, so an over-long name parses and `SL-V038` reports
  it at the declaration with its span, instead of the lexer rejecting the
  twenty-first character as unexpected. A sidecar dependency name is still
  capped at 20 characters, because that name builds a filesystem path.

- **Ctrl-C exits `130`.** An interrupted command now returns the shell
  convention of 128 + SIGINT instead of the usage code `2`, so a script can tell
  a cancelled run from a bad invocation.

- **The loader is four collaborators.** `ProjectLoader` now orchestrates a
  planner (resolve names into post-order plans), an executor (parse bodies and
  own the worker pool and AST cache), an assembler (registry entries and
  companions), and a validator (validation scope and diagnostic aggregation).
  The dependency algorithm no longer shares a module with multiprocessing or
  the registry, and the public `ProjectLoader` behaviour is unchanged.

### Fixed

- **Lookup roots compare as filesystem paths.** Two configured roots that differ
  only in letter case are two roots on a case-sensitive filesystem, so a root
  such as `Library` is no longer collapsed into `library`. Windows path
  comparison stays case-insensitive. Identifier comparison is unchanged and
  still uses the case-folding name table.

- **A boolean parameter mapping value is kept.** `Name => True` was read as the
  optional `GLOBAL` keyword, and `Name => False` as its absence, because the
  keyword and a boolean literal shared the value `True`. The keyword now has
  its own payload, so `True`, `False`, `0`, and `""` all reach the model as the
  written values.

## [2026.11.5] - 2026-11-14

### Added

- **`BuiltinParameter.accepts_const_string`.** The catalogue and the catalogue
  source carry a per-parameter boolean that marks a string-cursor parameter, so
  a Const string is accepted there while the argument is still checked for being
  a reference and for its datatype. Only `GetStringPos` and `SetStringPos`
  declare it.

- **Distribution companions.** The project layer now resolves and parses the
  distribution companion (`.p` draft, `.q` official) beside the selected code
  body. `SattLineProgram` gains `distribution_path`, `distribution`, and
  `has_executing_system`, the last being `None` when no companion was found,
  `False` when the executing-system list is empty, and `True` when it is not.
  `parse_distribution_file`, `parse_distribution_text`,
  `resolve_distribution_companion_path`, `DistributionData`, and
  `DistributionTarget` are public. `sattline project` reports the answer in both
  its text and JSON output, and the JSON program rows gain `distribution`,
  `has_executing_system`, and `executing_systems`. A companion that exists but
  does not parse is a load
  failure, never an empty list, and `check`, `parse`, `query`, `decode`, and
  `diff` refuse a `.p`/`.q` input as a companion rather than reporting it
  as broken source.

- **Parallel project load.** `SattLineProject.load(..., workers=N)` parses
  program bodies in `N` processes, and `sattline project` gains `--workers`
  defaulting to `min(8, cpu_count)`. Discovery resolves the whole closure first,
  so every plan is independent and the result is identical at any worker count:
  a 268-program library tree that takes 255s in one process splits across
  workers without changing the result. The library default stays `workers=1`. A single-threaded caller forks;
  a caller with other threads gets `forkserver`, because forking a threaded
  process is deprecated and can inherit a held lock. A daemonic parent, or a
  pool that cannot start, parses in the calling process instead of failing the
  load.

- **`SourceDocument.char_map`.** The provenance object exposes its per-character
  map as a read-only `char_map` property (`None` for an identity document), and
  `SourceDocument` is importable from `sattline_parser.preprocessing`.

- **`SattLineProject.from_programs`.** A project can be built directly from a
  name-to-program mapping, without a filesystem. This is the public form of the
  private test seam, and it is what makes `cycles()` useful for a hand-built
  graph.

- **Polygon points and text-object geometry reach the AST.** A `PolygonObject`
  keeps every coordinate pair in `GraphProperties["points"]` as a
  `PolygonPoint`, with the tails written after each value attached to that
  value. A `TextObject` keeps `Width_`, `ValueFraction`, and `Format_String_` as
  `TailedClause` payloads, its `LeftAligned`/`RightAligned` markers in
  `alignments`, and its `ConnectionNode` anchor as a `GraphObject`. `PolygonPoint`
  is exported from `sattline_parser.ast`, and the walk visits each new property
  once.

- **Header metadata reaches the AST.** `BasePicture.header_info` is a
  `HeaderInfo` holding the three quoted header lines as written and the optional
  change description as a `CodeComment`. It reads the written syntax version,
  original file date, and program date, and `program_name` remains the
  convenience view over the `name:` field, matched case-insensitively. `HeaderInfo`
  is exported from `sattline_parser.ast` and visited by `walk`.

- **`parse_source_bytes`.** Parses source bytes the caller already read, with the
  same decoding and provenance as `parse_source_file`, and keeps the bytes that
  were parsed in the caller's hands. The project cache uses it to record a
  digest of exactly the revision it stored.

- **`CenterAligned`.** The interactor body accepts `CenterAligned` and stores it
  as `Alignment("center")`, alongside `LeftAligned` and `RightAligned`. The
  spelling is now a reserved identifier keyword, so a declaration that uses it
  reports `SL-V039`.

- **Datatype and record-field query rows.** `sattline query --what symbols`
  reports datatypes and record fields, and variable, parameter, datatype, and
  record-field rows carry the declaration span instead of `line: null`.

### Changed

- **Artifact families no longer mix.** The resolved code body's extension now
  decides the artifact family for the whole unit: a `.s` body pairs only with
  `.l` dependencies, `.g` graphics, and `.p` distribution, and an `.x` body only
  with `.z`, `.y`, and `.q`. Previously the dependency sidecar followed the load
  mode alone, so draft mode could pair a `.s` body with a `.z` sidecar and an
  `.x` body with a `.l` sidecar, and draft bodies fell back to the official
  `.y` and `.q` companions. A sidecar that sits beside the body but in the other
  family is reported as `sidecar-family-mismatch` and is not paired. Code-body
  selection is unchanged: draft mode still prefers `.s` and falls back to `.x`.

- **A caller-supplied cache directory is only used when it is private.** The
  whole root is validated before either cache opens it, and an owned directory
  with group or world permission bits is tightened to `0700`. A directory that
  another user could write to, a symlink, or a read-only location disables both
  caches instead of being followed.

- **Companion extension candidates never cross families.**
  `graphics_ext_candidates` and `distribution_ext_candidates` return only the
  mode's own extension, matching the rule that a body pairs only with the
  companion of its own family. `body_mode` now derives the family from a `.s` or
  `.x` suffix alone, so `resolve_graphics_companion_path("A.s", official)` no
  longer answers `A.y`.

- **`sattline project` caches by default.** A load writes and reads the parser
  caches under `$XDG_CACHE_HOME/sattline-parser/project` unless `--no-cache` is
  given; `--cache-dir` overrides the location. A repeated load of an unchanged
  tree skips parsing: 68s instead of 255s on a 268-program tree. Workers read the
  cache and the parent writes it, so the per-user key stays single-process. The
  directory holds parsed ASTs of the loaded sources and must stay private.

- **Graphics expression spans.** An `Expr` binding is parsed without a padding
  prefix, and its spans are rebased into companion coordinates afterwards. The
  work is linear in the expression length instead of the file offset, so a
  companion with many bindings no longer pays quadratic padding.

- **A loader resolves one load.** `ProjectLoader.resolve()` raises on a second
  call instead of doubling the discovery plans over an existing registry;
  construct another loader for another load.

- **Cheaper parse hot paths.** The post-transform depth check caches a type's
  dataclass fields and checks atomic children against a tuple instead of a
  rebuilt union type, which halves its cost. The contextual lexer reads the
  compact-provenance flag once per run instead of once per token, so an
  uncompressed source skips the keyword retype entirely. `isinstance` checks
  across the parser, transformer, validator, and walker use tuples of types.
  Together these are about 9% of a cold parse.

- **`sattline project` drops `--cycles` and the `cycles` payload key.** A
  recursive dependency chain or a self-instantiating module type is a structural
  load error, so the command reports `cannot load project` and exits `1`; there
  is no cycle list left to print. A JSON consumer that read `cycles` must read
  the error instead. `SattLineProject.cycles()` remains for a directly built
  graph.

- **Recursive projects are rejected.** A `.l`/`.z` dependency chain that
  returns to a program already loading, and a module type that instantiates
  itself directly or through other module types, now raise
  `DependencyCycleError` and `ModuleTypeCycleError` from
  `SattLineProject.load`. Both are structural errors, so `strict=False` and
  `validate=NONE` cannot bypass them. `LoadDiagnosticKind.DEPENDENCY_CYCLE` is
  removed; read the error's `cycle` path instead. `SattLineProject.cycles()`
  remains for a directly built graph, where the loader has not already raised.

- **`Rule.status` replaces the rule flags.** `Rule.implemented` and
  `Rule.retired`, and their constructor arguments, are removed; read
  `Rule.status` (`ACTIVE`, `RETIRED`, `UNIMPLEMENTED`) instead. `to_json()`
  keeps the derived `retired` boolean, so a JSON consumer needs no change.

- **AST surface.** `FlagClause.extra` and `BasePicture.graphics_file` are
  removed, the underscore helpers are out of `sl_transformer.__all__`, and
  `iter_literal_leaves` now also reads scalar `leaf` fields and property-map
  values. It is re-exported from `sattline_parser.models` together with
  `LiteralLeaf`.

- **Sequence layer information.** A `Layer_ = N` on `SEQUENCE` or
  `OPENSEQUENCE` is modelled as `Sequence.layer_info` instead of being
  discarded.

- **`dependents_of` spelling.** `dependents_of` returns each dependent's
  declared spelling, matching `dependencies_of`.

- **Formatting matches source spelling.** `format_expr` renders states as
  `:Old` and `:New` and strings with double quotes and doubled inner quotes, so
  its output parses again. The SFC labels (`Substep`, `EndSubstep`) remain
  display text, not source keywords.

- **Keyword separators are explicit.** An underscore-suffixed keyword such as
  `PRIVATE_` must be separated from the identifier that follows it.
  `DateCode_` is the exception: a digit may follow it in the datecode slot,
  while `DateCode_1` remains a single identifier outside that slot. The
  grammar doc states the rule.

- **Retired rules and identifier resolution.** `DATATYPE_TOO_FEW_FIELDS` and
  `SEQUENCE_REQUIRES_INIT_STEP` are retired because the corpus shows the
  constructs are legal. Datatype lookup no longer falls back to `casefold`, so
  identifiers SattLine treats as distinct stay distinct.

- **The AST cache identifies a source by its bytes.** An entry records the
  SHA-256 of the exact bytes that were parsed. The `mtime_ns` and `size` stat
  snapshot is only a cheap first filter, so an edit that keeps the file size and
  lands inside the filesystem's mtime granularity, or a restore that puts an old
  mtime back, is a miss and the body is reparsed. `FILE_AST_CACHE_VERSION` is
  `11`, and entries from an older version are discarded.

- **Three reserved rules retired.** `DIVISION_BY_ZERO` is disproved by the
  corpus (a valid unit divides by a literal zero, which is runtime semantics),
  and `SEQUENCE_TRANSITION_AFTER_TRANSITION` and `PARALLEL_BRANCH_INCOMPLETE`
  are already covered by the sequence position rules. They are listed by
  `sattline rules --include-retired` as retired.

- **Equation block heading.** `str(ModuleCode)` now prints `Equation blocks:`
  instead of `Equations:`, matching the `equationblocks` field name.

- **The search path is the lookup order.** `SattLineProject.load` and
  `sattline project` search the roots in the order given, and an earlier root
  wins, matching the path list the real tool searches. Requester-relative
  precedence, cluster sorting by branch, and the terminal-root fallback are
  removed, and `ProjectLookup` computes one order instead of one per requester.
  `parse_search_path` reads the `LibA\UnitLib,LibB\UnitLib` notation, and
  `sattline project` gains `--search-path` and `--search-path-base`; positional
  roots and `--search-path` cannot be combined. Because one path order resolves
  every name, one folded name can no longer reach two bodies:
  `NAME_RESOLUTION_CONFLICT` is removed, and a later same-named body is never
  planned, parsed, or validated. `LOOKUP_CACHE_VERSION` is `2`.

- **`ScalarDatatype`.** `Simple_DataType` becomes `ScalarDatatype`, the closed
  set of the language's scalar datatypes. The name says what the enum holds: a
  scalar value, not a record, and not the `AnyType` wildcard, which stays a
  plain string for the type graph to resolve. The members, `from_any`, and the
  normalization behaviour are unchanged; the old spelling is removed, so a
  caller that imported it updates the name. Import it from
  `sattline_parser.ast` or `sattline_parser.types`.

- **Module layout blocks are singular again.** `SingleModule`, `FrameModule`,
  `ModuleTypeDef`, and `BasePicture` store `moduledef` and `modulecode` as
  optional fields. The `moduledefs` and `modulecodes` lists are removed. The
  grammar allows one `ModuleDef` and one optional `ModuleCode` per module body,
  so the lists could never hold more than one entry, and the property views over
  them implied a legacy multi-block shape the language does not have.
  `sattline parse --tree` emits `moduledef` and `modulecode` instead of the two
  lists, the transformer rejects a second block in one body instead of
  overwriting the first, and `FILE_AST_CACHE_VERSION` is `12`, so older AST
  cache entries are discarded.

### Removed

- **`ModuleTypeDef.parametermappings`.** The field is removed. A module type
  definition has no mapping list in the grammar, so the field could never be
  populated; a mapping belongs to the submodule or module-type instance that
  invokes it.

- **Fuzz exports leave the package.** `FuzzResult`, `assert_no_crashes`,
  `assert_no_timeouts`, `collect_corpus_inputs`, `fuzz_harness`,
  `fuzz_parse_text`, `generate_random_text`, `run_corpus_regression`, and
  `run_random_fuzz` are no longer attributes of `sattline_parser`, and the
  modules `sattline_parser.fuzz_harness`, `sattline_parser.parser_fuzzer`, and
  `sattline_parser.decode_fuzzer` are gone. The harness lives in the repository
  under `fuzzing/`; it is not part of the installed package.

- **`sattline project --no-validate`.** The alias is removed; use
  `--validate none`.

- **Lenient project loading.** `SattLineProject.load(..., strict=False)`,
  `ProjectLoader(strict=...)`, and `sattline project --lenient` are removed,
  together with `Diagnostic.tentative` and
  `LoadDiagnosticKind.LOAD_SKIPPED`. A missing or unparseable artifact now fails
  the load, so a project is either complete or not returned, and every
  validation finding is final. The project JSON loses `validation[].tentative`
  and the `load-skipped` value of `diagnostics[].kind`.

- **Interim AST payloads leave the model surface.** `CommonProperties`,
  `ModuleOptions`, `TwoLayers`, `Grid`, `SeqLayers`, `Zoomable`, `ClipValue`, and
  `CoordinateClipping` are transformer payloads, never AST nodes, and now live
  in `sattline_parser.transformer._payloads`. They are no longer defined in
  `sattline_parser.models.clauses` or `sattline_parser.models.tails`, and no
  longer exported from `sattline_parser.ast`.

- **`--fail-on never`.** The alias is removed; `--fail-on` accepts `none` and
  `error`. `never` is now a usage error instead of a synonym for `none`.

- **`sattline query --what definitions`.** The alias is removed; use
  `--what symbols`, which returns the same declaration rows. `definitions` is
  now a usage error.

### Fixed

- **Builtin output arguments are type-checked again.** A `VarRef` in an `out` or
  `inout` position reaches the datatype check, so `CopyTime(Source, IntVar)` and
  `CopyString(Src, IntVar, Status)` report `SL-V047` again. Only the two
  string-cursor parameters keep their `accepts_const_string` exemption, which
  covers the Const-write finding alone.

- **Corrupt cache metadata no longer fails a load.** A cache identity marker or
  lookup cache file that cannot be decoded is treated as an unusable entry and
  replaced on the next write, instead of raising `UnicodeDecodeError` out of
  every load now that the project cache is on by default.

- **Companions pair ignoring filename case.** Graphics and distribution
  companions are found by stem and extension case-insensitively, like code
  bodies and sidecars, so `Pump.S` pairs with `pump.g` and `Pump.S` with
  `pump.p` on a case-sensitive filesystem. `find_companion_beside` is the shared
  helper and is exported from `sattline_parser.project`.

- **Companions cannot be resolved through the ordered roots.**
  `ProjectLookup.find` now raises `ValueError` for `ArtifactKind.GRAPHICS` and
  `ArtifactKind.DISTRIBUTION`. A graphics or distribution companion is anchored
  to the body that owns it, so a root-ordered search could return another unit's
  companion and pollute the source index. Companions are reached only through
  `resolve_graphics_companion_path` and `resolve_distribution_companion_path`.
  Code bodies and dependency sidecars are unaffected.

- **An apostrophe inside an unquoted name is name text.** In a compressed source
  a name such as `Pump'A` no longer opens a quoted-identifier region, so a
  marker between two such names is decoded again and an unknown marker there
  raises `PreprocessError` instead of passing through as literal text.

- **Compressed lexing.** A single-quoted identifier such as `'#84'` is literal
  text, so a marker inside it is no longer expanded or rejected as unknown. A
  description that ends at a line break no longer shields the following lines
  from marker expansion. `load_source_text` expands markers inside a coded
  stream instead of returning them undecoded.

- **The default cache location degrades instead of crashing.** A relative
  `XDG_CACHE_HOME` is ignored rather than placing the cache inside the tree the
  command runs in, and a home directory that cannot be determined disables the
  cache instead of raising `RuntimeError`.

- **A deeply nested graphics expression becomes a message.** The binding
  scanner catches a recursion failure while rebasing spans, so an over-deep
  `Expr` payload returns a `GraphicsBinding` plus a `GraphicsMessage` warning
  instead of raising `RecursionError` out of `parse_graphics_text` and out of a
  project load.

- **Numeric literals in a graphics expression carry companion spans.**
  `IntLiteral` and `FloatLiteral` are `int` and `float` subclasses, so the span
  rebase used to skip them; an `Expr` binding now reports every leaf in file
  coordinates.

- **The module-type cycle check compares definitions, not names.** A cycle is a
  node per owning program and folded type name, so two libraries that reuse a
  type name no longer look recursive, and a library that shadows a dependency's
  name loads. A reference resolves to the referencing file's own definition
  first, then to any definition in the checked program's closure. The error
  names the program that owns the first node of the cycle.

- **`#;>` decodes as `Non_Zoomable`.** Scanner ordinal 190 was missing from
  `scanner_tokens.json`, so a coded library body that spells the argument failed
  to preprocess with `Unknown compressed marker '#;>'` and was skipped whole.
  The ordinal sits between `Cancel_Variable` (189) and `LayerLimit_` (191), and
  a coded invocation spells it where the uncompressed siblings spell
  `Non_Zoomable` after the five invocation coordinates. The code had been
  dropped from an earlier seed table because its entry there read `Zoomable`,
  which is already ordinal 106.

- **A parse pool that cannot start falls back.** `ProcessPoolExecutor` starts
  its workers on the first submit, so a denied fork, an exhausted process limit
  or a missing worker start method surfaces from `map`, not from the
  constructor. That failure is now handled like a broken pool: the load logs it
  and parses in the calling process, as the parallel-load documentation already
  promised.

- **Project cache integrity.** The Lark parser cache now validates the
  per-user directory under the temporary directory as well as the `lark-cache`
  child, so a pre-created parent cannot be used to replace the signed cache
  entry. A symlinked cache directory now disables caching instead of being
  followed. The AST cache records the source snapshot taken before the parse,
  so a body edited while a worker was reading it is not stored as current, and
  a warm load no longer rewrites entries it read. A warm lookup resolves the
  cached base through the same case-insensitive index as a cold scan, so a
  dependency spelling whose case differs from the file name no longer falls
  through to a coarser extension.

- **Project errors survive pickling.** `DependencyCycleError`,
  `ModuleTypeCycleError`, and `DistributionParseError` keep their fields across
  a process boundary, so a load or a companion parse that runs in a worker can
  return its error unchanged.

- **Project scope fixes.** A datecode conflict now names only the visible
  versions that differ from the program's own, so a closure holding versions 1
  and 2 no longer hides the conflict on a program that declares 1. Invoked
  validation resolves a module-type reference inside the referencing program's
  dependency closure, so a same-named type in an unrelated library is no longer
  validated. Module-type recursion is rejected at the first cycle found instead
  of enumerating every elementary cycle.

- **Family mismatch is reported in every mode.** A sidecar that sits at the
  body's prefix but in the other artifact family is probed for directly, so
  `--mode official` over `Main.x` beside `Main.l` reports
  `sidecar-family-mismatch` instead of a plain `sidecar-missing`.

- **Parsing works when the grammar cache is unusable.** With no private Lark
  cache directory the parser used to build with `cache_grammar=True` and no
  cache path, which Lark rejects, so every parse failed. The parser now builds
  without grammar caching in that case.

- **Argument and guard checks.** `accepts_const_string` now exempts only the
  Const-write finding for a string-cursor parameter: `GetStringPos` still
  rejects a non-reference argument (`SL-V014`) and a wrong datatype (`SL-V047`).
  An SFC transition guard is now checked like an IF condition, so
  `WAIT_FOR 123` reports `SL-V030`.

- **Record descriptions and frame datecodes.** A record without a description
  now reports `None` instead of the `RECORD` keyword token, and a frame module
  datecode is an `int` or `None` instead of `True`. Both values previously
  survived into the AST cache, so a cached tree could carry the wrong type.

- **Declared builtin record types.** `ComliMessage`, `ByteRecord`, and
  `PidType` are declared, so sources that use them validate and calls to the
  builtins that take them can satisfy the argument-type rule. The catalogue
  generator now rejects any datatype that is not a scalar, a declared record,
  or `AnyType`.

- **CLI contract fixes.** `--what definitions` returns symbols only, `--paths
  absolute` applies to every path in every command that accepts it, `--fail-on
  none` exits 0 for load skips, and companion content on stdin is refused like a
  companion path.

- **Unspaced binary operators.** `X = 1+2` and `X = 1-2` now parse like their
  spaced forms. A numeric literal only takes its sign when the sign starts an
  operand, so the operator is no longer swallowed by the literal.

- **Bounded, fresh project caches.** The AST cache drops entries whose source is
  gone, caps its entry count, and fingerprints `source_io.py`,
  `source_document.py`, and `names.py`, so a decoding or folding fix invalidates
  older trees. The lookup cache prunes abandoned temp files and caps entries,
  and a cache read never creates the signing key.

- **Companion safety and family reporting.** A companion must be a regular file,
  an oversized `.p`, `.q`, `.g`, or `.y` companion is refused instead of read,
  a graphics expression failure stays a `GraphicsMessage`, and
  `ProgramFormat.mode` reports the family of the body that was loaded.

- **Dependency containment.** A dependency name containing `/`, `\`, or `..`, or
  resolving outside its base, is refused, and companion lookup requires a
  regular file. A deleted body is reported as missing rather than as a parse
  failure.

- **Same-named units in different roots.** The loader keys plans by resolved
  path, so a second root's `Util.s` is no longer served the first root's body.
  When one folded name resolves to two bodies, a `NAME_RESOLUTION_CONFLICT`
  diagnostic names both, and datecode conflicts no longer depend on the order
  of the requested targets.

- **Tentative findings are per finding.** A purely local diagnostic is no
  longer marked tentative because an unrelated dependency failed to load. Only
  a finding whose resolved module type or datatype came from an incomplete
  dependency is tentative.

- **Source decoding and error details.** A UTF-8 BOM is stripped before
  decoding, `ParseErrorDetails.source_line` follows the same `\n` line
  numbering as `line` and `column`, an unterminated nested comment is refused,
  and expected-token labels no longer leak internal `_NOTAIL` terminal names.

- **Distinct, construct-specific diagnostics.** Each comparison operand finding
  carries its own span and names the operand, `SL-V058` is tested and scoped to
  the validator that emits it, and a `SUBSEQTRANSITION` body that opens with a
  step reports `SL-V054` rather than an alternative-branch code.

- **Parameter mappings on a plain submodule.** A mapping on a `SingleModule` is
  checked like the same mapping on a module-type instance, and `SL-V048` now
  reports a mapping target that is not a declared parameter. An unknown module
  type still reports duplicate mapping targets.

- **Validation scope fixes.** Frame modules are checked like single modules,
  a local definition wins over an external one of the same name, `Const`
  propagates through dotted writes and builtin output arguments, `AnyType` is
  accepted in conditions and ternary branches, and every definition of a
  duplicated datatype name is validated.

- **`sattline check --rule` only accepts ids that command can produce.**
  `PARSE_ERROR` and `DECODE_ERROR` remain valid, and a synthetic id that belongs
  to another command, such as `READ_ERROR`, is now a usage error instead of a
  filter that silently matched nothing.

- **`DateCode_1` parses without a separator.** The datecode prefix is the one
  keyword a digit may follow directly, because the rule after it starts with a
  number. A letter or underscore still blocks the keyword, so
  `PRIVATE_MODULEDEFINITION` stays one name and `Enable_1` is still a variable.
  Outside the datecode slot, `DateCode_1` is a single identifier.

- **Mapping sources and record fields are checked.** A parameter mapping whose
  source is not a declared variable now reports `UNDEFINED_VARIABLE` at the
  mapping span. A dotted mapping target resolves through the record's fields, so
  a boolean field mapped from an integer source reports the type mismatch. A
  field that a record declared in the same file does not carry reports
  `UNDEFINED_VARIABLE` for a read and for a write, with nested paths resolved one
  step at a time. A field on an opaque builtin record, an unloaded external
  record, or a record name declared more than once stays silent, and a temporal
  value reached through a record still exposes its component accessors.

- **`sattline project` no longer logs a parser traceback.** A body that fails to
  parse is reported once, as the structured `PROJECT_LOAD_ERROR` finding, with
  nothing on stderr. `--debug` still prints the loader's progress and the
  parser's traceback.

- **`sattline parse` and `sattline diff` count the whole module tree.**
  Sequences, equation blocks, graph objects, interact objects, local variables,
  submodules, and module types inside nested submodules and module-type bodies
  are included, so the summary agrees with a `walk` over the picture. A change
  inside a nested body is now visible to `diff`.

- **An unreadable project root is an input error, not an internal error.**
  `sattline project` exits `2` with `cannot read ...` instead of exiting `3` on a
  `PermissionError`, and the library raises `ProjectLoadError` rather than
  letting the `OSError` escape.

- **An untranscribed builtin parameter list no longer means zero arguments.**
  `GetPrivilegeFlag` and `ResetPrivilegeFlag` recorded `typed: false` with an
  empty parameter list, which the validator read as arity `0..0` and rejected
  every real call with `SL-V013`. An untyped catalogue entry now records `arity`
  explicitly: `null` means unknown, so a call to such a name is not arity or
  argument checked, and an integer pins both bounds to that count. The generator
  rejects an untyped entry that omits the field and an `arity` on a typed
  entry.

- **AST cache eviction follows last use.** A successful load touches its entry,
  the cap is configurable through `FileASTCache(max_entries=...)`, and a
  symlinked entry is ignored instead of read.

- **The parse pool no longer forces `fork` on every Linux host.** `fork` is
  used only on Linux before Python 3.14 with no other Python thread, and the
  platform default applies on macOS and newer Linux runtimes.

- **Bounded process and thread counts.** `sattline project --workers` accepts
  1 to 32 and `sattline corpus --jobs` accepts 1 to 32; a larger value is a
  usage error instead of a request that can exhaust the machine.

- **`sattline project --graph` reports validation findings.** Graph mode prints
  the validation rows and includes them in its JSON payload, so a run no longer
  exits `1` on a finding it did not show. `--of` with a name outside the loaded
  graph is a `PROJECT_QUERY_ERROR` finding instead of an empty graph.

- **Unknown SFC accessors are reported.** Only the runtime field names an
  element kind exposes are treated as accessors: `X`, `Hold`, `Reset`, and `T`
  for a step, and `Hold` and `Reset` for a sequence. A suffix such as
  `Step.Foo`, or `Sequence.X`, is now an undefined reference instead of an
  unchecked dotted name. Availability still comes from `SeqControl` and
  `SeqTimer`, which `SL-V051` reports separately.

- **Worker parse failures keep their cause.** A body parsed in a worker now
  rebuilds the same exception type and source position in the parent, so a
  broken dependency has the same `__cause__` at any worker count.

### Security

- **Dependency names are validated as SattLine identifiers.** A `.l`/`.z` line
  must be a unit name of at most 20 characters, so a drive-qualified name,
  path separator, parent reference, control character, Windows device name, or
  invalid filename character cannot resolve outside the search roots.

## [2026.11.4] - 2026-11-05

### Added

- **AI workspace tooling.** A repo-local `sattline-parser` skill, `/verify`,
  `/release`, and `/review` commands, a read-only `parser-reviewer` subagent,
  and a pull request template. The skill carries the map, invariants, recipes,
  and verification ladder so `AGENTS.md` can stay short.

- **Annotation-tail traversal.** The public walker now descends into
  `GraphObject.properties`, `InteractObject.properties`, and
  `ModuleDef.clipping`, and emits the typed clause and tail payloads
  (`EnableClause`, `ColourSpec`, `TailedClause`, `AssignClause`, `FlagClause`,
  `ProcedureCall`, `PickButton`, `ScaleSelector`, `VarTail`, `LitStringTail`).
  Property keys are visited in a documented order, and a tail shared with the
  flat `properties["tails"]` view is emitted once through its owning clause.
- **Annotation-tail validation.** Expression tails in headers, graphics,
  interact objects, and module layout are checked for undefined variables
  (`SL-V019`). An `Enable_` expression tail must be boolean (`SL-V030`), and
  `ModuleDef` coordinate tails keep `SL-V032`. Bound `InVar_`/`OutVar_` names
  stay undiagnosed.
- **Annotation-tail references.** `sattline query --what references` reports
  variable uses in header and object annotation tails. Bound tails appear with
  detail `unresolved`; text-object `VarName` and `IntObjPickButton` references
  are reported too.

- **`sattline_parser.ast`.** The whole AST model is now a supported import surface. Every node, clause payload, tail, `SourceSpan`, and the walker (`walk`, `iter_child_nodes`, `NodeVisitor`, `WalkEvent`) is re-exported from one module, so a consumer no longer imports from the `models` submodules. The class names remain importable from `models.ast_model` and `models.expressions`, but `sattline_parser.ast` is the documented path.
- **`MappingSource`.** `ParameterMapping.source_type` is a `MappingSource` value, `VARIABLE` or `VALUE`, instead of a bare string that reused tree-tag and property-key constants.

- **Public AST traversal.** `sattline_parser` now exports `walk`, `NodeVisitor`, `WalkEvent`, and `iter_child_nodes`, so a consumer can traverse the model in a supported way instead of importing `cli._ast_walk` or copying the recursion. The walk is pre-order, reports each node's relation and ancestor chain, and documents which attached fields it does not descend into. `sattline query` and the validator's variable-reference collection are rebuilt on it.
- **Validation rule registry.** Every `DiagnosticCode` now has one `Rule` in `validation/rules.py` with an id, enum name, scope, status, summary, and optional details. Retired and reserved codes are recorded rather than inferred, the rules table in `docs/validation.md` is generated from the registry, and `sattline rules` lists it. `check --rule` accepts an `SL-V###` id or an enum name and rejects an unknown or inactive rule instead of returning an empty report.

- **Docs CI.** `scripts/check_docs.py` checks relative links and dash
  punctuation and extracts Mermaid blocks. `.github/workflows/docs.yml` renders
  every diagram with `@mermaid-js/mermaid-cli` 11.17.1.

- **`docs/`.** A complete internals documentation set covering the layer model,
  parse pipeline, grammar and lexer, source provenance, AST, transformer,
  validation, project loading, graphics companions, CLI, builtins, testing, and
  development workflow. Each subsystem has a Mermaid diagram of how it fits
  together, and `docs/README.md` states the language-infrastructure boundary.

- **Layout metadata.** Every `SourceSpan` field, plus the geometry fields `BasePicture.position`, `Sequence.position`/`size`, `Equation.position`/`size`, `ModuleHeader.invoke_coord`, and `ClippingClause.bounds`, carries `metadata={"layout": True}` and is excluded from equality. A test classifies every `SourceSpan` field and pins the geometry set, so a consumer can drop the marked presentation fields when comparing two revisions.

- **Payload source spans.** `VarTail`, `LitStringTail`, `InteractObject`, `ModuleDef`, and the stored clause payloads (`EnableClause`, `ModuleInViewClause`, `AssignClause`, `FlagClause`, `TailedClause`, `ColourSpec`, `ClippingClause`, `PickButton`, `ScaleSelector`, `ProcedureCall`, `ModuleMarker`, `ZoomLimits`, `ModuleArguments`, `Alignment`) carry a `span`. `VarTail.bound_name` returns the written name for a string or `LitString` value and `None` for a numeric or boolean value. Spans are layout metadata and are excluded from equality.

- **`sattline_parser.types`.** Scalar type families, literal inference, datatype normalization, dotted-name splitting, and record field resolution are now a supported import surface, so a consumer no longer reaches into `validation.typing`. Expression typing that needs a validation scope stays internal.
- **`sattline_parser.formatting`.** The formatting helpers (`format_expr`, `format_list`, `format_optional`, `format_seq_nodes`) are documented as a public surface instead of a private import path.

- **Parse benchmarks.** `benchmarks/` uses pytest-benchmark for parse,
  validation, and walk timings, and CI uploads the JSON results.

- **Python 3.14.** Classifiers and the CI matrix cover 3.14 in addition to 3.12
  and 3.13.

### Changed

- **`AGENTS.md`** now records the documentation index, the language-infrastructure
  boundary, and a rule that `docs/` must be updated with the behavior it
  describes.

- **Façade layering.** `sattline_parser.api` no longer imports
  `sattline_parser.project`. The graphics entry points
  (`parse_graphics_file`, `parse_graphics_text`,
  `resolve_graphics_companion_path`) moved from `api.__all__` to
  `sattline_parser.__all__`, so the documented surface keeps every name while
  `api` now depends only on `source_io`, `errors` and `validation`.

- **AST cache format.** `FILE_AST_CACHE_VERSION` is now 9. The model no longer carries `parse_tree`, `ModuleCode.equations` is now `equationblocks`, and the earlier phases reshaped `source_type`, the payload spans, the reference leaves, the header arguments, and the clipping clause, so an older cache entry is discarded instead of being decoded into the current model.

- **AST surface documentation.** `docs/ast.md` points at `sattline_parser.ast` as the traversal door, spells out the two-case reference collector (`VarRef` plus bound `VarTail`), and labels `GraphicsBinding` as a project graphics value rather than a walker node. `GraphicsBinding` is also exported by `sattline_parser.project`.
- **CLI dogfooding.** The parser's own CLI imports the model and walker from `sattline_parser.ast`, so the public door is exercised by the `sattline` command.

- **AST walker.** `walk` now uses an explicit stack and a persistent ancestor chain. A manually built deep AST no longer exhausts the Python call stack, and `WalkEvent.parents` expands its sequence view only when read, so the walk itself is linear. Each `parents` read costs O(depth), and the field still behaves like a tuple for indexing, iteration, equality, and `len`. `NodeVisitor` dispatch remains recursive and is bounded by the parsed-structure depth limit.

- **`On`/`Off` are boolean literals.** `On` and `Off` are now equivalent to `True` and `False` everywhere `BOOL` is accepted, including the invocation-header and graphics property readers. The separate `ON_KW` and `OFF_KW` terminals are removed. Declarations named `On` or `Off` now fail at parse time; `SL-V034` remains a validator backstop for constructed ASTs.

- **`ModuleCode.equationblocks`.** The list of `Equation` nodes is renamed from `equations` to `equationblocks`, and the `sattline parse` summary count key is renamed to match. `Equation.kind` still records the written keyword as `"equationblock"` or `"equations"`.
- **Unit documentation.** The README, docs index, project document, and glossary now state that a SattLine program or library is one unit made of three files: the code body, the dependency sidecar, and the graphics companion. The `sattline diff` examples compare the official `.x` code body with the draft `.s` code body of that one unit.

- **Grammar constants.** Every constant is `Final` and exported through `__all__`, the keyword and boolean regexes are derived from the spelling constants, and the unused constants, the unused `New`/`Old` terminals, and the dead `variable_name` branches are removed. Guard tests check `__all__`, `Final` coverage, duplicate literal values, orphan constants, and that the grammar resolves.

- **Grammar templating.** `sattline.lark` placeholders are substituted by name
  instead of through `str.format`, so a literal brace such as a regex
  quantifier (`{2,3}`) is written as it reads and no longer has to be doubled.
  An unknown placeholder now fails with an explicit error instead of reaching
  Lark.

- **Graph-object enable tail.** `GraphObject.properties` keeps the `Enable_`
  tail in the new `enable_tail` key alongside the resolved `enable` boolean.

- **Invocation arguments are a stored payload.** `ModuleHeader.arguments` is a `ModuleArguments` value holding the layer, `Enable_`, `Module_In_View`, zoom limits, marker arguments, and `Name = value` assignments. A header assignment such as `Param1 = 5` is now retained instead of being reduced to its tail. `invoke_coord_tails` holds only the tails attached to the five invocation coordinates, and the old singular header names are read-only views over `arguments`.

- **Typed interactor bodies.** `InteractProperties.body` is now a closed union of typed payloads (`AssignClause`, `EnableClause`, `FlagClause`, `TailedClause`, `ColourSpec`, `PickButton`, `ScaleSelector`, `Alignment`, `Tail`, `int`, and `CodeComment`) instead of raw Lark trees. A `LeftAligned`/`RightAligned` line is an `Alignment`, a comment inside a body is a `CodeComment`, and `interact_body_payloads` is gone. The model layer no longer imports Lark.

- **`ModuleDef.clipping`.** The resolved `ClippingBounds` corners and the tails attached to them are one `ClippingClause` on `ModuleDef.clipping`. `clipping_bounds` and `clipping_tails` are read-only views over it, and `ModuleDef.properties` and `ModuleDefProperties` are removed.

- **Release policy.** Superseded names, fields, and aliases are removed in the
  same breaking release. There is no deprecation window, and the changelog no
  longer has a Deprecated section type.

- **`opencode.json`** now pins the Pyright LSP to Python files, formats Python
  with the project Ruff, blocks direct edits to generated files, and asks before
  push, merge, tag, and publish actions.

- **`parse_source_text` documentation.** The main entry point now documents the preprocess, parse, remap and transform stages, and failure logging.

- **`parser-reviewer` shell helpers.** The read-only review agent now allows `echo`, `head`, and `git branch --show-current` inside multi-segment inspection commands, so a snapshot one-liner no longer fails on a harmless echo segment. Every other shell command stays denied.

- **README scope section.** The public README now states the package's
  responsibilities and its non-responsibilities up front, and links to `docs/`.

- **References are modelled as `VarRef`.** `GraphProperties["text_vars"]` is a `list[VarRef]`, and `PickButton.is_reference` is replaced by `PickButton.reference: VarRef | None`. `walk` now yields every text-object and pick-button reference as a `VarRef`, so `sattline query --what references` reports them as ordinary references instead of labelled special cases.

- **Deep source nesting.** `parse_source_text` now rejects a structure deeper than `MAX_SOURCE_DEPTH` (256 levels, exported as a public constant) with `SourceTooDeepError`, a clean parse failure instead of a `RecursionError` escaping from the transformer, validator, formatter, or dataclass `repr`. The check follows dataclass fields, containers, and raw grammar trees, so interactor property payloads are covered too. The parse tree is transformed and remapped without recursion, comment token flattening is iterative, and `RecursionError` from a parser, transformer, or Lark `VisitError` wrapper is converted to the same clean error. `SourceTooDeepError` subclasses Lark's `UnexpectedInput`, so the CLI, project loader, fuzz harness, and Atheris targets classify it as invalid input.

- **Typed tail and clause nodes.** Coordinate, header, and property tails are
  modelled as frozen dataclasses instead of bare strings, dicts, and Lark
  trees: `VarTail(direction, value)` for `InVar_`/`OutVar_` bindings,
  `LitStringTail` for quoted symbols, and typed clause payloads such as
  `EnableClause`, `AssignClause`, `TailedClause`, `ColourSpec`,
  `ProcedureCall`, and `ModuleArguments`. `ModuleHeader.enable_tail`,
  `ModuleHeader.invoke_coord_tails`, and `ModuleDef.clipping_tails` now hold
  these nodes, and the graph and interact property maps are `TypedDict`
  definitions. Consumers that compared tails to strings or read `properties`
  as an untyped dict need updating.

- **Walker contract.** `WalkEvent` now carries `field`, `indices`, and `phase`. `walk(..., emit_leave=True)` emits a matching leave event after each subtree, and `NodeVisitor` dispatches `leave_<ClassName>` after each enter method. Every dataclass field is declared in `_FIELD_SPECS` as a child, a node-or-literal, a property map, or a leaf, and a test compares the declaration with `dataclasses.fields`. Literal values have an explicit reader, `iter_literal_leaves` / `LiteralLeaf`, instead of an `include_literals` walk option.

### Removed

- **AST compatibility fields.** `BasePicture.graphics_bindings`,
  `graphics_messages`, `graphics_composite_records`,
  `graphics_composite_occurrences`, `graphics_picture_display_records`,
  `graphics_picture_display_occurrences`, and `library_dependencies` are
  removed. Graphics data lives on `SattLineProgram.graphics`.

- **Compatibility shims.** `SEED_MAPPING`, the `_ModulesMixin` wrapper,
  `assignment_is_compatible`, and the unpickling fallbacks for older AST
  payloads are removed. `SCANNER_TOKENS` is the only token table name.

- **`create_sl_parser`.** The compatibility alias is gone from `source_io`,
  `api` and the package root; `create_parser` is the entry point.

- **`errors._unexpected_input_summary`.** Unused outside the tests. Call
  `describe_parse_error` for a rendered sentence, or the internal
  `_unexpected_description` for its parts.

- **The retained parse tree is gone.** `BasePicture.parse_tree`, `BasePicture.__getstate__`, and the `retain_parse_tree` parameter of `parse_source_text`, `parse_and_validate`, and `parse_source_file` are removed. The parser returns the model only; use `create_parser().parse(...)` when you need the raw Lark tree.

- **Validation rule severity.** Validation diagnostics are always errors, so `DiagnosticSeverity`, `Diagnostic.severity`, `Rule.severity`, the registry severity column, the `severity:` line in `sattline rules`, and the `severity` field in `sattline rules --json` and in `sattline project --json` validation rows are removed. `check --severity`, the `warning` alias for `--fail-on`, `--fail-on any`, and the warning buckets in `check`, `project`, and `corpus` output are removed with them. Graphics scan messages keep their `error` and `warning` severity.

- **Singular module block fields.** `SingleModule`, `FrameModule`,
  `ModuleTypeDef` and `BasePicture` no longer store `moduledef` and
  `modulecode`. The names remain as read-only properties returning the last
  entry of `moduledefs` / `modulecodes`, so reading them still works and the two
  views cannot disagree. Construction through the singular keyword arguments,
  assignment to the properties, and the corresponding `moduledef` /
  `modulecode` keys in `sattline parse --tree` output are removed; use the
  block lists instead.

### Fixed

- **Dependency cycle identity.** Cycles are deduplicated by directed node
  sequence, so `a -> b -> c -> a` and `a -> c -> b -> a` both appear. Rotations
  of the same cycle still collapse, and the project view and CLI report the real
  edge order.

- **Multi-block identifier checks and counts.** Declaration identifier
  validation and the `parse` / `diff` structural counts now cover every
  `ModuleDef` and `ModuleCode` block instead of only the last one.

- **Numeric coordinate tails.** A literal tail such as
  `ClippingBounds = ( -1.0 : 2.5 , -1.0 ) ( 1.0 , 1.0 )` is recorded as a tail
  instead of being read as the next coordinate value.

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
  `"schema": "sattline.v1.<command>"`. Exit codes are the contract: `0` clean,
  `1` findings, `2` usage/input, `3` internal. A traceback is only printed
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

- **Source files are now decoded strictly as Windows-1252 (cp1252)**, the only
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
  lookup: a directory that merely *contains* libraries is refused with
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
  load errors (`ProjectLoadError` and subclasses). Additive only; artifact
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
