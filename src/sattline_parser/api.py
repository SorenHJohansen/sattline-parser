"""Public parser-core entry points.

This façade re-exports the parse pipeline from
:mod:`sattline_parser.source_io` together with error description and
validation, so consumers have one door for parsing.

The dependency direction is downward only: this module builds on ``source_io``,
``errors`` and ``validation``, and knows nothing about
:mod:`sattline_parser.project`. The package root in
:mod:`sattline_parser` composes this façade with the project layer, and the
project layer loads files through ``source_io`` rather than back through here,
so no import cycle exists at any point.
"""

from __future__ import annotations

from .errors import ParseErrorDetails, describe_parse_error
from .source_io import (
    build_lark_parser,
    create_parser,
    decode_source_bytes,
    load_source_text,
    parse_and_validate,
    parse_source_file,
    parse_source_text,
    read_text_cp1252,
    render_ide_text,
    source_text_for_parse,
)
from .validation import validate_basepicture

__all__ = [
    "ParseErrorDetails",
    "build_lark_parser",
    "create_parser",
    "decode_source_bytes",
    "describe_parse_error",
    "load_source_text",
    "parse_and_validate",
    "parse_source_file",
    "parse_source_text",
    "read_text_cp1252",
    "render_ide_text",
    "source_text_for_parse",
    "validate_basepicture",
]
