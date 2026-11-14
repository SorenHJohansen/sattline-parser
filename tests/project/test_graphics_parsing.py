"""Unit tests for graphics companion parsing (``project/graphics_*``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from lark import Tree

from sattline_parser.models.ast_model import GraphicsBinding, SourceSpan
from sattline_parser.project import (
    GraphicsBinding as ProjectGraphicsBinding,
)
from sattline_parser.project import (
    LoadMode,
    parse_graphics_file,
    parse_graphics_text,
    resolve_graphics_companion_path,
)
from sattline_parser.project import graphics_bindings as bindings
from sattline_parser.project.graphics_parsing import GraphicsParseError


def test_graphics_binding_is_on_the_project_surface() -> None:
    assert ProjectGraphicsBinding is GraphicsBinding


def test_resolve_graphics_companion_path_pairs_ignoring_case(tmp_path: Path) -> None:
    (tmp_path / "PUMP.S").write_text("", encoding="utf-8")
    lower = tmp_path / "pump.g"
    lower.write_text("", encoding="utf-8")

    assert resolve_graphics_companion_path(tmp_path / "PUMP.S", mode=LoadMode.DRAFT) == lower


def test_resolve_graphics_companion_path_never_pairs_a_draft_body_with_official_graphics(tmp_path: Path) -> None:
    (tmp_path / "M.s").write_text("", encoding="utf-8")
    (tmp_path / "M.y").write_text("", encoding="utf-8")

    assert resolve_graphics_companion_path(tmp_path / "M.s", mode=LoadMode.OFFICIAL) is None


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


def test_resolve_graphics_companion_path_draft_does_not_use_official_y(tmp_path: Path) -> None:
    (tmp_path / "M.s").write_text("", encoding="utf-8")
    (tmp_path / "M.y").write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(tmp_path / "M.s", mode=LoadMode.DRAFT) is None


def test_resolve_graphics_companion_path_draft_uses_g(tmp_path: Path) -> None:
    (tmp_path / "M.s").write_text("", encoding="utf-8")
    (tmp_path / "M.g").write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(tmp_path / "M.s", mode=LoadMode.DRAFT) == tmp_path / "M.g"


def test_resolve_graphics_companion_path_official_only_y(tmp_path: Path) -> None:
    (tmp_path / "M.s").write_text("", encoding="utf-8")
    (tmp_path / "M.g").write_text("", encoding="utf-8")
    (tmp_path / "M.y").write_text("", encoding="utf-8")
    assert resolve_graphics_companion_path(tmp_path / "M.x", mode=LoadMode.OFFICIAL) == tmp_path / "M.y"


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
    match = bindings.BINDING_LINE_RE.search(" Var  True  5 HVar tail")
    assert match is not None
    binding, messages = bindings.parse_graphics_binding_match(match.string, line=7, match=match)
    assert messages == ()
    assert binding is not None
    assert binding.kind == "var"
    assert binding.raw_text == "HVar"
    assert binding.value == {"var_name": "HVar", "span": binding.span}


def test_parse_graphics_binding_match_lit() -> None:
    match = bindings.BINDING_LINE_RE.search("  Lit  True  4 True ")
    assert match is not None
    binding, _ = bindings.parse_graphics_binding_match(match.string, line=2, match=match, line_start_offset=1)
    assert binding is not None
    assert binding.kind == "lit"
    assert binding.value is True


def test_parse_graphics_binding_match_expr_success() -> None:
    text = "  Expr  True  15 not ZoomableVar"
    match = bindings.BINDING_LINE_RE.search(text)
    assert match is not None
    binding, messages = bindings.parse_graphics_binding_match(text, line=5, match=match, line_start_offset=4)
    assert messages == ()
    assert binding is not None
    assert binding.kind == "expr"
    assert binding.raw_text == "not ZoomableVar"
    assert not isinstance(binding.value, str)
    assert binding.span is not None
    assert binding.span.line == 5


def test_parse_graphics_binding_match_expr_failure_warns() -> None:
    text = "  Expr  True  3 ((("
    match = bindings.BINDING_LINE_RE.search(text)
    assert match is not None
    binding, messages = bindings.parse_graphics_binding_match(text, line=9, match=match, line_start_offset=8)
    assert binding is not None
    assert binding.kind == "expr"
    assert binding.value == "((("
    assert len(messages) == 1
    assert messages[0].severity == "warning"
    assert messages[0].message.startswith("Could not parse graphics expression '(((':")
    assert messages[0].line == 9


def test_parse_graphics_binding_match_negative_length() -> None:
    match = bindings.BINDING_LINE_RE.search("  Expr  True  -1  x")
    assert match is not None
    assert bindings.parse_graphics_binding_match(match.string, line=1, match=match, line_start_offset=0) == (None, ())


def test_parse_graphics_binding_match_length_overflow_and_empty() -> None:
    overflow_match = bindings.BINDING_LINE_RE.search("  Var  True  99 x")
    assert overflow_match is not None
    binding, messages = bindings.parse_graphics_binding_match(
        overflow_match.string, line=1, match=overflow_match, line_start_offset=0
    )
    assert messages == ()
    assert binding is not None
    assert binding.raw_text == "x"

    empty_match = bindings.BINDING_LINE_RE.search("  Lit  True  0  ")
    assert empty_match is not None
    assert bindings.parse_graphics_binding_match(
        empty_match.string, line=1, match=empty_match, line_start_offset=0
    ) == (None, ())


def test_parse_graphics_binding_line_multiple_bindings() -> None:
    text = " Var 0 12 OprPathIndex  Lit 0 2 -1     2"
    bindings_, messages = bindings.parse_graphics_binding_line(text, line=8)
    assert messages == ()
    assert [(b.kind, b.raw_text) for b in bindings_] == [("var", "OprPathIndex"), ("lit", "-1")]


# --- source positions -----------------------------------------------------------


def test_rebase_expression_spans_places_the_payload_at_the_requested_position() -> None:
    span = SourceSpan(start=4, end=9, line=1, column=5)

    rebased = bindings._rebase_expression_spans(span, line=2, column=11, start=100)

    assert rebased == SourceSpan(start=104, end=109, line=2, column=15)


def test_rebase_expression_spans_keeps_later_lines_in_their_own_column() -> None:
    span = SourceSpan(start=30, end=31, line=3, column=4)

    rebased = bindings._rebase_expression_spans(span, line=7, column=11, start=100)

    assert rebased == SourceSpan(start=130, end=131, line=9, column=4)


def test_rebase_expression_spans_rebuilds_nested_dataclasses_and_containers() -> None:
    text = "  Expr  True  15 not ZoomableVar"
    match = bindings.BINDING_LINE_RE.search(text)
    assert match is not None
    binding, _ = bindings.parse_graphics_binding_match(text, line=3, match=match, line_start_offset=0)

    assert binding is not None
    assert binding.span == SourceSpan(start=17, end=32, line=3, column=18)
    assert binding.value is not None
    assert binding.value.span == binding.span


def test_rebase_expression_spans_walks_dicts_lists_tuples_and_trees() -> None:
    span = SourceSpan(start=0, end=1, line=1, column=1)
    payload: dict[str, object] = {
        "span": span,
        "items": [span, (span,)],
        "tree": Tree("expression", [span]),
        "plain": 3,
    }

    rebased = cast("dict[str, Any]", bindings._rebase_expression_spans(payload, line=2, column=3, start=10))

    expected = SourceSpan(start=10, end=11, line=2, column=3)
    assert rebased["span"] == expected
    items = cast("list[Any]", rebased["items"])
    assert items[0] == expected
    assert cast("tuple[Any, ...]", items[1])[0] == expected
    assert cast("Tree[Any]", rebased["tree"]).children[0] == expected
    assert rebased["plain"] == 3


def test_parse_graphics_text_binding_spans_are_offsets_into_the_companion_text() -> None:
    text = "first line\r\n  Var  True  5 HVar tail\r\n  Lit  True  4 True \r\n  Expr  True  15 not ZoomableVar\r\n"

    model = parse_graphics_text(text)

    var_binding, lit_binding, expr_binding = model.bindings
    var_start = text.index("HVar")
    assert var_binding.span == SourceSpan(
        start=var_start,
        end=var_start + len("HVar"),
        line=2,
        column=16,
    )
    lit_start = text.index("  Lit") + 15
    assert lit_binding.span == SourceSpan(
        start=lit_start,
        end=lit_start + len("True"),
        line=3,
        column=16,
    )
    expr_start = text.index("not ZoomableVar")
    assert expr_binding.span == SourceSpan(
        start=expr_start,
        end=expr_start + len("not ZoomableVar"),
        line=4,
        column=18,
    )
    assert expr_binding.value is not None
    value_span = expr_binding.value.span
    assert isinstance(value_span, SourceSpan)
    assert value_span == expr_binding.span


def test_parse_graphics_binding_match_var_value_carries_the_binding_span() -> None:
    match = bindings.BINDING_LINE_RE.search(" Var  True  5 HVar tail")
    assert match is not None
    binding, messages = bindings.parse_graphics_binding_match(
        match.string,
        line=1,
        match=match,
        line_start_offset=0,
    )

    assert messages == ()
    assert binding is not None
    assert binding.span is not None
    assert binding.value == {"var_name": "HVar", "span": binding.span}


def test_parse_graphics_binding_line_reports_offsets_for_every_binding() -> None:
    text = " Var 0 12 OprPathIndex  Lit 0 2 -1     2"
    parsed, messages = bindings.parse_graphics_binding_line(text, line=1, line_start_offset=0)

    assert messages == ()
    spans: list[tuple[str, int, int]] = []
    for binding in parsed:
        assert binding.span is not None
        spans.append((binding.raw_text, binding.span.start, binding.span.end))
    assert spans == [
        ("OprPathIndex", text.index("OprPathIndex"), text.index("OprPathIndex") + len("OprPathIndex")),
        ("-1", text.index("-1"), text.index("-1") + len("-1")),
    ]


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


def test_parse_graphics_text_reports_an_over_deep_expression_as_a_warning() -> None:
    """A recursion failure becomes a message instead of escaping the parser."""
    model = parse_graphics_text(" Expr True 99999 " + "not " * 5000 + "x\r\n")

    assert len(model.bindings) == 1
    assert isinstance(model.bindings[0].value, str)
    assert len(model.warnings) == 1
    assert model.errors == ()


def test_expression_float_literals_carry_companion_spans() -> None:
    model = parse_graphics_text("pad\r\n Expr True 11 Level > 5.5\r\n")

    literal = model.bindings[0].value.right  # type: ignore[attr-defined]
    assert literal.span is not None
    assert (literal.span.line, literal.span.column) == (2, 23)
    assert (literal.span.start, literal.span.end) == (27, 30)


def test_expression_numeric_literals_carry_companion_spans() -> None:
    model = parse_graphics_text("pad\r\n Expr True 9 Level > 5\r\n")

    compare = model.bindings[0].value
    literal = compare.right  # type: ignore[attr-defined]
    assert literal.span is not None
    assert (literal.span.line, literal.span.column) == (2, 22)
    assert (literal.span.start, literal.span.end) == (26, 27)


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


@pytest.mark.parametrize("error", [ValueError("bad value"), TypeError("bad type"), IndexError("bad index")])
def test_parse_graphics_text_turns_transformer_failures_into_warnings(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """A transformer defect on one binding is a message, not an escaped traceback."""

    class FailingTransformer:
        def transform(self, tree: Tree[Any]) -> object:
            del tree
            raise error

    monkeypatch.setattr(bindings, "SLTransformer", lambda: FailingTransformer())

    model = parse_graphics_text(" Expr  True  15 not ZoomableVar\r\n")

    assert len(model.bindings) == 1
    assert isinstance(model.bindings[0].value, str)
    assert len(model.warnings) == 1
    assert model.errors == ()


def test_parse_graphics_file_rejects_an_oversize_companion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "Test.g"
    path.write_bytes(b"x" * 32)
    monkeypatch.setattr("sattline_parser.project.graphics_parsing.MAX_GRAPHICS_COMPANION_BYTES", 4)

    with pytest.raises(GraphicsParseError, match="byte limit"):
        parse_graphics_file(path)
