# pyright: reportPrivateUsage=false
"""Tests for the expression, builtin, identifier, and SFC rules."""

from __future__ import annotations

from sattline_parser.models.ast_model import (
    Assignment,
    BasePicture,
    CodeItem,
    Equation,
    ModuleCode,
    ModuleHeader,
    Sequence,
    SFCBodyItem,
    SFCCodeBlocks,
    SFCStep,
    SFCTransition,
    Simple_DataType,
    Variable,
)
from sattline_parser.models.expressions import (
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    FuncCallStmt,
    NotOp,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.code import _temporal_numeric_pair


def _var(name: str, datatype: Simple_DataType | str) -> Variable:
    return Variable(name=name, datatype=datatype)


def _header(name: str = "BasePicture") -> ModuleHeader:
    return ModuleHeader(name=name, invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0))


def _equation(*items: CodeItem) -> Equation:
    return Equation(name="Main", position=(0.0, 0.0), size=(1.0, 1.0), code=list(items))


def _sequence(*items: SFCBodyItem, name: str = "Seq", seqcontrol: bool = False, seqtimer: bool = False) -> Sequence:
    return Sequence(
        name=name,
        type="SEQUENCE",
        position=(0.0, 0.0),
        size=(1.0, 1.0),
        seqcontrol=seqcontrol,
        seqtimer=seqtimer,
        code=list(items),
    )


def _bp(*items: CodeItem, variables: list[Variable] | None = None) -> BasePicture:
    bp = BasePicture(header=_header())
    bp.localvariables = variables or []
    bp.modulecodes = [ModuleCode(equations=[_equation(*items)])]
    return bp


def _codes(bp: BasePicture) -> list[str]:
    return [diagnostic.code.value for diagnostic in validate_basepicture(bp)]


def test_logical_operators_require_boolean_operands() -> None:
    assert _codes(_bp(Assignment(VarRef("Sink"), BoolOp("AND", (1, 2))), variables=[_var("Sink", "boolean")])) == [
        "SL-V043",
        "SL-V043",
    ]
    assert _codes(_bp(Assignment(VarRef("Sink"), NotOp(1)), variables=[_var("Sink", "boolean")])) == ["SL-V043"]


def test_logical_operators_accept_boolean_operands() -> None:
    assert (
        _codes(
            _bp(
                Assignment(VarRef("Sink"), BoolOp("AND", (VarRef("A"), VarRef("B")))),
                variables=[_var("Sink", "boolean"), _var("A", "boolean"), _var("B", "boolean")],
            )
        )
        == []
    )


def test_unary_operator_requires_numeric_operand() -> None:
    assert _codes(
        _bp(
            Assignment(VarRef("Sink"), UnaryOp("-", VarRef("Flag"))),
            variables=[_var("Sink", "integer"), _var("Flag", "boolean")],
        )
    ) == ["SL-V028"]


def test_ternary_branches_must_be_compatible() -> None:
    ternary = TernaryOp(branches=((True, VarRef("Flag")),), else_expr=VarRef("Count"))
    assert _codes(
        _bp(
            Assignment(VarRef("Sink"), ternary),
            variables=[_var("Sink", "boolean"), _var("Flag", "boolean"), _var("Count", "integer")],
        )
    ) == ["SL-V044"]


def test_equality_rejects_incompatible_operands() -> None:
    assert _codes(
        _bp(
            Assignment(VarRef("Sink"), Compare(VarRef("Flag"), "==", VarRef("Count"))),
            variables=[_var("Sink", "boolean"), _var("Flag", "boolean"), _var("Count", "integer")],
        )
    ) == ["SL-V041"]


def test_ordering_allows_temporal_against_numeric() -> None:
    assert (
        _codes(
            _bp(
                Assignment(VarRef("Sink"), Compare(VarRef("Elapsed"), ">", 2.5)),
                variables=[_var("Sink", "boolean"), _var("Elapsed", "duration")],
            )
        )
        == []
    )


def test_builtin_in_var_argument_must_be_a_variable() -> None:
    call = FuncCallStmt(FuncCall(name="StringLength", args=(5,)))
    assert _codes(_bp(call, variables=[])) == ["SL-V046"]


def test_builtin_argument_datatype_mismatch() -> None:
    call = FuncCallStmt(FuncCall(name="StringLength", args=(VarRef("Flag"),)))
    assert _codes(_bp(call, variables=[_var("Flag", "boolean")])) == ["SL-V047"]


def test_builtin_argument_datatype_match_is_silent() -> None:
    call = FuncCallStmt(FuncCall(name="StringLength", args=(VarRef("Text"),)))
    assert _codes(_bp(call, variables=[_var("Text", "string")])) == []


def test_step_auto_variable_hold_requires_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("S1.Hold")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
        )
    ]
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" in _codes(bp)


def test_step_auto_variable_hold_is_allowed_with_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("S1.Hold")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True), seqcontrol=True)],
        )
    ]
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_step_auto_variable_t_requires_seqtimer() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("S1.T")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
        )
    ]
    bp.localvariables = [_var("Sink", "integer")]
    assert "SL-V051" in _codes(bp)


def test_step_auto_variable_x_is_always_available() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("S1.X")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
        )
    ]
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_sequence_hold_requires_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.Hold")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
        )
    ]
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" in _codes(bp)


def test_step_auto_variable_variable_root_is_skipped() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("Rec.Hold")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
        )
    ]
    bp.localvariables = [_var("Sink", "boolean"), _var("Rec", "Rec")]
    bp.datatype_defs = []
    assert "SL-V051" not in _codes(bp)


def test_identifier_too_long_is_flagged() -> None:
    bp = _bp(variables=[_var("A" * 21, "integer")])
    assert "SL-V038" in _codes(bp)


def test_reserved_keyword_identifier_is_flagged() -> None:
    bp = _bp(variables=[_var("ModuleDef", "integer")])
    assert "SL-V039" in _codes(bp)


def test_quoted_identifier_may_use_a_keyword() -> None:
    bp = _bp(variables=[_var("'ModuleDef'", "integer")])
    assert "SL-V039" not in _codes(bp)


def test_base_picture_header_is_exempt_from_keyword_check() -> None:
    bp = BasePicture(header=_header("BasePicture"))
    assert "SL-V039" not in _codes(bp)


def test_identifier_rules_cover_datatypes_modules_and_sequences() -> None:
    bp = _bp()
    bp.datatype_defs = []
    bp.header = _header("A" * 21)
    assert "SL-V038" in _codes(bp)


def test_step_auto_variables_walk_function_calls_and_ternaries() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    call = FuncCallStmt(FuncCall(name="StringLength", args=(VarRef("S1.Hold"),)))
    ternary = TernaryOp(branches=((True, VarRef("S1.T")),), else_expr=VarRef("Sink"))
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(call, Assignment(VarRef("Sink"), ternary))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
        )
    ]
    bp.localvariables = [_var("Sink", "string")]
    codes = _codes(bp)
    assert codes.count("SL-V051") == 2


def test_step_auto_variable_unknown_suffix_is_skipped() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("S1.Other")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
        )
    ]
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_sequence_runtime_accessor_with_a_step_suffix_is_skipped() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.X")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
        )
    ]
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_sequence_hold_is_allowed_with_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecodes = [
        ModuleCode(
            equations=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.Hold")))],
            sequences=[_sequence(step, SFCTransition(name="T1", condition=True), seqcontrol=True)],
        )
    ]
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_arithmetic_rejects_non_numeric_operands() -> None:
    assert _codes(_bp(Assignment(VarRef("Sink"), BinOp(1, "+", "text")), variables=[_var("Sink", "integer")])) == [
        "SL-V028"
    ]


def test_assignment_to_plain_string_is_rejected() -> None:
    assert _codes(_bp(Assignment(VarRef("Text"), 1), variables=[_var("Text", "string")])) == ["SL-V045", "SL-V029"]


def test_temporal_numeric_pair_rejects_none() -> None:
    assert _temporal_numeric_pair(None, "integer") is False
    assert _temporal_numeric_pair("integer", None) is False


def test_allow_unresolved_external_datatypes_suppresses_unknown_names() -> None:
    bp = _bp(variables=[_var("Bad", "NotAType")])
    assert _codes(bp) == ["SL-V020"]
    assert validate_basepicture(bp, allow_unresolved_external_datatypes=True) == ()
