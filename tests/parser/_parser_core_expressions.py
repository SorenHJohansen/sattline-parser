# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_tokens_mixin_coerces_supported_terminals_and_keywords():
    mixin = _TokensHarness()
    signed_int = Token("SIGNED_INT", "-7", line=4, column=2)
    real_value = Token("REAL", "3.25", line=8, column=6)

    assert mixin._unwrap_token(Token("NAME", "Motor")) == "Motor"
    assert mixin._unwrap_token("AlreadyString") == "AlreadyString"
    assert mixin.NAME(Token("NAME", "Valve")) == "Valve"
    assert mixin.STRING(Token("STRING", '"He said ""Hi""\n"')) == 'He said "Hi"'
    assert mixin.STRING(Token("STRING", "bare-text")) == "bare-text"
    assert mixin.STRING_CRLF(Token("STRING_CRLF", '"Line"\n')) == '"Line"'
    assert mixin.STRING_NOTAIL(Token("STRING_NOTAIL", '"Tail"')) == "Tail"

    assert mixin.SIGNED_INT(signed_int) == IntLiteral(-7, SourceSpan(line=4, column=2))
    assert mixin.SIGNED_INT_NOTAIL(signed_int) == IntLiteral(-7, SourceSpan(line=4, column=2))
    assert mixin.REAL(real_value) == FloatLiteral(3.25, SourceSpan(line=8, column=6))
    assert mixin.REAL_NOTAIL(real_value) == FloatLiteral(3.25, SourceSpan(line=8, column=6))
    assert mixin.BOOL(Token("BOOL", parser_const.GRAMMAR_VALUE_BOOL_TRUE)) is True
    assert mixin.BOOL_NOTAIL(Token("BOOL_NOTAIL", parser_const.GRAMMAR_VALUE_BOOL_FALSE)) is False

    assert mixin.GLOBAL_KW(None) is True
    assert mixin.CONST_KW(None) == "Const"
    assert mixin.STATE_KW(None) == "State"
    assert mixin.OPSAVE_KW(None) == "OpSave"
    assert mixin.SECURE_KW(None) == "Secure"
    assert mixin.DEFAULT(None) is DEFAULT_INIT
    assert mixin.COLON(None) is None
    assert mixin.COMMA(None) is None
    assert mixin.SEMI(None) is None
    assert mixin.ASSIGN_INIT_VALUE(None) is None
    assert mixin.DURATION_VALUE(None) == parser_const.GRAMMAR_VALUE_DURATION_VALUE


def test_tokens_mixin_rejects_invalid_bool_and_bad_datecode_tokens():
    mixin = _TokensHarness()

    with pytest.raises(ValueError, match="BOOL expected"):
        mixin.BOOL(Token("BOOL", "Maybe"))

    assert mixin.sl_datecode([12, Token(parser_const.KEY_SL_DATECODE, "99")]) == 12
    assert mixin.sl_datecode([Token(parser_const.KEY_SL_DATECODE, "20260430")]) == 20260430

    with pytest.raises(ValueError, match="Invalid SL_DATECODE value"):
        mixin.sl_datecode([Token(parser_const.KEY_SL_DATECODE, "invalid")])

    with pytest.raises(ValueError, match="sl_datecode expected"):
        mixin.sl_datecode([Token("NAME", "NoDateCode")])


def test_expressions_mixin_coerces_values_and_builds_expression_tuples():
    mixin = _ExpressionsHarness()

    assert mixin.value([True]) is True
    with pytest.raises(ValueError, match="got empty list"):
        mixin.value([])
    with pytest.raises(ValueError, match="expected exactly one item"):
        mixin.value([1, 2])
    with pytest.raises(ValueError, match="item is None"):
        mixin.value([None])

    assert mixin.connected_variable([Token("NAME", "ignored"), "Motor.Speed"]) == "Motor.Speed"
    assert mixin.invar_tail([Token("NAME", "ignored"), {"tail": "InVar_1"}]) == {"tail": "InVar_1"}
    with pytest.raises(ValueError, match="connected_variable expected"):
        mixin.connected_variable([Token("NAME", "OnlyToken")])
    with pytest.raises(ValueError, match="invar_tail expected"):
        mixin.invar_tail([Token("NAME", "OnlyToken")])
    with pytest.raises(ValueError, match="function_call missing name"):
        mixin.function_call([Token("LPAREN", "("), 42, Token("RPAREN", ")")])

    assert mixin.or_expression(["lhs"]) == "lhs"
    assert mixin.or_expression(["lhs", Token("OR", "OR"), "rhs"]) == BoolOp("OR", ("lhs", "rhs"))
    assert mixin.and_expression(["lhs"]) == "lhs"
    assert mixin.and_expression(["lhs", Token("AND", "AND"), "rhs"]) == BoolOp("AND", ("lhs", "rhs"))
    assert mixin.not_expression(["expr"]) == "expr"
    assert mixin.not_expression([Token("NOT", "NOT"), "expr"]) == NotOp("expr")
    assert mixin.not_expression([Token("NOT", "NOT")]) == Token("NOT", "NOT")

    assert mixin.compare(["lhs"]) == "lhs"
    assert mixin.compare([]) is None
    assert mixin.compare(["lhs", Token("EQ", "="), "rhs", Token("NE", "<>"), "other"]) == (
        Compare(Compare("lhs", "=", "rhs"), "<>", "other")
    )
    assert mixin.additive_expression(["lhs", Token("PLUS", "+"), "rhs"]) == BinOp("lhs", "+", "rhs")
    assert mixin.multiplicative_expression(["lhs", Token("STAR", "*"), "rhs"]) == BinOp("lhs", "*", "rhs")
    assert mixin.compare(["lhs", Token("EQ", "=")]) == "lhs"


def test_expressions_mixin_builds_statements_calls_and_conditionals():
    mixin = _ExpressionsHarness()

    assert mixin.unary_expression(["expr"]) == "expr"
    assert mixin.unary_expression([Token(parser_const.KEY_MINUS, "-"), "expr"]) == UnaryOp("-", "expr")
    assert mixin.unary_expression([Token("PLUS", "+"), "expr"]) == UnaryOp("+", "expr")
    assert mixin.not_expression([Token("NOT", "NOT"), Token("PLUS", "+")]) == Token("PLUS", "+")
    assert mixin.additive_expression([Token("PLUS", "+")]) is None
    assert mixin.additive_expression(["lhs", Token("PLUS", "+"), "rhs", Token("PLUS", "+")]) == BinOp("lhs", "+", "rhs")
    assert mixin.multiplicative_expression([Token("STAR", "*")]) is None
    assert mixin.multiplicative_expression(["lhs", Token("STAR", "*"), "rhs", Token("STAR", "*")]) == BinOp(
        "lhs", "*", "rhs"
    )
    assert mixin.compare(["lhs", Token("EQ", "="), "rhs", Token("NE", "<>")]) == Compare("lhs", "=", "rhs")
    with pytest.raises(ValueError, match="expected operator and expression"):
        mixin.unary_expression([Token("PLUS", "+"), Token("MINUS", "-")])

    assert mixin.argument_list(["a", Token("COMMA", ","), "b"]) == ["a", "b"]
    assert mixin.function_call(["Fn", ["arg"]]) == FuncCall("Fn", ("arg",))
    assert mixin.function_call(["Fn", Token("LPAREN", "("), ["arg1", "arg2"], Token("RPAREN", ")")]) == (
        FuncCall("Fn", ("arg1", "arg2"))
    )
    assert mixin.assignment_statement(["Target", "Value"]) == Assignment(VarRef("Target"), "Value")
    assert mixin.assignment_statement(["Target", Token("EQUAL", "="), "Value"]) == (
        Assignment(VarRef("Target"), "Value")
    )

    ternary_items = [
        Token(parser_const.GRAMMAR_VALUE_IF, "IF"),
        "cond1",
        Token("THEN", "THEN"),
        "value1",
        Token(parser_const.GRAMMAR_VALUE_ELSIF, "ELSIF"),
        "cond2",
        Token("THEN", "THEN"),
        "value2",
        Token(parser_const.GRAMMAR_VALUE_ELSE, "ELSE"),
        "fallback",
        Token(parser_const.GRAMMAR_VALUE_ENDIF, "ENDIF"),
    ]
    assert mixin.ternary_if(ternary_items) == TernaryOp(
        branches=(("cond1", "value1"), ("cond2", "value2")),
        else_expr="fallback",
    )

    if_items = [
        Token(parser_const.GRAMMAR_VALUE_IF, "IF"),
        "cond1",
        Token("THEN", "THEN"),
        "stmt1",
        Token(parser_const.GRAMMAR_VALUE_ELSIF, "ELSIF"),
        "cond2",
        Token("THEN", "THEN"),
        "stmt2",
        Token(parser_const.GRAMMAR_VALUE_ELSE, "ELSE"),
        "stmt3",
        Token(parser_const.GRAMMAR_VALUE_ENDIF, "ENDIF"),
    ]
    assert mixin.if_statement(if_items) == IfStmt(
        branches=(("cond1", ("stmt1",)), ("cond2", ("stmt2",))),
        else_block=("stmt3",),
    )
    assert mixin.if_statement([Token("IGNORED", "?"), *if_items]) == IfStmt(
        branches=(("cond1", ("stmt1",)), ("cond2", ("stmt2",))),
        else_block=("stmt3",),
    )
    assert mixin.statement([Token("IGNORED", "?"), "assignment"]) == "assignment"
    with pytest.raises(ValueError, match="statement expected a non-Token child"):
        mixin.statement([Token("ONLY", "token")])
    with pytest.raises(ValueError, match="statement expected a non-Token child"):
        mixin.statement([])
