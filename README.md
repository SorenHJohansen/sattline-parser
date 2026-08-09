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

picture = parse_source_file(Path("program.s"))
```

### Parse source text

```python
from sattline_parser import parse_source_text

source = open("program.x", encoding="utf-8").read()
picture = parse_source_text(source)  # comments stripped, decoding applied
```

`parse_source_file` and `parse_source_text` both return a `BasePicture` (the module-level model) with the full AST attached.

### Strip comments yourself

```python
from sattline_parser import strip_sl_comments

clean = strip_sl_comments(source)  # removes nested (* ... *) comments
```

### Handle compressed sources

```python
from sattline_parser import is_compressed, preprocess_sl_text

if is_compressed(source):
    decoded, _ = preprocess_sl_text(source)
```

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
