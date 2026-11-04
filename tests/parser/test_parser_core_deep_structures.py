# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
# ruff: noqa: F403, F405
"""Deep-structure limits: clean nesting errors, iterative parse-tree handling, and the iterative walker."""

from __future__ import annotations

import pickle

from lark.exceptions import VisitError

from sattline_parser import MAX_SOURCE_DEPTH, SourceTooDeepError
from sattline_parser.models.expressions import SLExpression
from sattline_parser.models.walk import WalkEvent, walk
from sattline_parser.source_document import remap_tree_to_original

from ._parser_core_test_support import *


def _program(expression: str) -> str:
    return (
        '"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-08-19-12:00:00.000, name: Deep"\n'
        "BasePicture Invocation\n"
        "   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
        "    ) : MODULEDEFINITION DateCode_ 1\n"
        "\n"
        "LOCALVARIABLES\n"
        "   A: real  := 1.0;\n"
        "   R: real  := 0.0;\n"
        "\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        f"      R = {expression};\n"
        "\n"
        "ENDDEF (*BasePicture*);\n"
    )


def _chain(terms: int) -> str:
    return " + ".join(["A"] * terms)


def _parens(levels: int) -> str:
    return "(" * levels + "A" + ")" * levels


def _comment_program(levels: int) -> str:
    comment = "(* " * levels + "core" + " *)" * levels
    return _program("A").replace("      R = A;", f"      {comment}\n      R = A;")


def _interact_program(expression: str) -> str:
    return (
        '"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-08-19-12:00:00.000, name: DeepBody"\n'
        "BasePicture Invocation\n"
        "   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
        "    ) : MODULEDEFINITION DateCode_ 1\n"
        "\n"
        "LOCALVARIABLES\n"
        "   A: real  := 1.0;\n"
        "   R: real  := 0.0;\n"
        "\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "InteractObjects :\n"
        "   ComBut_ ( 0.0 , 0.0 ) ( 1.0 , 1.0 )\n"
        f"      Enable_ = True : ( {expression} )\n"
        "\n"
        "ENDDEF (*BasePicture*);\n"
    )


def _tree_depth(root: object) -> int:
    if not isinstance(root, Tree):
        return 1
    best = 0
    stack: list[tuple[object, int]] = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        best = max(best, depth)
        if isinstance(node, Tree):
            for child in node.children:
                stack.append((child, depth + 1))
    return best


def _largest_accepted_chain() -> int:
    accepted = 0
    for terms in range(MAX_SOURCE_DEPTH - 40, MAX_SOURCE_DEPTH + 1):
        try:
            parser_core_parse_source_text(_program(_chain(terms)), log_failures=False)
        except SourceTooDeepError:
            break
        accepted = terms
    return accepted


def test_deep_left_associative_chain_is_a_clean_parse_error() -> None:
    with pytest.raises(SourceTooDeepError) as exc_info:
        parser_core_parse_source_text(_program(_chain(5000)), log_failures=False)

    error = exc_info.value
    assert error.limit == MAX_SOURCE_DEPTH
    assert isinstance(error, UnexpectedInput)
    assert "nested too deeply" in str(error)


def test_deep_parentheses_parse_without_recursion() -> None:
    bp = parser_core_parse_source_text(_program(_parens(1000)), log_failures=False)
    retained = parser_core_parse_source_text(_program(_parens(1000)), retain_parse_tree=True, log_failures=False)

    assert retained.parse_tree is not None
    assert _tree_depth(retained.parse_tree) > 1000
    references = [event.node for event in walk(bp) if isinstance(event.node, VarRef)]
    assert [reference.name for reference in references] == ["R", "A"]
    assert repr(bp)


def test_deeply_nested_comments_parse_without_recursion() -> None:
    bp = parser_core_parse_source_text(_comment_program(1000), log_failures=False)

    comments = [event.node for event in walk(bp) if isinstance(event.node, CodeComment)]
    assert comments
    assert "core" in comments[0].text


def test_chain_below_the_limit_is_accepted_and_walkable() -> None:
    source = _program(_chain(MAX_SOURCE_DEPTH - 20))
    bp, diagnostics = parser_api.parse_and_validate(source, log_failures=False)

    assert diagnostics == ()
    assert repr(bp)
    assert any(isinstance(event.node, BinOp) for event in walk(bp))


def test_chain_boundary_is_exact_and_near_cap_consumers_work() -> None:
    accepted = _largest_accepted_chain()
    assert accepted >= MAX_SOURCE_DEPTH - 40

    with pytest.raises(SourceTooDeepError):
        parser_core_parse_source_text(_program(_chain(accepted + 1)), log_failures=False)

    source = _program(_chain(accepted))
    bp = parser_core_parse_source_text(source, log_failures=False)
    same = parser_core_parse_source_text(source, log_failures=False)

    assert bp == same
    assert repr(bp)
    equations = bp.modulecodes[0].equations
    assert equations is not None
    assert format_expr(equations[0].code[0])
    assert pickle.loads(pickle.dumps(bp)) == bp


def test_deep_interact_tail_is_covered_by_the_limit() -> None:
    with pytest.raises(SourceTooDeepError):
        parser_core_parse_source_text(_interact_program(_chain(5000)), log_failures=False)


def test_describe_parse_error_reports_the_nesting_limit() -> None:
    source = _program(_chain(5000))
    with pytest.raises(SourceTooDeepError) as exc_info:
        parser_core_parse_source_text(source, log_failures=False)

    details = parser_api.describe_parse_error(exc_info.value, source)

    assert details.sentence == (
        f"the parsed structure is nested too deeply to analyze safely (limit {MAX_SOURCE_DEPTH} levels)"
    )
    assert details.hint == "split the expression into intermediate variables or reduce the nesting"
    assert details.line is not None
    assert details.source_line is not None


def test_fuzz_harness_classifies_the_nesting_error_as_expected_input() -> None:
    result = parser_fuzz_harness.fuzz_parse_text(_program(_chain(5000)), input_desc="deep-chain")

    assert result.success is False
    assert isinstance(result.error, SourceTooDeepError)
    assert parser_fuzz_harness._is_expected_parse_error(result.error)


def test_walk_handles_a_deep_manual_expression_without_recursion() -> None:
    expression: SLExpression = VarRef("A")
    for _ in range(5000):
        expression = BinOp(expression, "+", VarRef("A"))

    events = list(walk(expression))

    assert len(events) == 10001
    deepest = events[5000]
    assert isinstance(deepest.node, VarRef)
    assert len(deepest.parents) == 5000
    assert isinstance(deepest.parents[0], BinOp)


def test_walk_event_parents_behaves_like_a_tuple() -> None:
    root = VarRef("Root")
    parent = VarRef("Parent")
    child = VarRef("Child")

    event = WalkEvent(node=child, relation="value", parents=(root, parent))
    same = WalkEvent(node=child, relation="value", parents=(root, parent))
    empty = WalkEvent(node=root, relation="")

    assert event.relation == "value"
    assert event.parents == (root, parent)
    assert event.parents == same.parents
    assert event.parents == [root, parent]
    assert event.parents != object()
    assert hash(event.parents) == hash((root, parent))
    assert repr(event.parents) == repr((root, parent))
    assert event.parents[0] is root
    assert list(event.parents[1:]) == [parent]
    assert len(event.parents) == 2
    assert len(empty.parents) == 0
    assert list(empty.parents) == []
    assert empty.parents == ()


def test_recursion_error_in_the_transformer_becomes_a_clean_parse_error() -> None:
    class _RecursiveTransformer:
        def transform(self, _tree: object) -> object:
            raise RecursionError("boom")

    with pytest.raises(SourceTooDeepError):
        parser_core_parse_source_text(_program("A"), transformer=_RecursiveTransformer())


def test_lark_wrapped_recursion_error_becomes_a_clean_parse_error() -> None:
    class _WrappedRecursiveTransformer:
        def transform(self, _tree: object) -> object:
            raise VisitError("boom", Tree("rule", []), RecursionError("boom"))

    with pytest.raises(SourceTooDeepError):
        parser_core_parse_source_text(_program("A"), transformer=_WrappedRecursiveTransformer())


def test_recursion_error_in_the_parser_becomes_a_clean_parse_error() -> None:
    class _RecursiveParser:
        def parse(self, _text: str) -> Tree[Token]:
            raise RecursionError("boom")

    with pytest.raises(SourceTooDeepError):
        parser_core_parse_source_text(_program("A"), parser=_RecursiveParser())


def test_recursion_error_in_remap_becomes_a_clean_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_tree: object, _document: object) -> None:
        raise RecursionError("boom")

    monkeypatch.setattr(parser_api, "remap_tree_to_original", _boom)

    with pytest.raises(SourceTooDeepError):
        parser_core_parse_source_text(_program("A"))


def test_source_too_deep_error_survives_pickling() -> None:
    error = SourceTooDeepError(MAX_SOURCE_DEPTH, line=10, column=5, pos_in_stream=42)

    clone = pickle.loads(pickle.dumps(error))

    assert isinstance(clone, SourceTooDeepError)
    assert clone.limit == MAX_SOURCE_DEPTH
    assert str(clone) == str(error)
    assert clone.line == 10
    assert clone.column == 5
    assert clone.pos_in_stream == 42


def test_positionless_nesting_error_has_no_misleading_context() -> None:
    details = parser_api.describe_parse_error(SourceTooDeepError(MAX_SOURCE_DEPTH), "anything")

    assert details.line is None
    assert details.column is None
    assert details.source_line is None
    assert "\n^" not in details.message


def test_remap_tree_handles_a_deep_synthetic_tree() -> None:
    original = "x" * 2000
    normalized = "y" * 2000
    document = SourceDocument(original, normalized, tuple(range(2000)))

    node: object = Token("NAME", "y", start_pos=1999, end_pos=2000, line=1, column=2000)
    for index in range(1999, -1, -1):
        meta = Meta()
        meta.start_pos = index
        meta.end_pos = index + 1
        meta.line = 1
        meta.column = index + 1
        node = Tree("wrapper", [node], meta)

    remap_tree_to_original(cast(Tree[Token], node), document)

    current = node
    while isinstance(current, Tree):
        current = current.children[0]
    assert isinstance(current, Token)
    assert current.start_pos == 1999
    assert current.end_pos == 2000
