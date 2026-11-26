# pyright: reportPrivateUsage=false
"""The public ``SourceDocument`` contract: a valid map, and the line rule."""

from __future__ import annotations

import pytest
from lark import Token
from lark.tree import Tree

from sattline_parser import parse_source_text
from sattline_parser.source_document import (
    GENERATED,
    SourceDocument,
    remap_tree_to_original,
    split_source_lines,
)


def test_a_valid_map_maps_positions_and_ranges() -> None:
    doc = SourceDocument("AxB", "AB", (0, 2))

    assert doc.char_map == (0, 2)
    assert doc.map_position(0) == 0
    assert doc.map_position(1) == 2
    assert doc.map_range(0, 2) == (0, 3)


def test_a_map_with_generated_characters_is_valid() -> None:
    doc = SourceDocument("AB", "A;;B", (0, GENERATED, GENERATED, 1))

    assert doc.map_position(1) == 0
    assert doc.map_range(1, 3) == (0, 2)


def test_a_non_monotone_map_is_rejected() -> None:
    with pytest.raises(ValueError, match="char_map must be strictly increasing"):
        SourceDocument("aXYb", "abXY", (0, 3, 1, 2))


def test_a_repeated_original_offset_is_rejected() -> None:
    """Two normalized characters cannot claim one original character."""
    with pytest.raises(ValueError, match="strictly increasing"):
        SourceDocument("abcdef", "Xbcdef!", (0, 0, 2, 3, 4, 5, -1))


def test_an_out_of_range_offset_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside original_text"):
        SourceDocument("abc", "abc", (0, 1, 3))


def test_a_negative_entry_that_is_not_generated_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside original_text"):
        SourceDocument("abc", "abc", (0, -2, 1))


def test_line_and_column_use_every_line_terminator() -> None:
    doc = SourceDocument("a\rb\r\nc\nd", "a\rb\r\nc\nd", (0, 1, 2, 3, 4, 5, 6, 7))

    assert doc.line_col(0) == (1, 1)
    assert doc.line_col(2) == (2, 1)
    assert doc.line_col(5) == (3, 1)
    assert doc.line_col(7) == (4, 1)
    assert split_source_lines("a\rb\r\nc\nd") == ("a", "b", "c", "d")


def test_a_cr_only_document_reports_the_expected_line_and_column() -> None:
    doc = SourceDocument("first\rsecond\rthird", "first\rsecond\rthird", tuple(range(18)))

    assert doc.line_col(0) == (1, 1)
    assert doc.line_col(6) == (2, 1)
    assert doc.line_col(13) == (3, 1)
    assert doc.line_col(15) == (3, 3)
    assert split_source_lines("first\rsecond\rthird") == ("first", "second", "third")


def test_identity_remap_rewrites_lines_only_for_a_lone_cr() -> None:
    """CRLF is already LF-based for Lark, so only a lone CR needs a rewrite."""
    crlf = Tree("wrapper", [Token("NAME", "b", start_pos=3, end_pos=4, line=9, column=1)])
    remap_tree_to_original(crlf, SourceDocument.identity("a\r\nb"))
    crlf_token = crlf.children[0]
    assert isinstance(crlf_token, Token)
    assert crlf_token.line == 9

    cr = Tree("wrapper", [Token("NAME", "b", start_pos=2, end_pos=3, line=9, column=1)])
    remap_tree_to_original(cr, SourceDocument.identity("a\rb"))
    cr_token = cr.children[0]
    assert isinstance(cr_token, Token)
    assert cr_token.line == 2


def test_a_cr_only_source_remaps_ast_lines() -> None:
    """A successful parse uses the same line rule as line_col, not Lark's LF count."""
    lines = (
        '"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"',
        '"Original file date: ---"',
        '"Program date: 2026-04-23-12:00:00.000, name: Prog"',
        "",
        "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1",
        "ModuleDef",
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )",
        "ENDDEF (*BasePicture*);",
        "",
    )
    picture = parse_source_text("\r".join(lines))

    assert picture.header.declaration_span is not None
    assert picture.header.declaration_span.line == 5


def test_a_trailing_terminator_is_an_empty_boundary_line() -> None:
    doc = SourceDocument.identity("a\r")

    assert doc.line_col(2) == (2, 1)
    assert split_source_lines("a\r") == ("a", "")


def test_a_negative_range_clamps_to_the_start_on_a_mapped_document() -> None:
    doc = SourceDocument("abc", "bc", (1, 2))

    assert doc.map_range(-2, -1) == (1, 1)
    assert doc.map_range(-2, 0) == (1, 1)
