"""Layout decoded SattLine source so the IDE accepts it as a program file.

Decoding reproduces whatever line breaks the binary stream stored. SattLine
program files additionally follow two conventions the IDE relies on when
re-reading a saved file: CRLF terminators and no line longer than
:data:`MAX_IDE_LINE_LENGTH` characters. :func:`render_ide_text` applies that
layout and is safe to run on already-formatted text.
"""

from __future__ import annotations

import re

from .compressed import scan_opaque_regions

__all__ = ["MAX_IDE_LINE_LENGTH", "render_ide_text"]

#: Maximum emitted line length; genuine IDE-written sources stay below it.
MAX_IDE_LINE_LENGTH = 135

_NEWLINE_RE = re.compile(r"\r\n?|\n")


def _blocked_spaces(text: str) -> bytearray:
    """Mark every character that is inside a string literal or quoted identifier.

    The scan runs once over the whole source, so a continuation line inside a
    ``(* ... *)`` comment is comment text rather than a fresh string context.
    Comment regions stay unblocked: a space in a comment is a legal break point.
    """
    blocked = bytearray(len(text))
    for kind, start, end in scan_opaque_regions(text):
        if kind == "S":
            blocked[start:end] = b"\x01" * (end - start)
    return blocked


def render_ide_text(text: str) -> str:
    r"""Return *text* with CRLF terminators and IDE-safe line lengths.

    Lines longer than :data:`MAX_IDE_LINE_LENGTH` break at the last space
    within the limit. The scan never splits a string literal or a quoted
    identifier, and a line without a usable break space is emitted unchanged
    rather than cut mid-token.
    """
    normalized = _NEWLINE_RE.sub("\r\n", text)
    blocked = _blocked_spaces(normalized)
    lines: list[str] = []
    line_start = 0
    for raw in normalized.split("\r\n"):
        while len(raw) > MAX_IDE_LINE_LENGTH:
            last_space = -1
            for index in range(line_start, line_start + MAX_IDE_LINE_LENGTH):
                if normalized[index] == " " and not blocked[index]:
                    last_space = index - line_start
            if last_space <= 0:
                break
            lines.append(raw[:last_space])
            raw = raw[last_space + 1 :]
            line_start += last_space + 1
        lines.append(raw)
        line_start += len(raw) + 2

    return "\r\n".join(lines)
