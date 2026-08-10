# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_formatter_helpers_cover_variable_lists_optionals_and_expression_shapes():
    variables = [
        Variable(name="Alpha", datatype="integer", global_var=True, const=False, state=False, init_value=1),
        Variable(name="Beta", datatype="real", global_var=False, const=True, state=True, init_value=None),
    ]
    statement_tree = Tree(
        parser_const.KEY_STATEMENT,
        [(parser_const.KEY_ASSIGN, {parser_const.KEY_VAR_NAME: "Counter"}, 1)],
    )
    if_expr = (
        parser_const.GRAMMAR_VALUE_IF,
        [
            ({parser_const.KEY_VAR_NAME: "A"}, [(parser_const.KEY_ASSIGN, {parser_const.KEY_VAR_NAME: "B"}, 1)]),
            ({parser_const.KEY_VAR_NAME: "C"}, [(parser_const.KEY_ASSIGN, {parser_const.KEY_VAR_NAME: "D"}, 2)]),
        ],
        [(parser_const.KEY_ASSIGN, {parser_const.KEY_VAR_NAME: "E"}, 3)],
    )
    ternary_expr = (
        parser_const.KEY_TERNARY,
        [({parser_const.KEY_VAR_NAME: "Cond"}, {parser_const.KEY_VAR_NAME: "Left"})],
        {parser_const.KEY_VAR_NAME: "Right"},
    )

    assert format_list([], inline_if_singleline=True) == "[]"
    assert "Name: 'Alpha'" in format_list(variables)
    assert format_list([1, "two"], inline_if_singleline=True) == "[1, two]"
    assert format_list(["one\ntwo"], inline_if_singleline=True).startswith("[\n")
    assert format_optional(None) == "None"
    assert format_optional(5) == "5"
    assert format_expr(statement_tree) == "Counter = 1"
    assert format_expr({parser_const.KEY_VAR_NAME: "Value"}) == "Value"
    assert format_expr("hello") == "'hello'"
    assert format_expr([1, 2]) == "1\n2"
    assert format_expr((parser_const.KEY_ASSIGN, {parser_const.KEY_VAR_NAME: "Value"}, 5)) == "Value = 5"
    assert "ELSIF C" in format_expr(if_expr)
    assert "ELSE" in format_expr(if_expr)
    assert "ENDIF" in format_expr(ternary_expr)
    assert format_expr((parser_const.GRAMMAR_VALUE_OR, [True, False])) == "True OR \nFalse"
    assert format_expr((parser_const.GRAMMAR_VALUE_AND, [True, False])) == "True AND \nFalse"
    assert format_expr((parser_const.GRAMMAR_VALUE_NOT, {parser_const.KEY_VAR_NAME: "Flag"})) == "NOT(Flag)"
    assert format_expr((parser_const.KEY_COMPARE, {parser_const.KEY_VAR_NAME: "A"}, [])) == "A"
    assert format_expr((parser_const.KEY_COMPARE, {parser_const.KEY_VAR_NAME: "A"}, [(">", 1)])) == "A > 1"
    assert format_expr((parser_const.KEY_ADD, 1, [("+", 2)])) == "(1 + 2)"
    assert format_expr((parser_const.KEY_MUL, 2, [("*", 3)])) == "(2 * 3)"
    assert (
        format_expr((parser_const.KEY_FUNCTION_CALL, "CopyVariable", [{parser_const.KEY_VAR_NAME: "A"}, 1]))
        == "CopyVariable(A, 1)"
    )
    assert "('mystery', 1, 2)" in format_expr(("mystery", 1, 2))
    assert format_expr(SimpleNamespace(__str__=lambda self: "fallback")) != ""


def test_format_seq_nodes_covers_sfc_rendering_variants():
    assign_stmt = (parser_const.KEY_ASSIGN, {parser_const.KEY_VAR_NAME: "Out"}, 1)
    nodes = [
        SFCStep(
            kind="init",
            name="InitA",
            code=SFCCodeBlocks(enter=[assign_stmt], active=[assign_stmt], exit=[assign_stmt]),
        ),
        SFCTransition(name="ToRun", condition={parser_const.KEY_VAR_NAME: "Ready"}),
        SFCAlternative(branches=[[SFCFork(targets=("BranchA",))], [SFCBreak()]]),
        SFCParallel(branches=[[SFCFork(targets=("P1",))], [SFCFork(targets=("P2",))]]),
        SFCSubsequence(name="SubA", body=[SFCFork(targets=("SubTarget",))]),
        SFCTransitionSub(name="TransA", body=[SFCBreak()]),
        SFCFork(targets=("NextStep",)),
        SFCBreak(),
        "fallback-node",
    ]

    rendered = format_seq_nodes(nodes)

    assert "InitStep InitA" in rendered
    assert "Enter:" in rendered
    assert "Active:" in rendered
    assert "Exit:" in rendered
    assert "Transition ToRun WAIT_FOR Ready" in rendered
    assert "Alternative:" in rendered
    assert "EndAlternative" in rendered
    assert "Parallel:" in rendered
    assert "EndParallel" in rendered
    assert "Subsequence SubA:" in rendered
    assert "EndSubsequence" in rendered
    assert "TransitionSub TransA:" in rendered
    assert "EndTransitionSub" in rendered
    assert "Fork to NextStep" in rendered
    assert "Break" in rendered
    assert "fallback-node" in rendered
