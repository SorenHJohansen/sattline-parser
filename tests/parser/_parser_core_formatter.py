# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_formatter_helpers_cover_variable_lists_optionals_and_expression_shapes():
    variables = [
        Variable(name="Alpha", datatype="integer", global_var=True, const=False, state=False, init_value=1),
        Variable(name="Beta", datatype="real", global_var=False, const=True, state=True, init_value=None),
    ]
    if_stmt = IfStmt(
        branches=(
            (VarRef("A"), (Assignment(VarRef("B"), IntLiteral(1)),)),
            (VarRef("C"), (Assignment(VarRef("D"), IntLiteral(2)),)),
        ),
        else_block=(Assignment(VarRef("E"), IntLiteral(3)),),
    )
    ternary_expr = TernaryOp(branches=((VarRef("Cond"), VarRef("Left")),), else_expr=VarRef("Right"))

    assert format_list([], inline_if_singleline=True) == "[]"
    assert "Name: 'Alpha'" in format_list(variables)
    assert format_list([1, "two"], inline_if_singleline=True) == "[1, two]"
    assert format_list(["one\ntwo"], inline_if_singleline=True).startswith("[\n")
    assert format_optional(None) == "None"
    assert format_optional(5) == "5"
    assert format_expr(Assignment(VarRef("Counter"), IntLiteral(1))) == "Counter = 1"
    assert format_expr(VarRef("Value")) == "Value"
    assert format_expr("hello") == "'hello'"
    assert format_expr(Assignment(VarRef("Value"), IntLiteral(5))) == "Value = 5"
    assert "ELSIF C" in format_expr(if_stmt)
    assert "ELSE" in format_expr(if_stmt)
    assert "ENDIF" in format_expr(ternary_expr)
    assert format_expr(BoolOp("OR", (True, False))) == "True OR \nFalse"
    assert format_expr(BoolOp("AND", (True, False))) == "True AND \nFalse"
    assert format_expr(NotOp(VarRef("Flag"))) == "NOT(Flag)"
    assert format_expr(Compare(VarRef("A"), ">", 1)) == "A > 1"
    assert format_expr(BinOp(1, "+", 2)) == "(1 + 2)"
    assert format_expr(BinOp(2, "*", 3)) == "(2 * 3)"
    assert format_expr(FuncCall("CopyVariable", (VarRef("A"), IntLiteral(1)))) == "CopyVariable(A, 1)"
    assert "('mystery', 1, 2)" in format_expr(("mystery", 1, 2))
    assert format_expr(SimpleNamespace(__str__=lambda self: "fallback")) != ""


def test_format_seq_nodes_covers_sfc_rendering_variants():
    assign_stmt = Assignment(VarRef("Out"), IntLiteral(1))
    nodes = [
        SFCStep(
            kind="init",
            name="InitA",
            code=SFCCodeBlocks(enter=[assign_stmt], active=[assign_stmt], exit=[assign_stmt]),
        ),
        SFCTransition(name="ToRun", condition=VarRef("Ready")),
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
