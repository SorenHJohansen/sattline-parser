# sattline-parser

Standalone parser, AST, and transformer for ABB SattLine.

This package owns the Lark grammar, the strict single-file syntax behavior, the AST models, and the `SLTransformer`, all in one self-contained, installable package.

## Features

- Lark LALR parser for SattLine sources (grammar in `grammar/sattline.lark`)
- Parses plain text and files (`.s`, `.g`, `.l`, `.x`, `.y`, `.z` and any other extension; the parser is content-based, not extension-based)
- Strict, no-silent-fallback parsing: unknown compressed markers and unexpected transformer structures raise errors instead of being silently rewritten or dropped
- Structural comments (`(* ... *)`, nested) preserved as role-tagged AST nodes
- Automatic compressed-source decoding with full source provenance: AST spans and error locations always refer to the *original* source (`SourceSpan` carries character offsets plus line/column)
- Lexically aware decoding: string literals and comments are protected, so syntax-looking text inside them is never rewritten
- Error reporting with line/column locations in the original source (`describe_parse_error`)
- AST models in `sattline_parser.models`
- `SLTransformer` tree transformer in `sattline_parser.transformer`
- Standalone fuzz harness with hard subprocess timeouts and corpus regression
- Zero runtime dependencies beyond `lark` and `regex`

## Install

```bash
pip install sattline-parser
```

Requires Python 3.13+.

## Usage

### Parse a source file

```python
from pathlib import Path
from sattline_parser import parse_source_file

basepicture = parse_source_file(Path("program.s"))
```

### Parse source text

```python
from sattline_parser import parse_source_text

source = open("program.x", encoding="utf-8").read()
basepicture = parse_source_text(source)
```

`parse_source_file` and `parse_source_text` both return a `BasePicture` (the module-level model) with the full AST attached.

### Choosing an entry point

`parse_source_file` is for when you have a path on disk. It handles the file I/O for you: it reads the file with an encoding fallback (`utf-8`, then `cp1252`, then `latin-1`) and passes the path along so error messages can name the source file.

`parse_source_text` is for when you already hold the source as a string: a snippet, an editor buffer, a response from an API, or content read by your own code. The two are interchangeable in behavior; `parse_source_file(path)` is equivalent to `parse_source_text(path.read_text(...))` plus the encoding fallback and path-aware error reporting. Start with `parse_source_file` when you have a path, `parse_source_text` otherwise.

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
a position map — use `preprocess_source` for provenance. `preprocess_source`
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
    parse_source_text(source, parser=parser)
except Exception as exc:
    details = describe_parse_error(exc, source)
    print(f"{details.line}:{details.column} {details.message}")
```

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

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                   # full configured suite
ruff check src tests scripts
ruff format --check src tests scripts
pyright src tests
bandit -q -r src -x tests -c pyproject.toml
pip-audit
python scripts/check_branch_coverage.py     # line >= 100%, branch >= 93%
```

Line coverage is enforced at 100%; branch coverage is measured and gated by
`scripts/check_branch_coverage.py` (both enforced in CI). The full test suite
is run by CI via `pytest` (the project's configured `testpaths`), including the
packaging tests in `tests/test_packaging.py` that live outside `tests/parser`.

Fuzzing runs in three tiers, each enforced separately:

- **Deterministic corpus regression** — every fixture in `tests/fixtures/corpus/`
  must parse or produce an *expected* invalid-input error; runs in normal CI.
- **PR fuzz smoke** — a small number of random inputs must not crash the
  parser; runs in normal CI.
- **Continuous fuzzing** — long-running, coverage-guided fuzzing via
  ClusterFuzzLite (`.github/workflows/fuzz.yml`).

The fuzz harness enforces timeouts with a worker subprocess (killed on timeout,
reused across inputs) and classifies expected invalid-input errors (`UnexpectedInput`,
`PreprocessError`) separately from internal bugs — a `ValueError`/`TypeError`
from the transformer is treated as a crash, not as ordinary invalid input.

## Dependencies

The declared runtime dependencies are `lark[interegular]>=1.3.1,<2` and
`regex`. CI tests both the locked minimum (lark 1.3.1) and the latest lark that
satisfies the range, so the supported range is actually exercised. Installs use
`uv.lock` for reproducibility.

## Project layout

- `src/sattline_parser/grammar/` : Lark grammar and constants
- `src/sattline_parser/models/` : AST models
- `src/sattline_parser/transformer/` : transformer mixins and `SLTransformer`
- `src/sattline_parser/api.py` : public entry points
- `src/sattline_parser/fuzz_harness.py` : standalone fuzzing

## License

MIT. Copyright (c) 2025 Søren H. Johansen.
