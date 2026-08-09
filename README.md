# sattline-parser

Standalone parser, AST, and transformer for ABB SattLine.

This package owns the Lark grammar, the strict single-file syntax behavior, the AST models, and the `SLTransformer` — all in one self-contained, installable package.

## Features

- Lark LALR parser for SattLine sources (grammar in `grammar/sattline.lark`)
- Parses plain text and files — `.s`, `.g`, `.l`, `.x`, `.y`, `.z` and any other extension; the parser is content-based, not extension-based
- Strict, no-silent-fallback parsing
- Automatic comment stripping (`(* ... *)`, nested) before parsing
- Automatic compressed-source decoding (`preprocess_sl_text`, `is_compressed`)
- Error reporting with line/column mapping from cleaned text back to the original source (`describe_parse_error`)
- AST models in `sattline_parser.models`
- `SLTransformer` tree transformer in `sattline_parser.transformer`
- Standalone fuzz harness with timeout protection and corpus regression
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

`parse_source_text` is for when you already hold the source as a string — a snippet, an editor buffer, a response from an API, or content read by your own code. The two are interchangeable in behavior; `parse_source_file(path)` is equivalent to `parse_source_text(path.read_text(...))` plus the encoding fallback and path-aware error reporting. Start with `parse_source_file` when you have a path, `parse_source_text` otherwise.

Both entry points handle cleanup automatically, so you do not need to pre-process the source:

- **Comments are stripped** automatically (`(* ... *)`, including nested ones).
- **Compressed sources are detected and decoded** automatically.

The exposed helpers below exist for the rare case where you are building tooling that needs the intermediate stages (for example, to tokenize, diff, or re-emit sources). For ordinary parsing you can ignore them.

### For power users: strip comments yourself

```python
from sattline_parser import strip_sl_comments

clean = strip_sl_comments(source)  # removes nested (* ... *) comments
```

`strip_sl_comments` returns comment-free text without parsing. Useful for tools that operate on the raw source (syntax highlighting, diffs, search) or for wrapping the parser with your own preprocessing.

### For power users: handle compressed sources

```python
from sattline_parser import is_compressed, preprocess_sl_text

if is_compressed(source):
    decoded, mapping = preprocess_sl_text(source)
```

`is_compressed` answers whether the text uses the compressed encoding, and `preprocess_sl_text` decodes it, returning the decoded text plus a mapping back to the original. Since both parse entry points already detect and decode compressed sources, these are only needed by tooling that must decode without parsing — for example, saving a plain-text copy — or by the fuzz harness that drives `preprocess_sl_text` with adversarial inputs.

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

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/parser -q
ruff check src tests
pyright src tests
```

## Project layout

- `src/sattline_parser/grammar/` — Lark grammar and constants
- `src/sattline_parser/models/` — AST models
- `src/sattline_parser/transformer/` — transformer mixins and `SLTransformer`
- `src/sattline_parser/api.py` — public entry points
- `src/sattline_parser/fuzz_harness.py` — standalone fuzzing

## License

MIT. Copyright (c) 2025 Søren H. Johansen.
