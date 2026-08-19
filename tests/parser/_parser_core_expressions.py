# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *

_META = SimpleNamespace(line=1, column=1, start_pos=10, end_pos=20, end_line=1, end_column=11)
_SPAN = SourceSpan(start=10, end=20, line=1, column=1)


def test_tokens_mixin_coerces_supported_terminals_and_keywords():
    mixin = _TokensHarness()
    signed_int = Token("SIGNED_INT", "-7", start_pos=10, line=4, column=2, end_line=4, end_column=4, end_pos=12)
    real_value = Token("REAL", "3.25", start_pos=20, line=8, column=6, end_line=8, end_column=10, end_pos=24)

    assert mixin._unwrap_token(Token("NAME", "Motor")) == "Motor"
    assert mixin._unwrap_token("AlreadyString") == "AlreadyString"
    assert mixin.NAME(Token("NAME", "Valve")) == "Valve"
    assert mixin.STRING(Token("STRING", '"He said ""Hi""\n"')) == 'He said "Hi"'
    assert mixin.STRING(Token("STRING", "bare-text")) == "bare-text"
    assert mixin.STRING_CRLF(Token("STRING_CRLF", '"Line"\n')) == '"Line"'
    assert mixin.STRING_NOTAIL(Token("STRING_NOTAIL", '"Tail"')) == "Tail"

    assert mixin.SIGNED_INT(signed_int) == IntLiteral(-7, SourceSpan(start=10, end=12, line=4, column=2))
    assert mixin.SIGNED_INT_NOTAIL(signed_int) == IntLiteral(-7, SourceSpan(start=10, end=12, line=4, column=2))
    assert mixin.REAL(real_value) == FloatLiteral(3.25, SourceSpan(start=20, end=24, line=8, column=6))
    assert mixin.REAL_NOTAIL(real_value) == FloatLiteral(3.25, SourceSpan(start=20, end=24, line=8, column=6))
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
        mixin.function_call(_META, [Token("LPAREN", "("), 42, Token("RPAREN", ")")])

    assert mixin.or_expression(_META, ["lhs"]) == "lhs"
    assert mixin.or_expression(_META, ["lhs", Token("OR", "OR"), "rhs"]) == BoolOp("OR", ("lhs", "rhs"), span=_SPAN)
    assert mixin.and_expression(_META, ["lhs"]) == "lhs"
    assert mixin.and_expression(_META, ["lhs", Token("AND", "AND"), "rhs"]) == BoolOp("AND", ("lhs", "rhs"), span=_SPAN)
    assert mixin.not_expression(_META, ["expr"]) == "expr"
    assert mixin.not_expression(_META, [Token("NOT", "NOT"), "expr"]) == NotOp("expr", span=_SPAN)
    assert mixin.not_expression(_META, [Token("NOT", "NOT")]) == Token("NOT", "NOT")

    assert mixin.compare(_META, ["lhs"]) == "lhs"
    assert mixin.compare(_META, []) is None
    assert mixin.compare(_META, ["lhs", Token("EQ", "="), "rhs", Token("NE", "<>"), "other"]) == (
        Compare(Compare("lhs", "=", "rhs", span=_SPAN), "<>", "other", span=_SPAN)
    )
    assert mixin.additive_expression(_META, ["lhs", Token("PLUS", "+"), "rhs"]) == BinOp("lhs", "+", "rhs", span=_SPAN)
    assert mixin.multiplicative_expression(_META, ["lhs", Token("STAR", "*"), "rhs"]) == BinOp(
        "lhs", "*", "rhs", span=_SPAN
    )
    assert mixin.compare(_META, ["lhs", Token("EQ", "=")]) == "lhs"


def test_expressions_mixin_builds_statements_calls_and_conditionals():
    mixin = _ExpressionsHarness()

    assert mixin.unary_expression(_META, ["expr"]) == "expr"
    assert mixin.unary_expression(_META, [Token(parser_const.KEY_MINUS, "-"), "expr"]) == UnaryOp(
        "-", "expr", span=_SPAN
    )
    assert mixin.unary_expression(_META, [Token("PLUS", "+"), "expr"]) == UnaryOp("+", "expr", span=_SPAN)
    assert mixin.not_expression(_META, [Token("NOT", "NOT"), Token("PLUS", "+")]) == Token("PLUS", "+")
    assert mixin.additive_expression(_META, [Token("PLUS", "+")]) is None
    assert mixin.additive_expression(_META, ["lhs", Token("PLUS", "+"), "rhs", Token("PLUS", "+")]) == BinOp(
        "lhs", "+", "rhs", span=_SPAN
    )
    assert mixin.multiplicative_expression(_META, [Token("STAR", "*")]) is None
    assert mixin.multiplicative_expression(_META, ["lhs", Token("STAR", "*"), "rhs", Token("STAR", "*")]) == BinOp(
        "lhs", "*", "rhs", span=_SPAN
    )
    assert mixin.compare(_META, ["lhs", Token("EQ", "="), "rhs", Token("NE", "<>")]) == Compare(
        "lhs", "=", "rhs", span=_SPAN
    )
    with pytest.raises(ValueError, match="expected operator and expression"):
        mixin.unary_expression(_META, [Token("PLUS", "+"), Token("MINUS", "-")])

    assert mixin.argument_list(["a", Token("COMMA", ","), "b"]) == ["a", "b"]
    assert mixin.function_call(_META, ["Fn", ["arg"]]) == FuncCall("Fn", ("arg",), span=_SPAN)
    assert mixin.function_call(_META, ["Fn", Token("LPAREN", "("), ["arg1", "arg2"], Token("RPAREN", ")")]) == FuncCall(
        "Fn", ("arg1", "arg2"), span=_SPAN
    )
    assert mixin.assignment_statement(_META, [VarRef("Target"), "Value"]) == Assignment(
        VarRef("Target"), "Value", span=_SPAN
    )
    assert mixin.assignment_statement(_META, [VarRef("Target"), Token("EQUAL", "="), "Value"]) == (
        Assignment(VarRef("Target"), "Value", span=_SPAN)
    )
    with pytest.raises(ValueError, match="target must be a VarRef"):
        mixin.assignment_statement(_META, ["Target", "Value"])

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
    assert mixin.ternary_if(_META, ternary_items) == TernaryOp(
        branches=(("cond1", "value1"), ("cond2", "value2")),
        else_expr="fallback",
        span=_SPAN,
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
    assert mixin.if_statement(_META, if_items) == IfStmt(
        branches=(("cond1", ("stmt1",)), ("cond2", ("stmt2",))),
        else_block=("stmt3",),
        span=_SPAN,
    )
    assert mixin.if_statement(_META, [Token("IGNORED", "?"), *if_items]) == IfStmt(
        branches=(("cond1", ("stmt1",)), ("cond2", ("stmt2",))),
        else_block=("stmt3",),
        span=_SPAN,
    )
    assert mixin.statement(_META, [Token("IGNORED", "?"), "assignment"]) == "assignment"
    assert mixin.statement(_META, [Token("IGNORED", "?"), FuncCall("Fn", ("arg",))]) == FuncCallStmt(
        FuncCall("Fn", ("arg",)), span=_SPAN
    )
    with pytest.raises(ValueError, match="statement expected a non-Token child"):
        mixin.statement(_META, [Token("ONLY", "token")])
    with pytest.raises(ValueError, match="statement expected a non-Token child"):
        mixin.statement(_META, [])


def test_expression_and_value_literal_allowlists_are_symmetric():
    # Expressions end their recursion in the same `value` production that the
    # standalone value contexts (interact assignments, format strings, colour
    # tails, proc args) use, so the literal allowlist is one source of truth.
    # Pin that structure so the two contexts can never drift apart.
    grammar = _repo_path("src", "sattline_parser", "grammar", "sattline.lark").read_text(encoding="utf-8")
    value_line = next(line.strip() for line in grammar.splitlines() if line.startswith("value:"))
    assert {t for t in value_line.split()[1:] if t != "|"} == {"BOOL", "REAL", "STRING", "SIGNED_INT"}

    plain_value_line = next(line.strip() for line in grammar.splitlines() if line.startswith("plain_value:"))
    assert {t for t in plain_value_line.split()[1:] if t != "|"} == {
        "BOOL_NOTAIL",
        "REAL_NOTAIL",
        "STRING_NOTAIL",
        "SIGNED_INT_NOTAIL",
    }

    # The expression `term` rule must route literals through `value` (never
    # through a separate, parallel literal set).
    term_block = grammar.split("?term:", 1)[1].split("?")[0]
    assert "| value" in term_block

    # Behavioural check: each literal kind accepted by `value` also parses as
    # an expression operand, and each is accepted in a standalone value
    # context (interact assignment) too.
    cases = {
        "int": "Sink = 1;",
        "real": "Sink = 1.5;",
        "bool": "Sink = True;",
    }
    for literal_kind, equation_stmt in cases.items():
        bp = _parse_to_basepicture(
            '"SyntaxVersion"\n'
            '"OriginalFileDate"\n'
            '"ProgramDate"\n'
            "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
            "LOCALVARIABLES\n"
            "   Sink: integer := 0;\n"
            "   Flag: boolean := False;\n"
            "ModuleDef\n"
            "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            "ModuleCode\n"
            "   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
            f"      {equation_stmt}\n"
            "ENDDEF (*BasePicture*);\n"
        )
        assignment = bp.modulecode.equations[0].code[0]
        assert isinstance(assignment, Assignment)
        assert not isinstance(assignment.value, VarRef), f"{literal_kind} literal did not parse as expression operand"

        value_bp = _parse_to_basepicture(
            '"SyntaxVersion"\n'
            '"OriginalFileDate"\n'
            '"ProgramDate"\n'
            "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
            "LOCALVARIABLES\n"
            "   Flag: boolean := False;\n"
            "ModuleDef\n"
            "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            "InteractObjects :\n"
            "   ComBut_ ( -0.8 , 0.6 ) ( 0.8 , 0.4 )\n"
            "      Bool_Value\n"
            f"      Variable = {'0' if literal_kind == 'int' else '0.5' if literal_kind == 'real' else 'False'}\n"
            "ENDDEF (*BasePicture*);\n"
        )
        assert value_bp.moduledef is not None
        assert value_bp.moduledef.interact_objects
