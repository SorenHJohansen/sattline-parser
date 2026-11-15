"""AST formatting helpers for parser-core.

Renders nested expression trees, SFC node lists, and whole files into a
readable, SattLine-like notation. This package is a leaf: it only depends on the
grammar constants and the AST models.
"""

from __future__ import annotations

from .formatter import format_expr, format_list, format_optional, format_seq_nodes
from .source import UnsupportedFormattingError, format_module, format_source

__all__ = [
    "UnsupportedFormattingError",
    "format_expr",
    "format_list",
    "format_module",
    "format_optional",
    "format_seq_nodes",
    "format_source",
]
