"""Parse-error representation, description, and logging for parser-core."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken

from .preprocessing.comments import strip_sl_comments_with_mapping

__all__ = [
    "ParseErrorDetails",
    "_log_parser_failure",
    "describe_parse_error",
]

log = logging.getLogger("sattline_parser")
_LARK_LOCATION_SUFFIX_RE = re.compile(r", at line \d+ col \d+$")


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


def _render_source_context(source_text: str, *, line: int | None, column: int | None) -> str:
    if line is None or column is None or line < 1 or column < 1:
        return ""
    lines = source_text.splitlines()
    if line > len(lines):
        return ""
    context_line = lines[line - 1]
    caret_padding = max(column - 1, 0)
    return f"{context_line}\n{' ' * caret_padding}^"


def _rewrite_summary_location(summary: str, *, line: int | None, column: int | None) -> str:
    if line is None or column is None:
        return summary
    if not _LARK_LOCATION_SUFFIX_RE.search(summary):
        return summary
    return _LARK_LOCATION_SUFFIX_RE.sub(f", at line {line} col {column}", summary)


def describe_parse_error(exc: Exception, source_text: str) -> ParseErrorDetails:
    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)
    if isinstance(exc, UnexpectedInput):
        message = _unexpected_input_summary(exc)
        stripped = strip_sl_comments_with_mapping(source_text)
        if stripped.text != source_text:
            line, column = stripped.map_line_column(line, column)
            message = _rewrite_summary_location(message, line=line, column=column)
            context = _render_source_context(source_text, line=line, column=column).rstrip()
        else:
            context = exc.get_context(source_text, span=40).rstrip()
        if context:
            message = f"{message}\n{context}"
        return ParseErrorDetails(message=message, line=line, column=column)
    return ParseErrorDetails(message=str(exc), line=line, column=column)


def _failure_details(exc: Exception, source_text: str | None = None) -> ParseErrorDetails:
    if source_text is not None:
        return describe_parse_error(exc, source_text)
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
) -> None:
    details = _failure_details(exc, source_text)
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
