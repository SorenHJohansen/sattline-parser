"""Graphics companion parsing and companion-path resolution.

A companion file (``.g`` / ``.y``) is scanned line by line for binding lines.
The scan is textual: every binding on every line is reported, in file order,
with its source span. Structural problems surface as ``GraphicsMessage``
values, never as exceptions.
"""

from __future__ import annotations

from pathlib import Path

from sattline_parser.api import read_text_cp1252
from sattline_parser.models.ast_model import GraphicsBinding

from .formats import graphics_ext_candidates
from .graphics_bindings import _parse_graphics_binding_line
from .models import GraphicsMessage, GraphicsModel, LoadMode


def resolve_graphics_companion_path(code_path: Path, *, mode: LoadMode) -> Path | None:
    """Resolve the graphics companion file for ``code_path``.

    The companion always sits in the same directory as the code file (a
    ``with_suffix`` substitution, never a root-ordered lookup). ``.x`` code
    resolves only to ``.y``; draft code falls back from ``.g`` to ``.y``; a
    ``.g`` / ``.y`` input resolves to itself.
    """
    if code_path.suffix.lower() in {".g", ".y"}:
        return code_path

    candidates = (".y",) if code_path.suffix.lower() == ".x" else graphics_ext_candidates(mode)
    for extension in candidates:
        candidate = code_path.with_suffix(extension)
        if candidate.exists():
            return candidate
    return None


def parse_graphics_text(text: str) -> GraphicsModel:
    """Scan ``.g`` / ``.y`` companion text into a ``GraphicsModel``.

    Every line is offered to the binding scanner, which understands the
    ``Var`` / ``Expr`` / ``Lit`` forms. Malformed lines and expression failures
    are reported as ``GraphicsMessage`` values rather than raised.
    """
    messages: list[GraphicsMessage] = []
    bindings: list[GraphicsBinding] = []
    for line_number, line_text in enumerate(text.splitlines(), start=1):
        row_bindings, binding_messages = _parse_graphics_binding_line(line_text, line=line_number)
        bindings.extend(row_bindings)
        messages.extend(binding_messages)
    return GraphicsModel(messages=tuple(messages), bindings=tuple(bindings))


def parse_graphics_file(file_path: Path) -> GraphicsModel:
    """Read and parse a ``.g`` / ``.y`` companion file.

    ``OSError`` and ``UnicodeError`` propagate to the caller (the loader maps
    them onto load errors); unreadable binding content becomes a
    ``GraphicsMessage``.
    """
    text = read_text_cp1252(file_path)
    return parse_graphics_text(text)


__all__ = ["parse_graphics_file", "parse_graphics_text", "resolve_graphics_companion_path"]
