"""Input resolution and path display for the CLI."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from sattline_parser.api import decode_source_bytes
from sattline_parser.preprocessing import PreprocessError, is_coded

from ._errors import CliError

__all__ = ["Source", "display_path", "read_source", "read_source_path"]

_STDIN = "-"


@dataclass(frozen=True, slots=True)
class Source:
    """One resolved input: its display name, parse text and on-disk flavor."""

    name: str
    text: str
    #: True when the input was a byte-coded (binary-framed) stream.
    coded: bool
    #: Length of the input as stored: bytes on disk, characters on stdin.
    original_length: int


def read_source(target: str, *, name: str | None) -> Source:
    """Return the resolved :class:`Source` for a path or ``-`` for stdin.

    Files are decoded exactly like ``parse_source_file``: a byte-coded stream is
    decoded first, and plain or marker-compressed text is returned as written so
    provenance spans keep pointing into the original source. Stdin requires
    ``--stdin-name`` because every finding must be attributable to something.
    """
    if target == _STDIN:
        if name is None:
            raise CliError("reading from stdin requires --stdin-name so findings carry a path")
        raw = sys.stdin.buffer.read()
        return _source(raw, name)
    return read_source_path(Path(target))


def read_source_path(path: Path) -> Source:
    """Read one file into a :class:`Source`, mapping I/O problems to ``CliError``."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CliError(f"cannot read {path}: {exc.strerror or exc}") from exc
    return _source(raw, str(path))


def _source(raw: bytes, name: str) -> Source:
    try:
        text = decode_source_bytes(raw)
    except UnicodeDecodeError as exc:
        raise CliError(f"{name}: not valid Windows-1252 (byte {exc.start}: {exc.reason})") from exc
    except PreprocessError as exc:
        raise CliError(f"{name}: cannot decode: {exc}") from exc
    return Source(name=name, text=text, coded=is_coded(raw), original_length=len(raw))


def display_path(name: str, *, absolute: bool) -> str:
    """Render a source name according to ``--paths`` (``<stdin>`` stays as-is)."""
    if not absolute or name.startswith("<"):
        return name
    return str(Path(name).resolve())
