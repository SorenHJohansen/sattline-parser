# Architecture

## Layer model

The package is a stack of layers. A layer may import the layer below it, never
the layer above. The split exists so the project layer can load files without
importing the public façade back, and so validation can run without a project.

```mermaid
flowchart TB
    subgraph L6["Presentation"]
        CLI["cli/"]
    end

    subgraph L5["Public façade"]
        API["api.py"]
        ASTSURF["ast.py"]
        TYPEFACTS["types.py"]
        INIT["__init__.py"]
    end

    subgraph L4["Project layer"]
        PROJECT["project/"]
    end

    subgraph L3["Language semantics"]
        VALIDATION["validation/"]
        BUILTINS["builtins/"]
        FORMATTING["formatting/"]
    end

    subgraph L2["Parse core"]
        SOURCE_IO["source_io.py"]
        TRANSFORMER["transformer/"]
        MODELS["models/"]
        ERRORS["errors.py"]
    end

    subgraph L1["Language facts"]
        GRAMMAR["grammar/"]
        PREPROCESS["preprocessing/"]
        SOURCE_DOC["source_document.py"]
        NAMES["names.py"]
    end

    CLI --> API
    CLI --> PROJECT
    CLI --> VALIDATION
    CLI -->|graphics| PROJECT
    API --> SOURCE_IO
    API --> PREPROCESS
    API --> VALIDATION
    API --> MODELS
    API --> TRANSFORMER
    INIT --> API
    INIT --> ASTSURF
    INIT --> TRANSFORMER
    INIT --> PREPROCESS
    INIT --> VALIDATION
    ASTSURF --> MODELS
    TYPEFACTS --> VALIDATION

    PROJECT --> SOURCE_IO
    PROJECT --> VALIDATION
    PROJECT --> MODELS
    PROJECT --> GRAMMAR
    PROJECT --> SOURCE_DOC

    VALIDATION --> MODELS
    VALIDATION --> BUILTINS
    VALIDATION --> NAMES
    BUILTINS --> NAMES
    FORMAT["sattline_parser.formatting"] --> MODELS
    SERIAL["sattline_parser.serialization"] --> MODELS

    SOURCE_IO --> TRANSFORMER
    SOURCE_IO --> MODELS
    SOURCE_IO --> ERRORS
    SOURCE_IO --> GRAMMAR
    SOURCE_IO --> PREPROCESS
    SOURCE_IO --> SOURCE_DOC

    TRANSFORMER --> MODELS
    TRANSFORMER --> GRAMMAR
    TRANSFORMER --> FORMATTING
    MODELS --> GRAMMAR
    MODELS --> NAMES
    PREPROCESS --> SOURCE_DOC
    PREPROCESS --> GRAMMAR
    PREPROCESS --> NAMES
    ERRORS --> GRAMMAR
```

The important import-direction rules:

- `source_io` imports neither `api` nor `project`. It is the shared floor.
- `project/` is layered internally: `planner` resolves, `executor` parses,
  `assembler` registers, `scope` validates. `loader.py` is the orchestrator
  over those four, and `identity.py` names the comparison rules they share.
  The package imports `source_io.parse_source_bytes` and
  `validation.validate_basepicture`. It never imports `api`.
- `api.py` re-exports `source_io`, `errors`, `preprocessing`, and `validation`,
  and owns `parse_and_validate`, the one entry point that composes parsing with
  the validator. `source_io` therefore stays parse-only and never imports the
  validation layer. The top-level package resolves the graphics entry points
  from the project layer lazily, so importing `sattline_parser.api` does not
  load `project/`.
- `ast.py` is a façade over `models/`: every node, clause, tail, and walker
  name crosses one import door, and it depends on nothing above `models/`.
- `types.py` is a façade over the pure type facts in `validation/typing.py`.
  Expression typing that needs a validation scope stays in the validation
  layer, not in the public module.
- `formatting/` renders AST values. It imports `models/`, and the model
  `__str__` renderers call it at display time, so `models/` has no module-level
  import edge into `formatting/`. The downward-only rule therefore holds, and
  the public rendering helpers are still the same code path as model display.
- `cli/` imports the public API and the project layer, and duplicates no parse
  or validation behaviour.
- `sattline_parser.constants` is the top-level re-export of
  `grammar.constants`, the public vocabulary for grammar keywords, token types,
  and property-map keys. Consumers that need a spelling import it from there
  rather than from a transformer or model module.

## Module map

| Path | Responsibility | Read when |
| --- | --- | --- |
| `src/sattline_parser/__init__.py` | Public names and version | You need the stable import surface |
| `src/sattline_parser/api.py` | Public façade over `source_io`, `errors`, `models`, `transformer`, and `validation`; owns `parse_and_validate` | You add a public parse or validation entry point |
| `src/sattline_parser/ast.py` | Supported AST surface: every node, clause, tail, and the walker | You import or document the model |
| `src/sattline_parser/types.py` | Public scalar type facts and literal inference | You import a type fact in a consumer |
| `src/sattline_parser/serialization.py` | JSON-friendly data for the model | You export AST data |
| `src/sattline_parser/source_io.py` | Parser cache, decoding, the source-to-`BasePicture` pipeline | You change parse orchestration |
| `src/sattline_parser/source_document.py` | Original/normalized text and offset mapping | You change positions |
| `src/sattline_parser/errors.py` | Parse-error sentences, structured details, logging | You change diagnostics |
| `src/sattline_parser/names.py` | CP1252 identifier folding | You compare identifiers |
| `src/sattline_parser/grammar/` | Lark grammar, constants, keyword casing, custom lexer | You change the language |
| `src/sattline_parser/preprocessing/` | Coded stream decoding, compressed markers, IDE layout | You change source decoding |
| `src/sattline_parser/models/` | AST dataclasses and expression nodes | You change the tree |
| `src/sattline_parser/transformer/` | `SLTransformer` and responsibility mixins | You change tree construction |
| `src/sattline_parser/validation/` | Strict single-source rules, scopes, typing | You add a rule |
| `src/sattline_parser/builtins/` | Generated function catalogue and record specs | You change builtin facts |
| `src/sattline_parser/formatting/` | `__str__`, public expression rendering, and whole-file source formatting | You change rendered output |
| `src/sattline_parser/serialization.py` | JSON-friendly data for the model | You export AST data |
| `src/sattline_parser/project/` | Discovery, identity, planning, parsing, assembly, validation scope, graphics, distribution, caches | You change project behaviour |
| `src/sattline_parser/project/planner.py` | Resolve names into post-order plans; artifact-keyed cycle detection | You change dependency discovery |
| `src/sattline_parser/project/executor.py` | Parse planned bodies, worker pool, AST cache, failure records | You change parsing or parallelism |
| `src/sattline_parser/project/assembler.py` | Registry entries, origins, companions | You change what a loaded unit carries |
| `src/sattline_parser/project/scope.py` | Validation scope, datecode conflicts, module-type recursion | You change a project-level rule |
| `src/sattline_parser/project/identity.py` | Language and filesystem identity types | You compare a name or a path |
| `src/sattline_parser/project/index.py` | Project-wide definition and usage index | You answer "who defines X" |
| `src/sattline_parser/cli/` | The `sattline` command | You change the interface |
| `fuzzing/fuzz_harness.py` | Hard-timeout fuzzing and corpus regression | You change fuzzing |
| `tests/` | Parser, project, CLI, builtins, packaging suites | You verify a change |
| `docs/` | This documentation | You need the design intent |

## Request flow

### Single file

```mermaid
sequenceDiagram
    autonumber
    participant Caller
    participant API as api.py
    participant IO as source_io
    participant PRE as preprocessing
    participant DOC as SourceDocument
    participant LARK as Lark + lexer
    participant TR as SLTransformer
    participant VAL as validation

    Caller->>API: parse_source_file(path)
    API->>IO: source_text_for_parse(path)
    IO->>IO: read bytes
    alt coded stream
        IO->>PRE: decode_coded_stream
    else cp1252 text
        IO->>IO: decode cp1252, tolerate undefined bytes in comments only
    end
    IO-->>API: source text (possibly still marker-compressed)
    API->>IO: parse_source_text(text)
    IO->>PRE: preprocess_source(text)
    PRE->>DOC: SourceDocument(original, normalized, char_map)
    IO->>LARK: parse(normalized_text)
    LARK-->>IO: Lark Tree with normalized positions
    IO->>DOC: remap_tree_to_original(tree)
    IO->>TR: transform(tree)
    TR-->>IO: BasePicture
    IO-->>API: BasePicture
    API-->>Caller: BasePicture
    opt parse_and_validate
        API->>VAL: validate_basepicture(bp)
        VAL-->>API: tuple[Diagnostic, ...]
    end
```

### Whole project

```mermaid
sequenceDiagram
    autonumber
    participant Caller
    participant P as SattLineProject
    participant L as ProjectLoader
    participant PL as ProjectPlanner
    participant D as ProjectLookup
    participant FS as filesystem
    participant X as ParseExecutor
    participant S as source_io
    participant A as ProjectAssembler
    participant V as ProjectValidator

    Caller->>P: load(roots, mode, targets, validate)
    P->>L: ProjectLoader(...).resolve(targets)
    loop each dependency, depth first
        L->>PL: resolve targets
        PL->>D: find_code_with_base(name)
        D->>FS: indexed or stat lookup in ordered roots
        FS-->>D: code path and resolving base
        PL->>D: find_deps_beside(code_path, name)
        D-->>PL: .l/.z path or None
        PL->>PL: read dependency names
        PL->>PL: visit each dependency first
        PL->>PL: append the plan after its dependencies
    end
    L->>X: parse(plans)
    X->>S: parse_source_bytes(code_path)
    S-->>X: BasePicture
    L->>A: assemble(plans, outcomes)
    A->>A: record origin, datecodes, sidecar state
    A->>A: parse graphics and distribution companions when present
    alt validate=INVOKED
        L->>V: validate targets, and only invoked library module types
    else validate=FULL
        L->>V: validate every loaded unit
    end
    L-->>P: registry, diagnostics
    P-->>Caller: SattLineProject
```

## Package boundaries

```mermaid
graph LR
    CONSUMER["consumer tooling"] -->|imports| PUBLIC["sattline-parser public API"]
    PUBLIC --> CORE["language core"]
    CORE --> FACTS["grammar, source, AST"]
    CONSUMER -.->|must not be imported by| FACTS
```

The dashed edge is the rule that keeps the package shippable on PyPI: the
parser package must never import a linter, an editor integration, a report
generator, or any other consumer. If a feature needs consumer knowledge, it
belongs in the consumer and not here.

## Design decisions worth knowing

| Decision | Why |
| --- | --- |
| Lark LALR with a contextual lexer | Deterministic parsing, fast enough for batch project loads, and a grammar file that is readable on its own |
| Custom `SattLineLexer` | Nesting `(* ... *)` comments cannot be modelled safely by a merged LALR state machine |
| Per-character source map instead of re-parsing | One parse, and every span still points at the original bytes |
| AST as frozen dataclasses where possible | Hashable, comparable, picklable, and safe to share between the parser and a consumer |
| Validation separate from parsing | Consumers choose whether they want language rules; the project loader chooses the scope |
| Parser-owned caches keyed by grammar fingerprint | A warm cache can never disagree with a cold one after a grammar change |
| One finding shape in the CLI | Agents branch on exit codes and JSON, not on prose |
