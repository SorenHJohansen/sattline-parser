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


def _breakable_spaces(line: str) -> list[int]:
    """Return the indices of spaces that may become a line break.

    A space inside a string literal or a quoted identifier is not a break
    point: splitting there would cut one token into two. The regions come from
    the same lexically aware scanner the compressed decoder uses, so a
    ``'quoted identifier'`` is protected exactly where the grammar reads one.
    Comment bodies are not protected: breaking a comment line keeps it legal.
    """
    blocked = bytearray(len(line))
    for kind, start, end in scan_opaque_regions(line):
        if kind == "S":
            blocked[start:end] = b"\x01" * (end - start)
    return [index for index, character in enumerate(line) if character == " " and not blocked[index]]


def render_ide_text(text: str) -> str:
    r"""Return *text* with CRLF terminators and IDE-safe line lengths.

    Lines longer than :data:`MAX_IDE_LINE_LENGTH` break at the last space
    within the limit. The scan never splits a string literal or a quoted
    identifier, and a line without a usable break space is emitted unchanged
    rather than cut mid-token.
    """
    normalized = _NEWLINE_RE.sub("\r\n", text)
    lines: list[str] = []
    for raw in normalized.split("\r\n"):
        while len(raw) > MAX_IDE_LINE_LENGTH:
            last_space = -1
            for index in _breakable_spaces(raw):
                if index >= MAX_IDE_LINE_LENGTH:
                    break
                last_space = index
            if last_space <= 0:
                break
            lines.append(raw[:last_space])
            raw = raw[last_space + 1 :]
        lines.append(raw)
    return "\r\n".join(lines)
