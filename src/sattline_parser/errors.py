"""Parse-error representation, description, and logging for parser-core.

A parse failure is described as a *sentence* about the source, not as a dump of
Lark's internals: ``unexpected 'is'; expected 'Invocation' or a comment`` rather
than ``Unexpected token Token('NAME', 'is') ... Expected one of: INVOCATION``.
Terminal names are rendered through the resolved grammar, so an expectation is
reported in the spelling a source would use (``';'``, ``'ENDDEF'``) or as a
friendly phrase for pattern terminals (``a name``, ``a number``).

:class:`ParseErrorDetails` also carries the structured parts (``found``,
``expected``, ``hint`` and ``source_line``) so a caller can render its own
diagnostic without parsing prose.
"""

from __future__ import annotations

import difflib
import logging
import re
from collections.abc import Collection
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, cast

from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken

if TYPE_CHECKING:
    from sattline_parser.source_document import SourceDocument

__all__ = [
    "ParseErrorDetails",
    "_log_parser_failure",
    "_unexpected_input_summary",
    "describe_parse_error",
]

log = logging.getLogger("sattline_parser")


@dataclass(frozen=True, slots=True)
class ParseErrorDetails:
    """A described parse failure.

    ``message`` is the human/agent-facing text (sentence, optional ``help:``
    hint, then the source line and caret). The remaining fields expose the same
    information structurally for tools.
    """

    message: str
    line: int | None = None
    column: int | None = None
    #: The first line of ``message``: a sentence about the source, with no
    #: ``help:`` line and no source excerpt.
    sentence: str = ""
    #: The text that was not accepted; ``None`` at end of input.
    found: str | None = None
    #: What the grammar expected there, in source spelling where one exists.
    expected: tuple[str, ...] = ()
    #: One actionable sentence when the expectation pattern is recognised.
    hint: str | None = None
    #: The original source line at ``line`` (without the caret), when known.
    source_line: str | None = None


#: ``TERMINAL.10:   definition`` in the resolved grammar.
_TERMINAL_DEF_RE = re.compile(r"^(?P<name>[A-Z][A-Z0-9_]*)(?:\.[0-9]+)?:[ \t]*(?P<definition>.+?)[ \t]*$", re.MULTILINE)
#: ``";"`` — punctuation terminals keep their literal spelling.
_QUOTED_TERMINAL_RE = re.compile(r'^"(?P<text>[^"\\]+)"$')
#: ``/(?i:ENDDEF\b)/`` — a keyword after case folding.
_CASE_FOLDED_KEYWORD_RE = re.compile(r"^/\(\?i:(?P<text>[A-Za-z_][A-Za-z0-9_]*)\\b\)/$")
#: Friendly names for terminals that are patterns, not literal spellings.
_TERMINAL_DISPLAY = {
    "NAME": "a name",
    "REAL": "a number",
    "SIGNED_INT": "an integer",
    "STRING": "a string",
    "STRING_CRLF": "a string",
    "COMMENT_START": "a comment",
    "SL_DATECODE": "a date code",
}
#: Lark names anonymous punctuation terminals after the character
#: (``load_grammar._TERMINAL_NAMES``) and those names are what ``expected``
#: carries, so they need a spelling too.
_PUNCTUATION_TERMINALS = {
    "SEMICOLON": ";",
    "COMMA": ",",
    "COLON": ":",
    "DOT": ".",
    "LPAR": "(",
    "RPAR": ")",
    "LSQB": "[",
    "RSQB": "]",
    "EQUAL": "=",
    "PLUS": "+",
    "MINUS": "-",
    "STAR": "*",
    "SLASH": "/",
    "QMARK": "?",
    "AMPERSAND": "&",
}
#: Terminals that are legal between any two tokens; listing them as an
#: expectation is noise rather than an actionable alternative.
_ALWAYS_ALLOWED = frozenset({"COMMENT_START"})
#: How many expectations to spell out before truncating.
_MAX_EXPECTED = 5
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@cache
def _terminal_spellings() -> dict[str, str]:
    """Terminal name -> literal spelling, read from the resolved grammar."""
    from sattline_parser.api import (  # noqa: PLC0415 - avoids an import cycle
        _resolved_grammar,  # pyright: ignore[reportPrivateUsage]
    )

    spellings: dict[str, str] = dict(_PUNCTUATION_TERMINALS)
    for match in _TERMINAL_DEF_RE.finditer(_resolved_grammar()):
        definition = match.group("definition")
        quoted = _QUOTED_TERMINAL_RE.match(definition)
        keyword = _CASE_FOLDED_KEYWORD_RE.match(definition)
        text = quoted.group("text") if quoted is not None else (keyword.group("text") if keyword else None)
        if text is not None:
            spellings[match.group("name")] = text
    return spellings


def _terminal_label(name: str, spellings: dict[str, str]) -> str:
    spelling = spellings.get(name)
    if spelling is not None:
        return f"'{spelling}'"
    return _TERMINAL_DISPLAY.get(name, name)


def _label_order(label: str) -> tuple[bool, str]:
    # A missing ';' is by far the most common expectation, so it leads the list.
    return (label != "';'", label.casefold())


def _expected_labels(expected: object) -> tuple[str, ...]:
    candidates = cast("Collection[str]", expected) if isinstance(expected, Collection) else ()
    names = [name for name in candidates if name not in _ALWAYS_ALLOWED]
    if not names:
        return ()
    spellings = _terminal_spellings()
    labels = sorted({_terminal_label(name, spellings) for name in names if not name.startswith("__")}, key=_label_order)
    return tuple(labels[:_MAX_EXPECTED])


def _join_labels(labels: tuple[str, ...]) -> str:
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f" or {labels[-1]}"


def _unexpected_found(exc: UnexpectedInput) -> str | None:
    token = getattr(exc, "token", None)
    if token is not None:
        return None if getattr(token, "type", None) == "$END" else str(token)[:40]
    char = getattr(exc, "char", None)
    return char if isinstance(char, str) else None


def _unexpected_hint(found: str | None, labels: tuple[str, ...], *, line: int | None) -> str | None:
    if found is None:
        if "';'" in labels:
            return "the unit ends before a required ';'; the last construct is incomplete"
        return "the unit ends unexpectedly; the last construct is incomplete"
    if line is not None and line <= 3 and "a string" in labels:
        return "a unit starts with three quoted header lines (syntax version, original file date, program date)"
    words = [label[1:-1] for label in labels if label.startswith("'") and _WORD_RE.fullmatch(label[1:-1])]
    if _WORD_RE.fullmatch(found) and words:
        closest = difflib.get_close_matches(found, words, n=1, cutoff=0.8)
        if closest:
            return f"did you mean '{closest[0]}'?"
    return None


def _unexpected_description(exc: UnexpectedInput) -> tuple[str, str | None, tuple[str, ...], str | None]:
    """``(sentence, hint, expected labels, found)`` for a parse failure."""
    found = _unexpected_found(exc)
    labels = _expected_labels(getattr(exc, "expected", None))
    if found is None:
        sentence = "unexpected end of file" if isinstance(exc, UnexpectedEOF | UnexpectedToken) else "unexpected input"
    elif isinstance(exc, UnexpectedCharacters):
        sentence = f"unexpected character {found!r}"
    else:
        sentence = f"unexpected {found!r}"
    if labels:
        sentence = f"{sentence}; expected {_join_labels(labels)}"
    return sentence, _unexpected_hint(found, labels, line=getattr(exc, "line", None)), labels, found


def _unexpected_input_summary(exc: UnexpectedInput) -> str:
    """One-line sentence for a parse failure (used in logs)."""
    return _unexpected_description(exc)[0]


def _mapped_error_position(exc: UnexpectedInput, source_document: SourceDocument) -> int | None:
    """Map an UnexpectedInput's ``pos_in_stream`` to an original offset.

    When a ``source_document`` is supplied and the exception has not already
    been remapped (e.g. by ``sattline_parser.source_document.remap_parse_error``),
    the exception's ``pos_in_stream`` (an offset in the normalized text) is
    translated to an offset in the original source.
    """
    if getattr(exc, "_sattline_remapped", False):
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
        mapped: int | None = None
        if source_document is not None:
            mapped = _mapped_error_position(exc, source_document)
        if mapped is not None and source_document is not None:
            line, column = source_document.line_col(mapped)
            context = _context_at(source_text, mapped).rstrip()
        else:
            context = exc.get_context(source_text, span=40).rstrip()
        sentence, hint, expected, found = _unexpected_description(exc)
        parts = [sentence]
        if hint is not None:
            parts.append(f"help: {hint}")
        if context:
            parts.append(context)
        return ParseErrorDetails(
            message="\n".join(parts),
            line=line,
            column=column,
            sentence=sentence,
            found=found,
            expected=expected,
            hint=hint,
            source_line=_source_line(source_text, line),
        )
    return ParseErrorDetails(message=str(exc), line=line, column=column, sentence=str(exc))


def _source_line(source_text: str, line: int | None) -> str | None:
    """The original source line at ``line`` (1-based), when it exists."""
    if not isinstance(line, int) or line < 1:
        return None
    lines = source_text.splitlines()
    return lines[line - 1] if line <= len(lines) else None


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
