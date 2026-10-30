# pyright: reportPrivateUsage=false
"""Unit tests for graphics companion parsing (``project/graphics_*``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from lark import Tree

from sattline_parser.models.ast_model import GraphicsBinding, SourceSpan
from sattline_parser.project import LoadMode, parse_graphics_file, parse_graphics_text, resolve_graphics_companion_path
from sattline_parser.project import graphics_bindings as bindings


def _span_value(node: object, *, key: str = "span") -> SourceSpan:
    assert isinstance(node, dict)
    raw = cast(dict[str, object], node).get(key)
    assert isinstance(raw, SourceSpan)
    return raw


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


def test_offset_source_spans_falls_back_when_replace_rejects_a_field() -> None:
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


# --- companion scanning ----------------------------------------------------------


def test_parse_graphics_text_reports_bindings_in_file_order() -> None:
    text = '" Syntax version 2.23 "\r\n Var 0 12 OprPathIndex  Lit 0 2 -1     2\r\n Var 0 8 OtherVar\r\n'

    model = parse_graphics_text(text)

    assert [(binding.kind, binding.raw_text) for binding in model.bindings] == [
        ("var", "OprPathIndex"),
        ("lit", "-1"),
        ("var", "OtherVar"),
    ]
    assert model.messages == ()
    assert model.errors == ()
    assert model.warnings == ()


def test_parse_graphics_text_reports_a_bad_expression_as_a_warning() -> None:
    model = parse_graphics_text(" Expr  True  3 (((\r\n")

    assert len(model.bindings) == 1
    assert len(model.warnings) == 1
    assert model.errors == ()


def test_parse_graphics_file_reads_disk(tmp_path: Path) -> None:
    path = tmp_path / "Test.g"
    path.write_bytes(b" Var 0 7 SomeVar\r\n")

    model = parse_graphics_file(path)

    assert [binding.raw_text for binding in model.bindings] == ["SomeVar"]


def test_parse_graphics_file_read_failure_propagates(tmp_path: Path) -> None:
    path = tmp_path / "Test.g"
    path.mkdir()

    with pytest.raises(OSError):
        parse_graphics_file(path)


def test_parse_graphics_file_decode_failure_propagates(tmp_path: Path) -> None:
    path = tmp_path / "Test.g"
    path.write_bytes(b"\x81 not cp1252\r\n")

    with pytest.raises(UnicodeDecodeError):
        parse_graphics_file(path)
