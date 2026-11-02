"""Public parser-core entry points and orchestration layer.

This façade re-exports the parse pipeline from
:mod:`sattline_parser.source_io` together with the graphics companion entry
points, so consumers have one door. Keeping the pipeline in ``source_io`` lets
the project layer load files without importing this module back.
"""

from __future__ import annotations

from sattline_parser.project import (
    parse_graphics_file,
    parse_graphics_text,
    resolve_graphics_companion_path,
)

from .errors import (
    ParseErrorDetails,
    describe_parse_error,
)
from .errors import (
    _failure_details as _failure_details,  # pyright: ignore[reportPrivateUsage]  # re-exported as a test seam
)
from .errors import (
    _unexpected_input_summary as _unexpected_input_summary,  # pyright: ignore[reportPrivateUsage]  # re-exported as a test seam
)
from .source_io import (
    build_lark_parser,
    create_parser,
    create_sl_parser,
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
    "create_sl_parser",
    "decode_source_bytes",
    "describe_parse_error",
    "load_source_text",
    "parse_and_validate",
    "parse_graphics_file",
    "parse_graphics_text",
    "parse_source_file",
    "parse_source_text",
    "read_text_cp1252",
    "render_ide_text",
    "resolve_graphics_companion_path",
    "source_text_for_parse",
    "validate_basepicture",
]
