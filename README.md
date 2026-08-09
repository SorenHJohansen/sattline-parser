# sattline-parser

Standalone parser, AST, and transformer for the SattLine PLC language.

This package is the extracted parser core of [SattLint](https://github.com/SorenHJohansen/SattLint). It owns the Lark grammar, the strict single-file syntax behavior, the AST models, and the `SLTransformer`.

## Features

- Lark LALR parser for SattLine `.s`/`.g`/`.l` sources (grammar in `grammar/sattline.lark`)
- Strict, no-silent-fallback parsing
- AST models in `sattline_parser.models`
- `SLTransformer` tree transformer in `sattline_parser.transformer`
- Compressed-source decoding (`preprocess_sl_text`, `is_compressed`)
- Standalone fuzz harness with timeout protection and corpus regression
- Zero runtime dependencies beyond `lark` and `regex`

## Install

```bash
pip install sattline-parser
```

Requires Python 3.13+.

## Usage

```python
from sattline_parser import parse_source_text, create_parser

parser = create_parser()
picture = parse_source_text(open("program.s", encoding="utf-8").read())
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
