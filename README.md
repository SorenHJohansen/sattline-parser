# sattline-parser

Standalone parser, AST, and transformer for SattLine source.

This is an independent, unofficial project. It is not affiliated with, endorsed
by, or supported by ABB, and the SattLine name is used only to describe the file
format this package reads.

## Scope

`sattline-parser` is **language infrastructure**. It answers "what is in this
source, and how is it structured?". It does not analyse a program, score it,
refactor it, or decide whether it is correct for a machine.

| Responsibility | Where |
| --- | --- |
| Grammar and tokenization | `src/sattline_parser/grammar/` |
| Compressed-source preprocessing and source provenance | `src/sattline_parser/preprocessing/`, `src/sattline_parser/source_document.py` |
| AST models and transformation | `src/sattline_parser/models/`, `src/sattline_parser/transformer/` |
| Syntax diagnostics | `src/sattline_parser/errors.py` |
| Graphics file parsing and data models | `src/sattline_parser/project/graphics_*.py`, `project/models.py` |
| SattLine project discovery | `src/sattline_parser/project/discovery.py` |
| Draft/official resolution | `src/sattline_parser/project/formats.py` |
| Dependency resolution and project loading | `src/sattline_parser/project/loader.py` |
| Language-level structural validation | `src/sattline_parser/validation/` |
| Generic parser and project introspection | `src/sattline_parser/cli/` |

Out of scope: lint policy, metrics, dead-code analysis, refactoring, code
generation, graphics correlation, asset verification, rendering, and any
consumer-specific rule. The package supplies language facts with source
positions. A consumer applies its own policy on top.

## Documentation

The internals are documented in [`docs/`](docs/README.md):

- [Architecture](docs/architecture.md): layers, module map, and import rules
- [Parse pipeline](docs/parse-pipeline.md): bytes to `BasePicture`
- [Grammar and tokenization](docs/grammar.md): `sattline.lark`, the lexer, comments
- [Source provenance](docs/source-provenance.md): original-source positions
- [AST models](docs/ast.md): the tree and its invariants
- [Transformer](docs/transformer.md): how the tree is built
- [Validation](docs/validation.md): the strict single-source rules
- [Project layer](docs/project.md): discovery, dependencies, caches
- [Graphics companions](docs/graphics.md): `.g` / `.y` parsing
- [Command line](docs/cli.md): commands, exit codes, JSON schemas
- [Builtins](docs/builtins.md): function signatures and record fields
- [Public API](docs/api.md): the stable import surface
- [Testing and CI](docs/testing.md): suites, coverage, fuzzing
- [Development](docs/development.md): setup, workflow, conventions

## Provenance

Everything in this repository that describes SattLine behaviour was established
from publicly available documentation, from the observable behaviour of real
source and companion files, and from black-box testing against the product
itself.

This package owns the Lark grammar, the strict single-file syntax behavior, the AST models, and the `SLTransformer`, all in one self-contained, installable package.

## Features

- Lark LALR parser for SattLine sources (grammar in `grammar/sattline.lark`)
- Parses plain text and files (`.s`, `.g`, `.l`, `.x`, `.y`, `.z` and any other extension; the parser is content-based, not extension-based)
- Strict, no-silent-fallback parsing: unknown compressed markers and unexpected transformer structures raise errors instead of being silently rewritten or dropped
- Structural comments (`(* ... *)`, nested) preserved as role-tagged AST nodes
- Automatic compressed-source decoding with full source provenance: AST spans and error locations always refer to the *original* source (`SourceSpan` carries character offsets plus line/column)
- Lexically aware decoding: string literals and comments are protected, so syntax-looking text inside them is never rewritten
- Parse errors described as sentences about the source, with a location, the
  expected spellings and an actionable hint (`describe_parse_error`)
- AST models in `sattline_parser.models`
- `SLTransformer` tree transformer in `sattline_parser.transformer`
- Read-only `sattline` command line over the parser, project and graphics
  layers (`check`, `parse`, `query`, `project`, `graphics`, `decode`, `diff`,
  `corpus`, `version`) with JSON-first output
- PEP 561 typed: `py.typed` ships, so downstream type checkers use the inline
  annotations
- Standalone fuzz harness with hard subprocess timeouts and corpus regression
- Zero runtime dependencies beyond `lark` and `regex`

## Install

```bash
pip install sattline-parser
```

Requires Python 3.12+.

## Usage

### Command line

The package ships a `sattline` command (also `python -m sattline_parser`) for
tooling and agents that should not write Python glue:

```bash
sattline check SR/*.s --jsonl     # decode + parse + validate, machine-readable
sattline parse M.s --tree         # the AST as JSON
sattline query M.s --what writers # one structural question
sattline rules --json             # the validation rule registry
sattline diff Program.x Program.s # official vs draft code of one unit, findings and counts
sattline version --json           # tool and JSON schema versions
```

Findings are sentences with a location, an optional `help:` line and a
machine-only rule id; exit codes are `0` clean, `1` findings, `2` usage/input,
`3` internal. Run `sattline <command> --help` for the full option list of any
command.

### Parse a source file

```python
from pathlib import Path
from sattline_parser import parse_source_file

basepicture = parse_source_file(Path("program.s"))
```

### Parse source text

```python
from sattline_parser import parse_source_text

source = open("program.x", encoding="cp1252").read()
basepicture = parse_source_text(source)
```

`parse_source_file` and `parse_source_text` both return a `BasePicture` (the module-level model) with the full AST attached.

### Choosing an entry point

`parse_source_file` is for when you have a path on disk. It handles the file I/O for you: it reads the file as **Windows-1252** (`cp1252`, the only encoding the real SattLine parser accepts, with no fallback to `utf-8` or `latin-1`) and passes the path along so error messages can name the source file.

`parse_source_text` is for when you already hold the source as a string: a snippet, an editor buffer, a response from an API, or content read by your own code. The two are interchangeable in behavior; `parse_source_file(path)` is equivalent to `parse_source_text(path.read_bytes().decode("cp1252"))` plus path-aware error reporting. Start with `parse_source_file` when you have a path, `parse_source_text` otherwise.

Both entry points handle cleanup automatically, so you do not need to pre-process the source:

- **Comments are parsed structurally** (`(* ... *)`, including nested ones) and preserved on the AST as `CodeComment` nodes.
- **Compressed sources are detected and decoded** automatically.

The exposed helpers below exist for the rare case where you are building tooling that needs the intermediate stages (for example, to tokenize, diff, or re-emit sources). For ordinary parsing you can ignore them.

### For power users: handle compressed sources

```python
from sattline_parser import is_compressed, preprocess_sl_text, preprocess_source

if is_compressed(source):
    decoded, mapping = preprocess_sl_text(source)
    # ... or, when you need original-source provenance:
    doc = preprocess_source(source)
    doc.original_text, doc.normalized_text  # preprocessed vs original
```

`is_compressed` answers whether the text uses the compressed encoding.
`preprocess_sl_text` decodes it, returning the decoded text plus the *marker
substitution table* (the seed mapping that was applied). That mapping is **not**
a position map. Use `preprocess_source` for provenance. `preprocess_source`
returns a `SourceDocument` carrying the original text, the decoded text, and a
per-character map from decoded offsets back to the original source; `parse_source_text`
uses it internally so every AST span and diagnostic points into the original source.

Decoding is lexically aware: string literals and `(* ... *)` comments are
protected before any transformation runs, so `#markers` and other syntax-looking
text inside them are never rewritten. An unknown compressed marker raises
`PreprocessError` instead of being silently replaced with whitespace.

Since both parse entry points already detect and decode compressed sources,
these helpers are only needed by tooling that must decode without parsing (for
example, saving a plain-text copy) or by the fuzz harness that drives the
decoder with adversarial inputs.

### Report errors with source locations

```python
from sattline_parser import create_parser, describe_parse_error, parse_source_text

parser = create_parser()
try:
    parse_source_text(source, parser=parser, log_failures=False)
except Exception as exc:
    details = describe_parse_error(exc, source)
    print(f"{details.line}:{details.column} {details.message}")
```

`details.message` is a sentence about the source, not a parser dump. For
`ENDDEF (*BasePicture*)` with the terminating `;` missing it reads:

```text
unexpected end of file; expected ';', '(', 'LOCALVARIABLES' or 'ModuleDef'
help: the unit ends before a required ';'; the last construct is incomplete
ENDDEF (*BasePicture*)
                    ^
```

The same information is available structurally for tools: `details.found`,
`details.expected`, `details.hint` and `details.source_line`. Pass
`log_failures=False` to keep the traceback out of the log when you render the
message yourself.

### What is the AST good for?

`parse_source_file` and `parse_source_text` return a `BasePicture`, a tree of Python objects that mirrors the structure of the program. Once you have it, you can inspect and walk the program *as data* instead of as text.

For readers new to ASTs (abstract syntax trees): the parser does not give you the flat file back; it gives you structured objects. `basepicture.program_name` is the program name, `basepicture.moduletype_defs` is the list of type definitions, `basepicture.submodules` is the tree of nested modules, and so on. You can read fields, iterate lists, and check conditions directly in Python. For a small program this prints:

```python
from pathlib import Path
from sattline_parser import parse_source_file

basepicture = parse_source_file(Path("program.s"))
print(basepicture.program_name)
print([submodule.header.name for submodule in basepicture.submodules])
print(len(basepicture.submodules), "submodules")
```

```text
program
['Controller1', 'Controller2']
2 submodules
```

Think of the AST as a structured, machine-readable view of the program, that tools (a linter, a refactorer, an editor, a report generator) can walk without re-parsing the text. Since an AST is just nested objects, answering questions about the program becomes ordinary Python.

For a generic traversal, use the public walker instead of copying the recursion:

```python
from sattline_parser import NodeVisitor, VarRef, walk

for event in walk(basepicture):
    if isinstance(event.node, VarRef):
        print(event.relation, event.node.name)


class Calls(NodeVisitor):
    def __init__(self):
        self.names = []

    def visit_FuncCall(self, call):
        self.names.append(call.name)
        self.generic_visit(call)


visitor = Calls()
visitor.visit(basepicture)
print(visitor.names)
```

`walk` is pre-order and reports the field, indices, and ancestor chain of each
node. `walk(..., emit_leave=True)` adds matching leave events for scope stacks,
and `iter_literal_leaves` reads the literal values a node holds. `NodeVisitor`
dispatches on the class name and supports `leave_<ClassName>` hooks. See
[docs/ast.md](docs/ast.md) for the covered fields and the parts of the model it
deliberately does not descend into.

### One unit, three files

A SattLine program or library is one unit made of three files: the code body,
the dependency sidecar, and the graphics companion. Draft is `.s`, `.l`, `.g`;
official is `.x`, `.z`, `.y`. The loader resolves each role by mode; a missing
sidecar is reported as a diagnostic and a missing companion is recorded as
absent, never invented. See
[docs/project.md](docs/project.md#artifact-formats) for the extension table.

### Project layer: load a whole project

Beyond single sources, `sattline_parser.project` owns the SattLine **project
layer**: search-root discovery, per-artifact draft→official fallback,
recursive requester-relative dependency resolution, and `.g`/`.y` graphics
companion parsing. `SattLineProject.load` resolves one or more targets across
the ordered roots and returns the complete resolved graph:

```python
from pathlib import Path
from sattline_parser.project import LoadMode, SattLineProject

project = SattLineProject.load(
    roots=[Path("programs"), Path("libs")],
    mode=LoadMode.DRAFT,
    targets=["MyProgram"],
)

program = project.get("MyProgram")  # case-insensitive; raises KeyError if absent
print(program.name)
print(list(project.graph().nodes))  # casefolded canonical identities
if program.graphics is not None:  # GraphicsMessage values, never raised
    print(program.graphics.errors)
```

- A `SattLineProgram` is one loaded source artifact (one `.x` or `.s` file),
  not one executable top-level program. A single target can therefore produce
  many entries in `project.programs()` through its dependency closure.
- Each target is resolved across ordered roots, its `.l` / `.z` dependency file
  is read, and dependencies load recursively before the target itself.
- Programs are canonicalized by casefolded identity: each name is visited and
  parsed exactly once, and cycles resolve as edges in the derived
  `DependencyGraph` (never infinite recursion).
- `strict=True` (default) fails fast on missing or unparseable artifacts;
  `strict=False` skips the failing program and continues. Failures surface as
  structured errors (`ProjectLoadError`, `ArtifactLoadError`,
  `DependencyNotFoundError`, `DependencyParseError`), and a skipped program is
  recorded as a `LoadDiagnosticKind.LOAD_SKIPPED` diagnostic, so a partial load
  is never silent.
- `validate=LoadValidation.INVOKED` (default) validates each target in full and
  limits a dependency file to the module types that target invokes,
  transitively, so an imported library's unused module types are never checked
  on the consumer's behalf. `FULL` validates every loaded program, which is what
  a whole-tree audit wants; `NONE` parses only. On the command line this is
  `--validate invoked|full|none`, and `--no-validate` stays as an alias for
  `none`.
- `cache_dir=...` optionally enables the parser-owned lookup and per-file AST
  caches (`FileLookupCache` / `FileASTCache`) so repeated loads skip
  re-discovery and re-parsing. When `cache_dir=None` (default) the load is
  fully in-memory and hermetic: no disk writes, no shared cache state.

```python
# Hermetic callers (no disk cache) are the recommended default:
project = SattLineProject.load(
    roots=[Path("programs"), Path("libs")],
    mode=LoadMode.DRAFT,
    targets=["MyProgram"],
    cache_dir=None,
)
```

## Public API and versioning

Releases use calendar versioning (`YYYY.M.N`). The version orders releases; it
does not encode semantic-version compatibility.

The supported public surface is documented in
[`docs/api.md`](https://github.com/SorenHJohansen/sattline-parser/blob/main/docs/api.md):
the names in the documented `__all__` sets, the `sattline` command, and its JSON
schemas. Submodule paths and names not listed there are internal and may change
between releases.

Within that surface, patch releases preserve existing names and behaviour. A
breaking change is called out in the changelog and removed in that release.
There is no deprecation window and no compatibility shim. Adding a dataclass
field is not considered breaking; removing or renaming one is.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                   # full configured suite
pytest benchmarks --no-cov -q               # parse benchmarks
ruff check src tests scripts benchmarks
ruff format --check src tests scripts benchmarks
pyright src tests benchmarks
bandit -q -r src -x tests -c pyproject.toml
pip-audit
python scripts/check_branch_coverage.py     # line >= 100%, branch >= 93%
```

The repository also ships an OpenCode workspace in `.opencode/`: the
`sattline-parser` skill, the `/verify`, `/release`, and `/review` commands, and a
read-only `parser-reviewer` subagent. `AGENTS.md` is the control plane, and
`docs/development.md` describes the workflow.

`dev` never pulls the `fuzz` extra, because the fuzzing engine is Linux and
FreeBSD only. Add it explicitly where it is supported:

```bash
pip install -e ".[dev,fuzz]"                # Linux / FreeBSD only
```

Line coverage is enforced at 100% after `pragma: no cover` and the configured
`exclude_lines` are applied; branch coverage is measured and gated by
`scripts/check_branch_coverage.py` (both enforced in CI). That script also
prints how many executable lines the exclusion rules keep outside the line
gate, so the 100% number is not mistaken for full-source coverage. The full
test suite is run by CI via `pytest` (the project's configured `testpaths`),
including the packaging tests in `tests/test_packaging.py` that live outside
`tests/parser`.

Fuzzing runs in three tiers, each enforced separately:

- **Deterministic corpus regression**: every fixture in `tests/fixtures/corpus/`
  must parse or produce an *expected* invalid-input error; runs in normal CI.
- **PR fuzz smoke**: a small number of random inputs must not crash the
  parser; runs in normal CI.
- **Continuous fuzzing**: long-running, coverage-guided fuzzing via
  ClusterFuzzLite (`.github/workflows/fuzz.yml`).

The fuzz harness enforces timeouts with a worker subprocess (killed on timeout,
reused across inputs) and classifies expected invalid-input errors (`UnexpectedInput`,
`PreprocessError`) separately from internal bugs: a `ValueError`/`TypeError`
from the transformer is treated as a crash, not as ordinary invalid input.

## Dependencies

The declared runtime dependencies are `lark[interegular]>=1.3.1,<1.4` and
`regex>=2023.12.25`. The parser does not call `regex` directly; Lark's `regex`
engine does. The floor is the first release with the Python 3.12 wheels used by
CI, not a feature requirement. CI tests both the locked minimum (lark 1.3.1)
and the latest lark that satisfies the range, so the supported range is
actually exercised. Installs use `uv.lock` for reproducibility.

## Project layout

- `src/sattline_parser/grammar/` : Lark grammar and constants
- `src/sattline_parser/models/` : AST models
- `src/sattline_parser/preprocessing/` : compressed-source decoding and its scanner table
- `src/sattline_parser/source_document.py` : original-source provenance and span remapping
- `src/sattline_parser/transformer/` : transformer mixins and `SLTransformer`
- `src/sattline_parser/validation/` : validator rules and diagnostics
- `src/sattline_parser/builtins/` : builtin function signatures and record field tables
- `src/sattline_parser/cli/` : the `sattline` command line (one module per command)
- `src/sattline_parser/api.py` : public entry points
- `src/sattline_parser/project/` : project/artifact layer (`SattLineProject`, discovery, resolution, `.g`/`.y` parsing, parser-owned caches)
- `src/sattline_parser/fuzz_harness.py` : standalone fuzzing
- `docs/` : architecture and internals documentation

## License

MIT. Copyright (c) 2025 Søren H. Johansen.
