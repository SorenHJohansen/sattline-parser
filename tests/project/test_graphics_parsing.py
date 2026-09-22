# pyright: reportPrivateUsage=false
"""Unit tests for Phase 4 graphics parsing (``project/graphics_*``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from lark import Tree

from sattline_parser.models.ast_model import GraphicsBinding, SourceSpan
from sattline_parser.project import (
    GraphicsModel,
    LoadMode,
    parse_graphics_file,
    parse_graphics_text,
    resolve_graphics_companion_path,
)
from sattline_parser.project import graphics_bindings as bindings
from sattline_parser.project import graphics_parsing as parsing


def _span_value(node: object, *, key: str = "span") -> SourceSpan:
    assert isinstance(node, dict)
    raw = cast(dict[str, object], node).get(key)
    assert isinstance(raw, SourceSpan)
    return raw


_OG = """" Syntax version 2.23, date: 2026-06-19-12:41:09.218 N "

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


def test_parse_graphics_parity_fixture() -> None:
    model = parse_graphics_text(_OG)

    assert [
        (c.record_index, c.family_code, c.record_start_line, c.record_end_line) for c in model.composite_records
    ] == [(1, "5", 3, 14)]
    assert [(b.kind, b.raw_text) for b in model.bindings] == [
        ("var", "OprPathIndex"),
        ("lit", "-1"),
        ("var", "PathOK"),
        ("var", "PathNotOK"),
    ]
    assert model.messages == ()

    [record] = model.picture_display_records
    assert record.record_index == 1
    assert record.record_start_line == 3
    assert record.record_end_line == 14
    assert record.path_row_lines == (9, 10, 11)
    assert [
        (row.index_token, row.kind, row.raw_text, row.index_value, row.span.line, row.span.column)
        for row in record.path_rows
    ] == [
        ("1", "variable_invalid", "PathOK", 1, 9, 21),
        ("2", "variable_invalid", "PathNotOK", 2, 10, 21),
    ]


def test_parse_graphics_errors_and_warnings_properties() -> None:
    model = parse_graphics_text("5\none\n 0\n")
    assert isinstance(model, GraphicsModel)
    assert model.errors == ()
    assert model.warnings == ()


def test_parse_graphics_empty_text() -> None:
    model = parse_graphics_text("")
    assert model.bindings == ()
    assert model.messages == ()
    assert model.composite_records == ()
    assert model.picture_display_records == ()


def test_parse_graphics_unterminated_record_reports_error() -> None:
    model = parse_graphics_text(" 4\n some\n none\n")
    assert model.composite_records == ()
    assert len(model.messages) == 1
    message = model.messages[0]
    assert message.severity == "error"
    assert message.message == "Unterminated graphics record; expected trailing '0' line"
    assert message.line == 1


def test_parse_graphics_records_separated_by_blank_line() -> None:
    model = parse_graphics_text(" 1\n one\n 0\n\n 2\n two\n 0\n")
    assert [
        (c.record_index, c.family_code, c.record_start_line, c.record_end_line) for c in model.composite_records
    ] == [
        (1, "1", 1, 3),
        (2, "2", 5, 7),
    ]
    assert model.picture_display_records == ()
    assert model.messages == ()


def test_parse_graphics_short_record_skipped() -> None:
    model = parse_graphics_text(" 5\n 0\n t\n 0\n")
    assert [(c.record_index, c.family_code) for c in model.composite_records] == [(1, "5")]
    assert model.picture_display_records == ()
    assert model.messages == ()


def test_parse_graphics_subtype_mismatch_skips_picture_display() -> None:
    model = parse_graphics_text(" 5\n one\n two\n three\n four\n 0\n done\n t\n 0\n")
    assert [(c.record_index, c.family_code) for c in model.composite_records] == [(1, "5")]
    assert model.picture_display_records == ()
    assert model.messages == ()


def test_parse_graphics_missing_keep_shape_flag_reports_error() -> None:
    model = parse_graphics_text(" 5\n None  True  0 1\n 2 3\n 0\n 2\n row\n row\n None  X\n q\n 0\n")
    assert model.picture_display_records == ()
    assert [m.message for m in model.messages] == [
        "PictureDisplay record is missing the trailing KeepPictureShape flag"
    ]
    assert model.messages[0].line == 5


def test_parse_graphics_keep_shape_is_case_insensitive() -> None:
    model = parse_graphics_text(
        " 5\n None  True  0.1 1.1\n 2.1 3.1\n 0\n 2\n"
        " Var 0 12 OprPathIndex  Lit 0 2 -1     2\n"
        "1 1 Var  Invalid  4 OKAY\n 0\n None  T\nT\n 0\n"
    )
    [record] = model.picture_display_records
    assert record.path_row_lines == (7, 8)
    assert [(row.kind, row.raw_text) for row in record.path_rows] == [("variable_invalid", "OKAY")]
    assert model.messages == ()


def test_parse_graphics_literal_path_row() -> None:
    model = parse_graphics_text(
        " 5\n None  True  1 2\n 3 4\n 0\n 2\n"
        " Var 0 12 OprPathIndex  Lit 0 2 -1     2\n"
        "4 /pic/logo.bmp\n 0\n None  True\nf\n 0\n"
    )
    [record] = model.picture_display_records
    assert record.path_row_lines == (7, 8)
    assert [(row.kind, row.raw_text, row.index_token, row.index_value) for row in record.path_rows] == [
        ("literal", "/pic/logo.bmp", "4", 4)
    ]
    assert model.messages == ()


# --- companion-path resolution -------------------------------------------------


def test_resolve_graphics_companion_path_returns_input_for_graphics(tmp_path: Path) -> None:
    g_path = tmp_path / "X.g"
    y_path = tmp_path / "Y.y"
    g_path.write_text("", encoding="utf-8")
    y_path.write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(g_path, mode=LoadMode.DRAFT) == g_path
    assert resolve_graphics_companion_path(y_path, mode=LoadMode.OFFICIAL) == y_path


def test_resolve_graphics_companion_path_draft_prefers_g(tmp_path: Path) -> None:
    (tmp_path / "M.s").write_text("", encoding="utf-8")
    (tmp_path / "M.g").write_text("", encoding="utf-8")
    (tmp_path / "M.y").write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(tmp_path / "M.s", mode=LoadMode.DRAFT) == tmp_path / "M.g"


def test_resolve_graphics_companion_path_draft_falls_back_to_y(tmp_path: Path) -> None:
    (tmp_path / "M.s").write_text("", encoding="utf-8")
    (tmp_path / "M.y").write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(tmp_path / "M.s", mode=LoadMode.DRAFT) == tmp_path / "M.y"


def test_resolve_graphics_companion_path_official_only_y(tmp_path: Path) -> None:
    (tmp_path / "M.s").write_text("", encoding="utf-8")
    (tmp_path / "M.g").write_text("", encoding="utf-8")
    (tmp_path / "M.y").write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(tmp_path / "M.s", mode=LoadMode.OFFICIAL) == tmp_path / "M.y"


def test_resolve_graphics_companion_path_x_code_only_y(tmp_path: Path) -> None:
    (tmp_path / "M.x").write_text("", encoding="utf-8")
    (tmp_path / "M.g").write_text("", encoding="utf-8")
    (tmp_path / "M.y").write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(tmp_path / "M.x", mode=LoadMode.DRAFT) == tmp_path / "M.y"


def test_resolve_graphics_companion_path_absent(tmp_path: Path) -> None:
    (tmp_path / "M.s").write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(tmp_path / "M.s", mode=LoadMode.DRAFT) is None


# --- row parsing helpers --------------------------------------------------------


def test_parse_picture_display_row_accepts_nested_invalid_variable_paths() -> None:
    row = parsing._parse_picture_display_row("2 1 Var Invalid 9 PathNotOK", record_index=1, line=10)

    assert row is not None
    assert row.index_token == "2"
    assert row.index_value == 2
    assert row.kind == "variable_invalid"
    assert row.raw_text == "PathNotOK"
    assert row.span.line == 10
    assert row.span.column == 19


def test_parse_picture_display_row_keeps_plain_invalid_variable_paths_excluded() -> None:
    assert parsing._parse_picture_display_row("1 Var  Invalid  7 PathAIT", record_index=1, line=3) is None


def test_parse_picture_display_row_variable_kind() -> None:
    row = parsing._parse_picture_display_row("3 Var True 5 PVar", record_index=1, line=2)
    assert row is not None
    assert row.kind == "variable"
    assert row.raw_text == "PVar"
    assert row.index_value == 3


def test_parse_picture_display_row_non_numeric_index_token() -> None:
    row = parsing._parse_picture_display_row("abc Var True 5 PVar", record_index=1, line=2)
    assert row is not None
    assert row.index_value is None


def test_parse_picture_display_row_negative_index() -> None:
    row = parsing._parse_picture_display_row("-1 1 Var Invalid 6 PathXY", record_index=1, line=2)
    assert row is not None
    assert row.index_value == -1


def test_parse_picture_display_row_unknown_binding_meta_excluded() -> None:
    assert parsing._parse_picture_display_row("1 Var X 5 PVar", record_index=1, line=2) is None


def test_parse_picture_display_row_non_var_binding_excluded() -> None:
    assert parsing._parse_picture_display_row("1 Lit True 4 /x", record_index=1, line=2) is None


def test_parse_picture_display_row_blank_and_single_token_excluded() -> None:
    assert parsing._parse_picture_display_row("   ", record_index=1, line=2) is None
    assert parsing._parse_picture_display_row("2", record_index=1, line=2) is None


def test_parse_picture_display_row_literal_kind() -> None:
    row = parsing._parse_picture_display_row("4 /pic/logo.bmp", record_index=1, line=2)
    assert row is not None
    assert row.kind == "literal"
    assert row.raw_text == "/pic/logo.bmp"
    assert row.index_value == 4


def test_parse_picture_display_row_nested_index_literal() -> None:
    row = parsing._parse_picture_display_row("4 7 /pic/logo.bmp", record_index=1, line=2)
    assert row is not None
    assert row.raw_text == "/pic/logo.bmp"
    assert row.index_value == 4


def test_parse_picture_display_row_literal_lookup_rejected() -> None:
    assert parsing._parse_picture_display_row("3 Var  x", record_index=1, line=2) is None


def test_extract_literal_path_rejects_var_lit_none_payloads() -> None:
    assert parsing._extract_literal_path("1 Var  x") is None
    assert parsing._extract_literal_path("1 Lit  x") is None
    assert parsing._extract_literal_path("1 None  True") is None
    assert parsing._extract_literal_path("1 /pic/x.bmp") == "/pic/x.bmp"
    assert parsing._extract_literal_path("single") is None


def test_extract_literal_path_nested_index_stripped() -> None:
    assert parsing._extract_literal_path("1 5 /pic/x.bmp") == "/pic/x.bmp"


def test_split_nested_picture_display_payload() -> None:
    assert parsing._split_nested_picture_display_payload("12 OprPathIndex") == ("12", "OprPathIndex")
    assert parsing._split_nested_picture_display_payload("-3 rest") == ("-3", "rest")
    assert parsing._split_nested_picture_display_payload("abc") == (None, "abc")
    assert parsing._split_nested_picture_display_payload("x rest") == (None, "x rest")


# --- binding parsing ------------------------------------------------------------


def test_coerce_graphics_literal() -> None:
    assert bindings._coerce_graphics_literal("true") is True
    assert bindings._coerce_graphics_literal("FALSE") is False
    assert bindings._coerce_graphics_literal("+7") == 7
    assert bindings._coerce_graphics_literal("-3") == -3
    assert bindings._coerce_graphics_literal("1.5") == 1.5
    assert bindings._coerce_graphics_literal("1.5e2") == 150.0
    assert bindings._coerce_graphics_literal("1e3") == "1e3"
    assert bindings._coerce_graphics_literal("2m") == "2m"
    assert bindings._coerce_graphics_literal("") == ""


def test_normalize_graphics_expression() -> None:
    assert bindings._normalize_graphics_expression("not ZoomableVar and other") == "NOT ZoomableVar AND other"
    assert bindings._normalize_graphics_expression("plain") == "plain"


def test_unwrap_expression_root() -> None:
    assert bindings._unwrap_expression_root("x") == "x"
    child = SourceSpan(start=0, end=0, line=1, column=1)
    assert bindings._unwrap_expression_root(Tree("expression", [child])) is child
    empty_tree: Tree[object] = Tree("expression", [])
    assert bindings._unwrap_expression_root(empty_tree) is empty_tree


def test_parse_graphics_binding_match_var() -> None:
    match = bindings._BINDING_LINE_RE.search(" Var  True  5 HVar tail")
    assert match is not None
    binding, messages = bindings._parse_graphics_binding_match(match.string, line=7, match=match)
    assert messages == ()
    assert binding is not None
    assert binding.kind == "var"
    assert binding.raw_text == "HVar"
    assert binding.value == {"var_name": "HVar", "span": binding.span}


def test_parse_graphics_binding_match_lit() -> None:
    match = bindings._BINDING_LINE_RE.search("  Lit  True  4 True ")
    assert match is not None
    binding, _ = bindings._parse_graphics_binding_match(match.string, line=2, match=match)
    assert binding is not None
    assert binding.kind == "lit"
    assert binding.value is True


def test_parse_graphics_binding_match_expr_success() -> None:
    text = "  Expr  True  15 not ZoomableVar"
    match = bindings._BINDING_LINE_RE.search(text)
    assert match is not None
    binding, messages = bindings._parse_graphics_binding_match(text, line=5, match=match)
    assert messages == ()
    assert binding is not None
    assert binding.kind == "expr"
    assert binding.raw_text == "not ZoomableVar"
    assert not isinstance(binding.value, str)
    assert binding.span is not None
    assert binding.span.line == 5


def test_parse_graphics_binding_match_expr_failure_warns() -> None:
    text = "  Expr  True  3 ((("
    match = bindings._BINDING_LINE_RE.search(text)
    assert match is not None
    binding, messages = bindings._parse_graphics_binding_match(text, line=9, match=match)
    assert binding is not None
    assert binding.kind == "expr"
    assert binding.value == "((("
    assert len(messages) == 1
    assert messages[0].severity == "warning"
    assert messages[0].message.startswith("Could not parse graphics expression '(((':")
    assert messages[0].line == 9


def test_parse_graphics_binding_match_negative_length() -> None:
    match = bindings._BINDING_LINE_RE.search("  Expr  True  -1  x")
    assert match is not None
    assert bindings._parse_graphics_binding_match(match.string, line=1, match=match) == (None, ())


def test_parse_graphics_binding_match_length_overflow_and_empty() -> None:
    overflow_match = bindings._BINDING_LINE_RE.search("  Var  True  99 x")
    assert overflow_match is not None
    binding, messages = bindings._parse_graphics_binding_match(overflow_match.string, line=1, match=overflow_match)
    assert messages == ()
    assert binding is not None
    assert binding.raw_text == "x"

    empty_match = bindings._BINDING_LINE_RE.search("  Lit  True  0  ")
    assert empty_match is not None
    assert bindings._parse_graphics_binding_match(empty_match.string, line=1, match=empty_match) == (None, ())


def test_parse_graphics_binding_line_multiple_bindings() -> None:
    text = " Var 0 12 OprPathIndex  Lit 0 2 -1     2"
    bindings_, messages = bindings._parse_graphics_binding_line(text, line=8)
    assert messages == ()
    assert [(b.kind, b.raw_text) for b in bindings_] == [("var", "OprPathIndex"), ("lit", "-1")]


# --- expression span offsetting -------------------------------------------------


def test_offset_source_spans_dict_and_span_key() -> None:
    node = {"var_name": "X", "span": SourceSpan(start=0, end=0, line=1, column=2)}
    result = bindings._offset_source_spans(node, line_offset=3, column_offset=5)
    span = _span_value(result)
    assert span.line == 3
    assert span.column == 6


def test_offset_source_spans_dict_non_span_key_is_str() -> None:
    node: dict[str, object] = {"span": "not-a-span"}
    result = bindings._offset_source_spans(node, line_offset=1, column_offset=1)
    assert result == node


def test_offset_source_spans_list_and_tuple() -> None:
    items: list[object] = [{"span": SourceSpan(start=0, end=0, line=1, column=1), "name": "X"}]
    bindings._offset_source_spans(items, line_offset=2, column_offset=1)
    inner = _span_value(items[0])
    assert inner.line == 2
    assert inner.column == 1

    shared = SourceSpan(start=0, end=0, line=1, column=1)
    raw = ({"span": shared, "n": 1}, {"span": shared, "n": 2})
    rebuilt = bindings._offset_source_spans(raw, line_offset=2, column_offset=1)
    assert isinstance(rebuilt, tuple)
    assert rebuilt is not raw
    assert rebuilt[0] is raw[0]
    assert rebuilt[1] is raw[1]
    first_span = raw[0]["span"]
    assert isinstance(first_span, SourceSpan)
    assert first_span.line == 2


def test_offset_source_spans_bare_span_is_identity() -> None:
    span = SourceSpan(start=0, end=0, line=1, column=1)
    result = bindings._offset_source_spans(span, line_offset=5, column_offset=3)
    assert result is span
    assert span.line == 1


def test_offset_source_spans_tree() -> None:
    tree = Tree("step", [{"span": SourceSpan(start=0, end=0, line=1, column=1), "value": "x"}])
    result = bindings._offset_source_spans(tree, line_offset=4, column_offset=1)
    tree_result = cast(Tree[object], result)
    inner = _span_value(tree_result.children[0])
    assert inner.line == 4


def test_offset_source_spans_object_with_children_unchanged_and_changed() -> None:
    class WithChildren:
        children: list[object]

        def __init__(self, children: list[object]) -> None:
            self.children = children

    node = WithChildren([1, 2])
    assert bindings._offset_source_spans(node, line_offset=1, column_offset=1) is node

    span_node = WithChildren([("payload", {"span": SourceSpan(start=0, end=0, line=1, column=1)})])
    result = bindings._offset_source_spans(span_node, line_offset=2, column_offset=1)
    assert result is span_node
    entry = span_node.children[0]
    assert isinstance(entry, tuple)
    payload = cast(tuple[object, object], entry)[1]
    inner = _span_value(payload)
    assert inner.line == 2


def test_offset_source_spans_object_with_readonly_children() -> None:
    class ReadOnlyChildren:
        @property
        def children(self) -> tuple[tuple[object, object], ...]:
            return (("payload", {"span": SourceSpan(start=0, end=0, line=1, column=1)}),)

    node = ReadOnlyChildren()
    assert bindings._offset_source_spans(node, line_offset=1, column_offset=1) is node


def test_offset_source_spans_dataclass_span_field_not_a_span() -> None:
    @dataclass(frozen=True)
    class WithStringSpan:
        span: object
        other: int

    node = WithStringSpan("kept", 1)
    assert bindings._offset_source_spans(node, line_offset=2, column_offset=1) is node


def test_offset_source_spans_dataclass_replace() -> None:
    binding = GraphicsBinding(
        kind="var",
        raw_text="X",
        value=None,
        span=SourceSpan(start=0, end=0, line=4, column=1),
    )
    result = bindings._offset_source_spans(binding, line_offset=5, column_offset=1)
    assert result is not binding
    assert isinstance(result, GraphicsBinding)
    assert result.span is not None
    assert result.span.line == 8
    assert result.raw_text == "X"


def test_offset_source_spans_dataclass_unchanged() -> None:
    @dataclass(frozen=True)
    class Plain:
        x: int

    node = Plain(5)
    assert bindings._offset_source_spans(node, line_offset=1, column_offset=1) is node


def test_offset_source_spans_dataclass_replace_typeerror() -> None:
    @dataclass
    class InitFalse:
        span: SourceSpan = field(default_factory=lambda: SourceSpan(start=0, end=0, line=1, column=1))
        other: int = field(init=False, default=5)

    node = InitFalse()
    assert bindings._offset_source_spans(node, line_offset=2, column_offset=1) is node


def test_offset_source_spans_dict_object_and_scalar() -> None:
    class WithDict:
        def __init__(self) -> None:
            self.meta: dict[str, list[object]] = {"nested": [{"span": SourceSpan(start=0, end=0, line=1, column=1)}]}

    node = WithDict()
    assert bindings._offset_source_spans(node, line_offset=3, column_offset=1) is node
    nested = node.meta["nested"]
    inner = _span_value(nested[0])
    assert inner.line == 3

    assert bindings._offset_source_spans(5, line_offset=1, column_offset=1) == 5


def test_offset_source_spans_later_line_column_unchanged() -> None:
    span = SourceSpan(start=0, end=0, line=3, column=9)
    result = bindings._offset_source_spans({"span": span}, line_offset=10, column_offset=5)
    offset = _span_value(result)
    assert offset.line == 12
    assert offset.column == 9


# --- file parsing ----------------------------------------------------------------


def test_parse_graphics_file_reads_disk(tmp_path: Path) -> None:
    path = tmp_path / "Test.g"
    path.write_text(_OG, encoding="utf-8")
    model = parse_graphics_file(path)
    assert len(model.picture_display_records) == 1


def test_parse_graphics_file_read_failure_propagates(tmp_path: Path) -> None:
    path = tmp_path / "Test.g"
    path.mkdir()
    with pytest.raises(OSError):
        parse_graphics_file(path)
