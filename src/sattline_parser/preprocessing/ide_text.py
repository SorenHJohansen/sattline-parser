"""Layout decoded SattLine source so the IDE accepts it as a program file.

Decoding reproduces whatever line breaks the binary stream stored. Native
SattLine sources additionally follow two conventions the IDE relies on when
re-reading a saved file: CRLF terminators and no line longer than
:data:`MAX_IDE_LINE_LENGTH` characters. :func:`render_ide_text` applies that
layout and is safe to run on already-formatted text.
"""

from __future__ import annotations

import re

__all__ = ["MAX_IDE_LINE_LENGTH", "render_ide_text"]

#: Maximum emitted line length; genuine IDE-written sources stay below it.
MAX_IDE_LINE_LENGTH = 135

_NEWLINE_RE = re.compile(r"\r\n?|\n")


def render_ide_text(text: str) -> str:
    r"""Return *text* with CRLF terminators and IDE-safe line lengths.

    Lines longer than :data:`MAX_IDE_LINE_LENGTH` break at the last space
    within the limit. The scan never splits a double-quoted string literal,
    and a line without a usable break space is emitted unchanged rather than
    cut mid-token.
    """
    normalized = _NEWLINE_RE.sub("\r\n", text)
    lines: list[str] = []
    for raw in normalized.split("\r\n"):
        while len(raw) > MAX_IDE_LINE_LENGTH:
            in_string = False
            last_space = -1
            for k, ch in enumerate(raw[:MAX_IDE_LINE_LENGTH]):
                if in_string:
                    in_string = ch != '"'
                elif ch == '"':
                    in_string = True
                elif ch == " ":
                    last_space = k
            if last_space <= 0:
                break
            lines.append(raw[:last_space])
            raw = raw[last_space + 1 :]
        lines.append(raw)
    return "\r\n".join(lines)
