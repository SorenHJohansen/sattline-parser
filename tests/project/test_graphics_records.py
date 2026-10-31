# pyright: reportPrivateUsage=false
"""Structural graphics record scanning (``project/graphics_parsing``)."""

from __future__ import annotations

import pytest

from sattline_parser.project import graphics_parsing as parsing
from sattline_parser.project import parse_graphics_text

_PICTURE_DISPLAY_TEXT = """\" Syntax version 2.23, date: 2026-06-19-12:41:09.218 N \"

 5
 None  True  -2.40000E-01 1.08000E+00
  1.38000E+00 1.28000E+00
 0
 2
 Var 0 12 OprPathIndex  Lit 0 2 -1     2
1 1 Var  Invalid  6 PathOK
2 1 Var  Invalid  9 PathNotOK
 0
 None  True
t
           0
"""


def _record(*body: str) -> str:
    return "\n".join(body) + "\n"


def test_picture_display_record_is_extracted() -> None:
    model = parse_graphics_text(_PICTURE_DISPLAY_TEXT)

    assert len(model.composite_records) == 1
    composite = model.composite_records[0]
    assert (composite.record_index, composite.family_code, composite.start_line, composite.end_line) == (1, "5", 3, 14)

    assert len(model.picture_display_records) == 1
    picture = model.picture_display_records[0]
    assert (picture.record_index, picture.start_line, picture.end_line) == (1, 3, 14)
    assert [(row.index_token, row.index_value, row.kind, row.raw_text) for row in picture.path_rows] == [
        ("1", 1, "variable_invalid", "PathOK"),
        ("2", 2, "variable_invalid", "PathNotOK"),
    ]
    assert picture.path_rows[0].span.line == 9
    assert picture.path_rows[1].span.line == 10


def test_non_picture_record_is_composite_only() -> None:
    model = parse_graphics_text(_record("1", "alpha", "0", ""))

    assert [(record.record_index, record.family_code) for record in model.composite_records] == [(1, "1")]
    assert model.picture_display_records == ()
    assert model.messages == ()


def test_short_picture_record_is_skipped() -> None:
    model = parse_graphics_text(_record("5", "a", "b", "0", ""))

    assert len(model.composite_records) == 1
    assert model.picture_display_records == ()
    assert model.messages == ()


def test_picture_record_with_other_subtype_is_skipped() -> None:
    model = parse_graphics_text(_record("5", "a", "b", "c", "3", "d", "t", "0", ""))

    assert len(model.composite_records) == 1
    assert model.picture_display_records == ()
    assert model.messages == ()


def test_unterminated_record_reports_an_error() -> None:
    model = parse_graphics_text(_record("5", "alpha"))

    assert model.composite_records == ()
    assert model.picture_display_records == ()
    assert len(model.errors) == 1
    assert model.errors[0].line == 1
    assert "Unterminated graphics record" in model.errors[0].message


def test_missing_keep_shape_flag_reports_an_error() -> None:
    model = parse_graphics_text(_record("5", "a", "b", "c", "2", "d", "x", "0", ""))

    assert len(model.composite_records) == 1
    assert model.picture_display_records == ()
    assert len(model.errors) == 1
    assert model.errors[0].line == 5
    assert "KeepPictureShape" in model.errors[0].message


def test_variable_path_row_is_extracted() -> None:
    model = parse_graphics_text(_record("5", "a", "b", "c", "2", "d", "1 1 Var True 6 Path", "None True", "t", "0", ""))

    picture = model.picture_display_records[0]
    assert [(row.kind, row.raw_text) for row in picture.path_rows] == [("variable", "Path")]


def test_literal_path_row_is_extracted() -> None:
    model = parse_graphics_text(_record("5", "a", "b", "c", "2", "d", "1 1 scr:face.wmf", "None True", "t", "0", ""))

    picture = model.picture_display_records[0]
    assert [(row.kind, row.index_value, row.raw_text) for row in picture.path_rows] == [("literal", 1, "scr:face.wmf")]


def test_binding_warnings_and_structural_errors_share_the_message_list() -> None:
    text = " Expr  True  3 (((\n5\nalpha\n"
    model = parse_graphics_text(text)

    assert [message.severity for message in model.messages] == ["warning", "error"]
    assert model.warnings[0].message.startswith("Could not parse graphics expression")
    assert model.errors[0].message.startswith("Unterminated graphics record")


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ("   ", None),
        ("1", None),
        ("1 Var Invalid 6 X", None),
        ("1 Var Weird 6 X", None),
        ("1 Lit True 4 X", None),
        ("1 None True", None),
    ],
)
def test_malformed_path_rows_are_rejected(row: str, expected: object) -> None:
    assert parsing._parse_picture_display_row(row, record_index=1, line=1) == expected


def test_path_row_with_nested_index_and_valid_binding_is_a_variable() -> None:
    row = parsing._parse_picture_display_row("1 2 Var 1 6 X", record_index=1, line=4)
    assert row is not None
    assert (row.kind, row.index_token, row.index_value, row.raw_text) == ("variable", "1", 1, "X")


def test_path_row_with_non_numeric_index_token_keeps_none() -> None:
    row = parsing._parse_picture_display_row("x 1 Var True 6 X", record_index=1, line=4)
    assert row is not None
    assert row.index_value is None


def test_extract_literal_path_rejects_missing_payloads() -> None:
    assert parsing._extract_literal_path("x") is None
    assert parsing._extract_literal_path("1 Var True 6 X") is None
    assert parsing._extract_literal_path("1 Lit True 4 X") is None
    assert parsing._extract_literal_path("1 None True") is None


def test_extract_literal_path_unwraps_a_nested_index() -> None:
    assert parsing._extract_literal_path("1 2 scr:face.wmf") == "scr:face.wmf"


def test_split_nested_picture_display_payload_branches() -> None:
    assert parsing._split_nested_picture_display_payload("single") == (None, "single")
    assert parsing._split_nested_picture_display_payload("x payload") == (None, "x payload")
    assert parsing._split_nested_picture_display_payload("3 payload") == ("3", "payload")


def test_find_record_end_ignores_a_terminator_followed_by_content() -> None:
    lines = ["5", "a", "0", "b", "0", ""]
    assert parsing._find_record_end(lines, 0) == 4


def test_find_record_end_returns_none_without_a_terminator() -> None:
    assert parsing._find_record_end(["5", "a"], 0) is None
