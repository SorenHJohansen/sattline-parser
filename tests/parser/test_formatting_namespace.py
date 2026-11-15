"""Tests for the public ``sattline_parser.formatting`` namespace."""

from __future__ import annotations

import sattline_parser.formatting as formatting
from sattline_parser.formatting import formatter, source

_EXPECTED_ALL = {
    "UnsupportedFormattingError",
    "format_expr",
    "format_list",
    "format_module",
    "format_optional",
    "format_seq_nodes",
    "format_source",
}
_IMPLEMENTATIONS = {
    "UnsupportedFormattingError": source,
    "format_module": source,
    "format_source": source,
}


def test_export_set_matches_the_documented_surface() -> None:
    assert set(formatting.__all__) == _EXPECTED_ALL


def test_every_export_resolves_to_the_implementation() -> None:
    for name in formatting.__all__:
        module = _IMPLEMENTATIONS.get(name, formatter)
        assert getattr(formatting, name) is getattr(module, name), name


def test_all_names_are_unique_and_sorted() -> None:
    assert formatting.__all__ == sorted(formatting.__all__)
    assert len(formatting.__all__) == len(set(formatting.__all__))
