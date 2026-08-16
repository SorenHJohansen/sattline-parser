"""Parse-error representation, description, and logging for parser-core."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken

if TYPE_CHECKING:
    from sattline_parser.source_document import SourceDocument

__all__ = [
    "ParseErrorDetails",
    "_log_parser_failure",
    "describe_parse_error",
]

log = logging.getLogger("sattline_parser")


@dataclass(frozen=True, slots=True)
class ParseErrorDetails:
    message: str
    line: int | None = None
    column: int | None = None


def _unexpected_input_summary(exc: UnexpectedInput) -> str:
    summary = str(exc).splitlines()[0].strip()
    expected = getattr(exc, "expected", None)
    if expected:
        expected_text = ", ".join(sorted(expected)[:12])
        if expected_text and expected_text not in summary:
            summary = f"{summary}. Expected one of: {expected_text}"
    elif isinstance(exc, UnexpectedEOF):
        expected = sorted(getattr(exc, "expected", ()) or ())
        if expected:
            summary = f"Unexpected end of input. Expected one of: {', '.join(expected[:12])}"
    elif isinstance(exc, UnexpectedToken):
        token = getattr(exc, "token", None)
        if token is not None:
            summary = f"Unexpected token {token!r}"
            expected = sorted(getattr(exc, "expected", ()) or ())
            if expected:
                summary = f"{summary}. Expected one of: {', '.join(expected[:12])}"
    elif isinstance(exc, UnexpectedCharacters):
        summary = summary.rstrip(".")
    return summary


def _mapped_error_position(exc: UnexpectedInput, source_document: SourceDocument | None) -> int | None:
    """Map an UnexpectedInput's ``pos_in_stream`` to an original offset.

    When a ``source_document`` is supplied and the exception has not already
    been remapped (e.g. by ``sattline_parser.source_document.remap_parse_error``),
    the exception's ``pos_in_stream`` (an offset in the normalized text) is
    translated to an offset in the original source.
    """
    if source_document is None or getattr(exc, "_sattline_remapped", False):
        return None
    pos = getattr(exc, "pos_in_stream", None)
    if not isinstance(pos, int):
        return None
    return source_document.map_position(pos)


def _context_at(source_text: str, pos: int, span: int = 40) -> str:
    before = source_text[max(pos - span, 0) : pos].rsplit("\n", 1)[-1]
    after = source_text[pos : pos + span].split("\n", 1)[0]
    return before + after + "\n" + " " * len(before.expandtabs()) + "^\n"


def describe_parse_error(
    exc: Exception,
    source_text: str,
    *,
    source_document: SourceDocument | None = None,
) -> ParseErrorDetails:
    """Describe a parse failure, reporting positions in the *original* source.

    ``source_text`` must be the original (un-preprocessed) source. When
    ``source_document`` is supplied and the exception position is in normalized
    (decoded) coordinates, the reported line/column are mapped back to the
    original source.
    """
    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)
    if isinstance(exc, UnexpectedInput):
        mapped = _mapped_error_position(exc, source_document)
        if mapped is not None:
            line, column = source_document.line_col(mapped)  # type: ignore[union-attr]
            context = _context_at(source_text, mapped).rstrip()
        else:
            context = exc.get_context(source_text, span=40).rstrip()
        message = _unexpected_input_summary(exc)
        if context:
            message = f"{message}\n{context}"
        return ParseErrorDetails(message=message, line=line, column=column)
    return ParseErrorDetails(message=str(exc), line=line, column=column)


def _failure_details(
    exc: Exception,
    source_text: str | None = None,
    source_document: SourceDocument | None = None,
) -> ParseErrorDetails:
    if source_text is not None:
        return describe_parse_error(exc, source_text, source_document=source_document)
    return ParseErrorDetails(
        message=str(exc),
        line=getattr(exc, "line", None),
        column=getattr(exc, "column", None),
    )


def _log_parser_failure(
    *,
    stage: str,
    exc: Exception,
    source_text: str | None = None,
    source_path: Path | None = None,
    source_document: SourceDocument | None = None,
) -> None:
    details = _failure_details(exc, source_text, source_document)
    path_text = str(source_path) if source_path is not None else None
    location_text = ""
    if details.line is not None and details.column is not None:
        location_text = f" (line {details.line}, column {details.column})"
    elif details.line is not None:
        location_text = f" (line {details.line})"
    path_suffix = f" for {path_text}" if path_text is not None else ""
    log.error(
        "Parser %s failure%s%s: %s",
        stage,
        path_suffix,
        location_text,
        details.message,
        extra={
            "parser_stage": stage,
            "parser_path": path_text,
            "parser_line": details.line,
            "parser_column": details.column,
            "parser_context": details.message,
        },
        exc_info=(type(exc), exc, exc.__traceback__),
    )
