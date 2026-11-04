# Glossary

## Language and files

| Term | Meaning |
| --- | --- |
| SattLine | The PLC programming language and file format this package reads. The name is used only to describe the format. |
| BasePicture | The root AST node for one parsed source unit. It is also the name of the root module in the grammar. |
| Module | A nested executable unit. `SingleModule` has a body; `FrameModule` is a pure container; `ModuleTypeInstance` references a named type. |
| Module type | A reusable module definition (`ModuleTypeDef`) that instances reference. It may be declared in this file or in a dependency. |
| ModuleDef | The layout and graphics section of a module: clipping bounds, grid, layers, graph objects, interactor objects. |
| ModuleCode | The executable section: sequences and equations. |
| Sequence | An SFC program unit. It contains steps, transitions, alternatives, parallels, and subsequences. |
| Equation | A statement block introduced by `EQUATIONBLOCK` or `EQUATIONS`. |
| SFC | Sequential function chart. The step and transition model used by a `Sequence`. |
| Program | In this package, one loaded source artifact (one `.x` or `.s` file). Not one top-level executable program. |
| Artifact | A file the project layer can resolve: a code body, a dependency sidecar, or a graphics companion. |
| Target | A program name passed to `SattLineProject.load`. Its closure is loaded. |
| Root | A directory the project layer searches. Each root is a library. |
| Sidecar | A `.l` / `.z` file that lists a program's declared dependencies. |
| Companion | A `.g` / `.y` graphics file paired with a code body. |
| Datecode | A numeric version attached to a module type or datatype. The parser preserves absence; it never invents one. |
| Draft | `.s` code, `.l` dependencies, `.g` graphics. |
| Official | `.x` code, `.z` dependencies, `.y` graphics. |

## Grammar and parsing

| Term | Meaning |
| --- | --- |
| Terminal | A lexer token, such as `NAME`, `REAL`, or `SEMICOLON`. |
| Rule | A parser production, such as `sequence` or `variable_group`. |
| Contextual lexer | A Lark lexer that selects accepted terminals from the current parser state. |
| SattLineLexer | The custom contextual lexer that models nested comments. |
| Extra | A terminal Lark can accept between any two tokens, such as whitespace. |
| LALR | The parser algorithm Lark uses here. It is deterministic and table-driven. |
| Priority | A terminal precedence, used by the `NOTAIL` tokens. |
| `NOTAIL` | A value terminal with a negative lookahead so a trailing `:` is not consumed as part of the value. |
| Opaque region | A string literal or `(* ... *)` comment that the decoder must not rewrite. |
| Marker | A compact `#NN` code in a compressed source. |
| Coded stream | A binary-framed source with header `\x80 3.1`. |

## Provenance

| Term | Meaning |
| --- | --- |
| Original source | The text or bytes the caller supplied, before any decoding. |
| Normalized text | The decoded text the Lark parser sees. |
| Source document | A `SourceDocument`: original text, normalized text, and the map between them. |
| Character map | `SourceDocument.char_map`, one entry per normalized character. |
| `GENERATED` | The sentinel for a normalized character with no exact original offset. |
| Anchor | The nearest preceding real source offset used for a generated character. |
| Remap | Rewrite a position from normalized to original coordinates. |
| Span | A half-open `[start, end)` range plus one-based line and column. In this package, `SourceSpan`. |

## AST

| Term | Meaning |
| --- | --- |
| `SLTransformer` | The Lark transformer that builds the AST. |
| Mixin | One responsibility module of the transformer. |
| `CodeComment` | A preserved `(* ... *)` comment with its role and span. |
| `SLExpression` | The union of every expression node. |
| `SLStmt` | The union of statement nodes. |
| `CodeItem` | A statement or comment inside a code list. |
| `SFCBodyItem` | An SFC node or comment inside a sequence body. |
| `VarRef` | A variable or dotted field reference, optionally with `:Old` or `:New`. |
| `BinOp` | A binary arithmetic node. Chains fold left. |
| `BoolOp` | An n-ary `OR` or `AND` node. |
| `TernaryOp` | An expression-context `IF`/`ELSIF`/`ELSE`/`ENDIF`. |
| `IfStmt` | A statement-context `IF`/`ELSIF`/`ELSE`/`ENDIF`. |

## Validation

| Term | Meaning |
| --- | --- |
| Diagnostic | One validation finding: code, message, span, tentative. It is always an error. |
| Rule code | A stable `SL-V###` identifier. |
| Severity | A CLI finding field: `error` for validation and parse findings, `warning` for graphics scan messages. |
| Tentative | A finding that depends on a part of the closure that failed to load. Set by the loader, never by the validator. |
| Scope | A chain of variable declarations: module parameters and locals, then enclosing modules. |
| Type graph | A case-insensitive map from record datatype to its fields. |
| Builtin record | A record datatype whose fields come from `builtins/records.py`. |
| Retired code | A diagnostic id no longer emitted because the rule was disproved. The id stays reserved so it cannot be reused. |
| `INVOKED` | Validation scope: targets in full, dependencies only for the module types a target invokes. |
| `FULL` | Validation scope: every loaded program. |
| `NONE` | Validation scope: parse only. |

## Project layer

| Term | Meaning |
| --- | --- |
| `SattLineProject` | The loaded registry and derived dependency graph. |
| `SattLineProgram` | One loaded source artifact with its code, graphics, dependencies, and diagnostics. |
| `DependencyGraph` | Canonical nodes and declared edges. |
| Closure | A program plus its transitive dependencies. |
| Post-order | Dependencies are registered before their consumers. |
| Visible definition | A datatype or module type from a program's transitive closure. |
| Reachability | The walk from a target's module tree into the module types it invokes. |
| Lookup cache | A JSON cache of `(kind, name, mode) -> (base, extension)` resolutions. |
| AST cache | An HMAC-signed pickle cache of parsed `BasePicture` values. |
| Hermetic load | A load with `cache_dir=None`: no disk writes, no shared state. |

## CLI

| Term | Meaning |
| --- | --- |
| Finding | The one reportable-problem shape the CLI emits. |
| Rule | The machine-only finding identifier. It is never printed as prose. |
| Schema | A versioned JSON document id, `sattline.v1.<command>`. |
| `--fail-on` | Which findings turn the exit code into `1`: `none` or `error`. |
| `--jsonl` | One JSON object per line, then a summary object. |
| Exit code | `0` clean, `1` findings, `2` usage/input, `3` internal. |
