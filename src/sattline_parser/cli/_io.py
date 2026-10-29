"""Input resolution and path display for the CLI."""

from __future__ import annotations

import sys
from pathlib import Path

from sattline_parser.api import read_text_cp1252

from ._errors import CliError

__all__ = ["display_path", "read_source"]

_STDIN = "-"


def read_source(target: str, *, name: str | None) -> tuple[str, str]:
    """Return ``(display name, text)`` for a path or ``-`` for stdin.

    Files are decoded exactly like the project loader (strict Windows-1252), so
    the CLI sees the same bytes the parser does. Stdin requires ``--name``
    because every finding must be attributable to something.
    """
    if target == _STDIN:
        if name is None:
            raise CliError("reading from stdin requires --stdin-name so findings carry a path")
        return name, sys.stdin.buffer.read().decode("cp1252")
    path = Path(target)
    try:
        return str(path), read_text_cp1252(path)
    except OSError as exc:
        raise CliError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise CliError(f"{path}: not valid Windows-1252 (byte {exc.start}: {exc.reason})") from exc


def display_path(name: str, *, absolute: bool) -> str:
    """Render a source name according to ``--paths`` (``<stdin>`` stays as-is)."""
    if not absolute or name.startswith("<"):
        return name
    return str(Path(name).resolve())
