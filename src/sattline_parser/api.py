"""Public parser-core entry points.

This façade re-exports the parse pipeline from
:mod:`sattline_parser.source_io` together with error description and
validation, so consumers have one door for parsing.

The dependency direction is downward only: this module builds on ``source_io``,
``errors``, ``preprocessing``, and ``validation``, and knows nothing about
:mod:`sattline_parser.project`. The package root in
:mod:`sattline_parser` composes this façade with the project layer, and the
project layer loads files through ``source_io`` rather than back through here,
so no import cycle exists at any point.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from lark import Lark

from .errors import PARSE_FAILURES, ParseErrorDetails, SourceTooDeepError, describe_parse_error, source_line_at
from .models.ast_model import BasePicture, DataType, ModuleTypeDef
from .preprocessing import render_ide_text
from .source_document import split_source_lines
from .source_io import (
    MAX_SOURCE_DEPTH,
    build_lark_parser,
    create_parser,
    decode_source_bytes,
    load_source_text,
    parse_source_bytes,
    parse_source_file,
    parse_source_text,
    read_text_cp1252,
    source_text_for_parse,
)
from .transformer.sl_transformer import SLTransformer
from .validation import Diagnostic, validate_basepicture


def parse_and_validate(
    src: str,
    *,
    parser: Lark | None = None,
    transformer: SLTransformer | None = None,
    debug: Callable[[str], None] | None = None,
    source_path: Path | None = None,
    log_failures: bool = True,
    external_datatypes: Sequence[DataType] = (),
    external_moduletype_defs: Sequence[ModuleTypeDef] = (),
    allow_unresolved_external_datatypes: bool = False,
) -> tuple[BasePicture, tuple[Diagnostic, ...]]:
    """Parse a SattLine source and run strict single-source validation.

    This is the façade that composes ``source_io`` with the validator, so
    ``source_io`` stays a parse-only floor and the project layer never imports
    the public façade back.
    """
    basepic = parse_source_text(
        src,
        parser=parser,
        transformer=transformer,
        debug=debug,
        source_path=source_path,
        log_failures=log_failures,
    )
    return basepic, validate_basepicture(
        basepic,
        external_datatypes=external_datatypes,
        external_moduletype_defs=external_moduletype_defs,
        allow_unresolved_external_datatypes=allow_unresolved_external_datatypes,
    )


__all__ = [
    "MAX_SOURCE_DEPTH",
    "PARSE_FAILURES",
    "ParseErrorDetails",
    "SourceTooDeepError",
    "build_lark_parser",
    "create_parser",
    "decode_source_bytes",
    "describe_parse_error",
    "load_source_text",
    "parse_and_validate",
    "parse_source_bytes",
    "parse_source_file",
    "parse_source_text",
    "read_text_cp1252",
    "render_ide_text",
    "source_line_at",
    "source_text_for_parse",
    "split_source_lines",
    "validate_basepicture",
]
