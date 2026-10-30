# pyright: reportPrivateUsage=false
"""Unit tests for Phase 4 graphics parsing (``project/graphics_*``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from lark import Tree

from sattline_parser.api import parse_source_text
from sattline_parser.models.ast_model import GraphicsBinding, SourceSpan
from sattline_parser.project import (
    GraphicsModel,
    LoadMode,
    parse_graphics_file,
    parse_graphics_text,
    resolve_graphics_companion_path,
)
from sattline_parser.project import graphics_bindings as bindings
from sattline_parser.project.graphics_parsing import _composite_markers as parsed_markers
from sattline_parser.project.graphics_parsing import correlate_composites


def _span_value(node: object, *, key: str = "span") -> SourceSpan:
    assert isinstance(node, dict)
    raw = cast(dict[str, object], node).get(key)
    assert isinstance(raw, SourceSpan)
    return raw


_HEADER = '" Syntax version 2.23, date: 2026-06-19-12:41:09.218 N "'


def _companion(*lines: str) -> str:
    """Companion text with the CRLF line endings the writer emits."""
    return "".join(f"{line}\r\n" for line in lines)


def _family_4() -> str:
    return _companion(" 4", " 0.0 0.0 1.0 1.0", " 1 1 1 X.Y", " 0")


_OG = _companion(
    _HEADER,
    "",
    " 5",
    " None  True  -2.40000E-01 1.08000E+00",
    "  1.38000E+00 1.28000E+00",
    " 0",
    " 2",
    " Var 0 12 OprPathIndex  Lit 0 2 -1     2",
    "1 1 Var  Invalid  6 PathOK",
    "2 1 Var  Invalid  9 PathNotOK",
    " 0",
    " None  True",
    "t",
    "           0",
)


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
    assert record.path_row_lines == (9, 10)
    assert [
        (row.index_token, row.kind, row.raw_text, row.index_value, row.span.line, row.span.column)
        for row in record.path_rows
    ] == [
        ("1", "variable_invalid", "PathOK", 1, 9, 21),
        ("2", "variable_invalid", "PathNotOK", 2, 10, 21),
    ]
    # The inline default payload is empty in this record, so it produces no row.
    assert record.default_path_row is None


def test_parse_graphics_errors_and_warnings_properties() -> None:
    model = parse_graphics_text(_family_4())
    assert isinstance(model, GraphicsModel)
    assert model.errors == ()
    assert model.warnings == ()
    assert model.bindings == ()


def test_parse_graphics_empty_text() -> None:
    model = parse_graphics_text("")
    assert model.bindings == ()
    assert model.messages == ()
    assert model.composite_records == ()
    assert model.picture_display_records == ()


def test_parse_graphics_unterminated_record_reports_error() -> None:
    model = parse_graphics_text(_companion(" 4", " 0.0 0.0 1.0 1.0", " 1 1 1 X.Y"))
    assert model.composite_records == ()
    assert len(model.messages) == 1
    message = model.messages[0]
    assert message.severity == "error"
    assert message.message == "Unterminated graphics record; expected trailing '0' line"
    assert message.line == 1


def test_parse_graphics_reports_malformed_field() -> None:
    model = parse_graphics_text(_companion(" 4", " not-a-number", " 1 1 1", " 0"))

    [message] = model.messages
    assert message.severity == "error"
    assert message.message == "Malformed graphics record: expected a floating-point number"
    assert (message.line, message.column) == (2, 1)


def test_parse_graphics_reports_unsupported_reader_as_warning() -> None:
    model = parse_graphics_text(_companion(" 1", " None  True  0.0 0.0", " 0.0 0.0", " 0", " 9 payload", " 0"))

    assert model.composite_records == ()
    [message] = model.messages
    assert message.severity == "warning"
    assert (
        message.message == "Graphics record content is not supported for family 1 discriminator 9; record scan stopped"
    )


def test_parse_graphics_records_separated_by_blank_line() -> None:
    model = parse_graphics_text(_companion(" 4", " 0.0 0.0 1.0 1.0", " 1 1 1 X.Y", " 0", "", *_family_4_lines()))

    assert [
        (c.record_index, c.family_code, c.record_start_line, c.record_end_line) for c in model.composite_records
    ] == [
        (1, "4", 1, 4),
        (2, "4", 6, 9),
    ]
    assert model.picture_display_records == ()
    assert model.messages == ()


def _family_4_lines() -> list[str]:
    return [" 4", " 0.0 0.0 1.0 1.0", " 1 1 1 X.Y", " 0"]


def test_parse_graphics_adjacent_records_need_no_blank_line() -> None:
    model = parse_graphics_text(_companion(" 4", " 0.0 0.0 1.0 1.0", " 1 1 1 X.Y", " 0", *_family_4_lines()))

    assert [(c.record_index, c.record_start_line, c.record_end_line) for c in model.composite_records] == [
        (1, 1, 4),
        (2, 5, 8),
    ]


def test_parse_graphics_record_ordinals_follow_file_order() -> None:
    model = parse_graphics_text(
        _companion(
            " 4",
            " 0.0 0.0 1.0 1.0",
            " 1 1 1 X.Y",
            " 0",
            " 5",
            " None  True  0.0 0.0",
            "  1.0 1.0",
            " 0",
            " 2",
            " None 0  None -1     0",
            " 0 path",
            " None  True",
            "t",
            "           0",
        )
    )

    assert [(c.record_index, c.ordinal, c.family_code) for c in model.composite_records] == [
        (1, 1, "4"),
        (2, 2, "5"),
    ]


def test_parse_graphics_subtype_1_is_not_a_picture_display() -> None:
    model = parse_graphics_text(
        _companion(
            " 5",
            " Lit  True  4 True  0.0 0.0",
            "  1.0 1.0",
            " -3",
            " 1",
            "WeekDayPres",
            "",
            "12",
            "2",
            " Var 0 5 DayNo ",
            " None -3 ",
            "1",
            "1",
            "Mandag",
            "           0",
        )
    )

    assert [(c.record_index, c.family_code) for c in model.composite_records] == [(1, "5")]
    assert model.picture_display_records == ()
    assert model.messages == ()


def test_parse_graphics_unsupported_subtype_reports_error() -> None:
    model = parse_graphics_text(_companion(" 5", " None  True  0.0 0.0", "  1.0 1.0", " 0", " 9"))

    assert model.composite_records == ()
    [message] = model.messages
    assert message.severity == "error"
    assert message.message == "Unsupported graphics record subtype 9"


def test_parse_graphics_keep_shape_is_case_insensitive() -> None:
    """The shape byte is only false for a lowercase ``f``; any other byte is true."""
    for shape in ("t", "T", " "):
        model = parse_graphics_text(
            _companion(
                " 5",
                " None  True  0.1 1.1",
                " 2.1 3.1",
                " 0",
                " 2",
                " Var 0 12 OprPathIndex  Lit 0 2 -1     0",
                " 0 default",
                " None  True",
                shape,
                "           0",
            )
        )
        [record] = model.picture_display_records
        assert record.record_index == 1
        assert model.messages == ()


def test_parse_graphics_literal_path_row() -> None:
    model = parse_graphics_text(
        _companion(
            " 5",
            " None  True  1 2",
            " 3 4",
            " 0",
            " 2",
            " Var 0 12 OprPathIndex  Lit 0 2 -1     1",
            "4 0 /pic/logo.bmp",
            " 0 default",
            " None  True",
            "f",
            "           0",
        )
    )

    [record] = model.picture_display_records
    assert record.path_row_lines == (7, 8)
    assert [
        (row.kind, row.raw_text, row.index_token, row.index_value, row.span.column) for row in record.path_rows
    ] == [
        ("literal", "/pic/logo.bmp", "4", 4, 5),
        ("literal", "default", "0", 0, 4),
    ]
    assert record.default_path_row is not None
    assert record.default_path_row.raw_text == "default"
    assert model.messages == ()


def test_parse_graphics_rows_from_bindings() -> None:
    model = parse_graphics_text(
        _companion(
            " 5",
            " None  True  1 2",
            " 3 4",
            " 0",
            " 2",
            " None 0  None -1     3",
            "1 1 Var  Invalid  6 PathOK",
            "2 1 Var  True  4 PVar",
            "3 1 Lit  True  4 text",
            " 0 default",
            " None  True",
            "f",
            "           0",
        )
    )

    [record] = model.picture_display_records
    assert [(row.index_token, row.kind, row.raw_text) for row in record.path_rows] == [
        ("1", "variable_invalid", "PathOK"),
        ("2", "variable", "PVar"),
        ("0", "literal", "default"),
    ]
    assert record.path_row_lines == (7, 8, 10)
    assert record.default_path_row == record.path_rows[-1]


def test_parse_graphics_blank_lines_do_not_change_record_structure() -> None:
    dense = _companion(*_family_4_lines(), *_family_4_lines())
    spaced = _companion("", *_family_4_lines(), "", "", *_family_4_lines(), "")

    def structure(text: str) -> list[tuple[int, str, int]]:
        model = parse_graphics_text(text)
        assert model.messages == ()
        return [
            (c.record_index, c.family_code, c.record_end_line - c.record_start_line) for c in model.composite_records
        ]

    assert structure(dense) == structure(spaced)


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
    path.write_bytes(_OG.encode("cp1252"))
    model = parse_graphics_file(path)
    assert len(model.picture_display_records) == 1


def test_parse_graphics_file_read_failure_propagates(tmp_path: Path) -> None:
    path = tmp_path / "Test.g"
    path.mkdir()
    with pytest.raises(OSError):
        parse_graphics_file(path)


def test_correlate_composites_binds_markers_to_records_by_ordinal():
    """Each CompositeObject marker consumes the next record, in order."""
    source = (
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-27-12:00:00.000, name: Composite"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "GraphObjects :\n"
        "   CompositeObject\n"
        "   CompositeObject Layer_ = 2\n"
        "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    model = parse_graphics_text(_companion(*_family_4_lines(), "", *_family_4_lines()))

    pairs, messages = correlate_composites(picture, model)

    assert [pair.marker_ordinal for pair in pairs] == [1, 2]
    assert [pair.record.ordinal for pair in pairs] == [1, 2]
    assert messages == ()


def test_correlate_composites_reports_unmatched_records_and_markers():
    source = (
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-27-12:00:00.000, name: Composite"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "GraphObjects :\n"
        "   CompositeObject\n"
        "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)

    no_records = parse_graphics_text("")
    _pairs, messages = correlate_composites(picture, no_records)
    assert [message.message for message in messages] == [
        "1 CompositeObject marker(s) in the source but only 0 companion record(s)"
    ]

    two_records = parse_graphics_text(_companion(*_family_4_lines(), "", *_family_4_lines()))
    pairs, messages = correlate_composites(picture, two_records)
    assert len(pairs) == 1
    assert [message.severity for message in messages] == ["error"]
    assert "has no matching CompositeObject marker" in messages[0].message


def _section_markers(picture: object) -> tuple[object, object, object]:
    """The single marker of the module type, of the submodule, and of the own def."""
    from sattline_parser.models.ast_model import BasePicture, SingleModule  # noqa: PLC0415

    assert isinstance(picture, BasePicture)
    type_def = picture.moduletype_defs[0].moduledef
    assert type_def is not None
    submodule = picture.submodules[0]
    assert isinstance(submodule, SingleModule)
    sub_def = submodule.moduledef
    assert sub_def is not None
    own_def = picture.moduledef
    assert own_def is not None
    type_objects = type_def.graph_objects
    sub_objects = sub_def.graph_objects
    own_objects = own_def.graph_objects
    assert type_objects is not None
    assert sub_objects is not None
    assert own_objects is not None
    return type_objects[0], sub_objects[0], own_objects[0]


def _nested_marker_source() -> str:
    """One CompositeObject in a module type, one in an inline submodule, one own."""
    return (
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-27-12:00:00.000, name: Order"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "TYPEDEFINITIONS\n"
        "   Child = MODULEDEFINITION DateCode_ 2\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   GraphObjects :\n"
        "      CompositeObject\n"
        "   ENDDEF (*Child*);\n"
        "SUBMODULES\n"
        "   Sub Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 3\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   GraphObjects :\n"
        "      CompositeObject\n"
        "   ENDDEF (*Sub*) ;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "GraphObjects :\n"
        "   CompositeObject\n"
        "ENDDEF (*BasePicture*);\n"
    )


def test_composite_markers_follow_the_declaration_order() -> None:
    """Module types first, then inline submodules, then the own ModuleDef.

    The companion cursor is opened before the recursive parse starts, so the
    first record belongs to the first marker the declaration loop reaches - a
    module type here, not the enclosing BasePicture's own ModuleDef.
    """
    picture = parse_source_text(_nested_marker_source())

    type_marker, sub_marker, own_marker = _section_markers(picture)

    markers = parsed_markers(picture)

    # Identity, not equality: every marker is an equal `GraphObject`.
    assert len(markers) == 3
    assert markers[0] is type_marker
    assert markers[1] is sub_marker
    assert markers[2] is own_marker


def test_composite_markers_carry_a_span_and_pairs_expose_it() -> None:
    """A paired marker must be pointable-at in the source (diagnostics/UI)."""
    picture = parse_source_text(
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-27-12:00:00.000, name: Span"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "GraphObjects :\n"
        "   CompositeObject Layer_ = 2\n"
        "ENDDEF (*BasePicture*);\n"
    )

    module_def = picture.moduledef
    assert module_def is not None
    graph_objects = module_def.graph_objects
    assert graph_objects is not None
    marker = graph_objects[0]
    assert marker.span is not None
    assert (marker.span.line, marker.span.column) == (8, 4)

    model = parse_graphics_text(_companion(*_family_4_lines()))
    pairs, messages = correlate_composites(picture, model)

    assert messages == ()
    assert pairs[0].marker_span == marker.span


def test_correlate_composites_pairs_records_in_declaration_order() -> None:
    picture = parse_source_text(_nested_marker_source())
    model = parse_graphics_text(_companion(*_family_4_lines(), *_family_4_lines(), *_family_4_lines()))

    pairs, messages = correlate_composites(picture, model)

    assert [pair.record.ordinal for pair in pairs] == [1, 2, 3]
    assert [pair.marker_ordinal for pair in pairs] == [1, 2, 3]
    assert messages == ()


def test_correlate_composites_walks_submodules_and_module_types():
    """Markers are collected in source parse order across definitions."""
    source = (
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-27-12:00:00.000, name: Composite"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "TYPEDEFINITIONS\n"
        "   Child = MODULEDEFINITION DateCode_ 2\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   GraphObjects :\n"
        "      CompositeObject\n"
        "   ENDDEF (*Child*);\n"
        "SUBMODULES\n"
        "   Sub Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 3\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   GraphObjects :\n"
        "      CompositeObject\n"
        "   ENDDEF (*Sub*) ;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    model = parse_graphics_text(_companion(*_family_4_lines(), "", *_family_4_lines()))

    pairs, _messages = correlate_composites(picture, model)

    assert [pair.marker_ordinal for pair in pairs] == [1, 2]


def test_correlate_composites_ignores_other_graph_primitives() -> None:
    """Only CompositeObject markers consume a record; other objects do not."""
    source = (
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-27-12:00:00.000, name: Composite"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "GraphObjects :\n"
        "   CompositeObject\n"
        "   RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 )\n"
        "   CompositeObject\n"
        "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    model = parse_graphics_text(_companion(*_family_4_lines(), *_family_4_lines()))

    pairs, messages = correlate_composites(picture, model)

    assert [pair.marker_ordinal for pair in pairs] == [1, 2]
    assert messages == ()


def test_correlate_composites_counts_every_moduledef_block():
    """A unit with several ModuleDef blocks contributes all of its markers."""
    source = (
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-27-12:00:00.000, name: Composite"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "GraphObjects :\n"
        "   CompositeObject\n"
        "ENDDEF (*BasePicture*);\n"
    )
    picture = parse_source_text(source)
    # Two ModuleDef blocks in one unit (the real corpus has up to dozens).
    picture.moduledefs = [picture.moduledef, picture.moduledef]  # type: ignore[list-item]
    model = parse_graphics_text(_companion(*_family_4_lines(), "", *_family_4_lines()))

    pairs, messages = correlate_composites(picture, model)

    assert [pair.marker_ordinal for pair in pairs] == [1, 2]
    assert messages == ()
