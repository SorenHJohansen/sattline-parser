"""The one finding shape the CLI emits, for parse errors and validator diagnostics alike.

A finding explains itself: ``message`` is a sentence about the source, ``hint``
carries the actionable part when there is one, and ``rule`` is a machine-only
identifier (never printed as text) for baselines and diffs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lark.exceptions import UnexpectedInput

from sattline_parser.api import describe_parse_error
from sattline_parser.validation import Diagnostic

from ._io import display_path

__all__ = ["Finding", "finding_from_diagnostic", "finding_from_parse_error"]

Severity = Literal["error", "warning"]

#: Rule id for a source that does not parse (no validator rule applies).
_PARSE_RULE = "PARSE_ERROR"
#: Rule id for input the decoder refuses (malformed compact/coded stream).
_DECODE_RULE = "DECODE_ERROR"


@dataclass(frozen=True, slots=True)
class Finding:
    """One reportable problem, shaped the same for every source of finding."""

    severity: Severity
    message: str
    rule: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    start: int | None = None
    end: int | None = None
    hint: str | None = None
    source_line: str | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def location(self) -> str:
        """``path:line:col: `` prefix, or an empty string when there is no location."""
        if self.file is None:
            return ""
        if self.line is None:
            return f"{self.file}: "
        if self.column is None:
            return f"{self.file}:{self.line}: "
        return f"{self.file}:{self.line}:{self.column}: "

    def to_json(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "message": self.message,
            "rule": self.rule,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "start": self.start,
            "end": self.end,
            "hint": self.hint,
            "source_line": self.source_line,
        }


def finding_from_diagnostic(diagnostic: Diagnostic, *, file: str, source_text: str, absolute_paths: bool) -> Finding:
    """Map a parser diagnostic onto the CLI finding shape."""
    span = diagnostic.span
    line = span.line if span is not None else None
    return Finding(
        severity=diagnostic.severity.value,
        message=diagnostic.message,
        rule=diagnostic.code.name,
        file=display_path(file, absolute=absolute_paths),
        line=line,
        column=span.column if span is not None else None,
        start=span.start if span is not None else None,
        end=span.end if span is not None else None,
        source_line=_source_line(source_text, line),
    )


def _source_line(source_text: str, line: int | None) -> str | None:
    if line is None or line < 1:
        return None
    lines = source_text.splitlines()
    return lines[line - 1] if line <= len(lines) else None


def finding_from_parse_error(exc: Exception, source_text: str, *, file: str, absolute_paths: bool) -> Finding:
    """Describe a parse (or decode) failure as a self-contained finding."""
    if isinstance(exc, UnexpectedInput):
        details = describe_parse_error(exc, source_text)
        return Finding(
            severity="error",
            message=details.sentence or details.message.splitlines()[0],
            rule=_PARSE_RULE,
            file=display_path(file, absolute=absolute_paths),
            line=details.line,
            column=details.column,
            hint=details.hint,
            source_line=details.source_line or _source_line(source_text, details.line),
        )
    return Finding(
        severity="error",
        message=str(exc),
        rule=_DECODE_RULE,
        file=display_path(file, absolute=absolute_paths),
    )
