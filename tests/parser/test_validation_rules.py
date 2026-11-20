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
    ScalarDatatype,
    Sequence,
    SFCBodyItem,
    SFCCodeBlocks,
    SFCStep,
    SFCTransition,
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


def _var(name: str, datatype: ScalarDatatype | str) -> Variable:
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
    bp.modulecode = ModuleCode(equationblocks=[_equation(*items)])
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


def test_anytype_argument_is_exempt_from_the_builtin_argument_rule() -> None:
    """``AnyType`` proves nothing about the value, so the parameter accepts it."""
    call = FuncCallStmt(FuncCall(name="ClearStatusMac", args=(VarRef("Raw"),)))
    assert _codes(_bp(call, variables=[_var("Raw", "AnyType")])) == []


def test_string_literal_is_accepted_for_a_documented_in_string_parameter() -> None:
    """A documented ``in`` String parameter names a value, so the literal is legal."""
    call = FuncCallStmt(FuncCall(name="LoggedIn", args=("operator",)))
    assert _codes(_bp(call, variables=[])) == []


def test_string_literal_is_rejected_for_an_unknown_callee() -> None:
    """No signature means no evidence that the callee takes a value there."""
    call = FuncCallStmt(FuncCall(name="UserProcedure", args=("text",)))
    assert _codes(_bp(call, variables=[])) == ["SL-V015"]


def test_string_literal_is_rejected_for_a_written_string_parameter() -> None:
    """CopyString's destination is an ``out`` buffer, not a value position."""
    call = FuncCallStmt(FuncCall(name="CopyString", args=(VarRef("Source"), "text", VarRef("Status"))))
    codes = _codes(_bp(call, variables=[_var("Source", "string"), _var("Status", "integer")]))
    assert "SL-V015" in codes
    assert "SL-V014" in codes


def test_string_literal_is_rejected_for_an_in_var_string_parameter() -> None:
    """An ``in var`` parameter names a buffer, so a literal is not a value there."""
    call = FuncCallStmt(FuncCall(name="StringLength", args=("text",)))
    codes = _codes(_bp(call, variables=[]))
    assert "SL-V015" in codes
    assert "SL-V046" in codes


def test_step_auto_variable_hold_requires_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("S1.Hold")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" in _codes(bp)


def test_step_auto_variable_hold_is_allowed_with_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("S1.Hold")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True), seqcontrol=True)],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_step_auto_variable_t_requires_seqtimer() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("S1.T")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "integer")]
    assert "SL-V051" in _codes(bp)


def test_step_auto_variable_x_is_always_available() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("S1.X")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_sequence_hold_requires_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.Hold")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" in _codes(bp)


def test_sequence_disable_is_allowed_with_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.Disable")))],
        sequences=[
            _sequence(step, SFCTransition(name="T1", condition=True), name="Seq", seqcontrol=True),
        ],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V019" not in _codes(bp)
    assert "SL-V051" not in _codes(bp)


def test_sequence_disable_requires_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.Disable")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True), name="Seq")],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" in _codes(bp)


def test_step_disable_is_an_undefined_reference() -> None:
    """A step exposes .X/.Hold/.Reset/.T, not .Disable."""
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("S1.Disable")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True), seqcontrol=True)],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V019" in _codes(bp)
    assert "SL-V051" not in _codes(bp)


def test_unknown_step_accessor_is_an_undefined_reference() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("S1.Foo")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V019" in _codes(bp)
    assert "SL-V051" not in _codes(bp)


def test_sequence_x_is_not_a_runtime_accessor() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.X")))],
        sequences=[
            _sequence(step, SFCTransition(name="T1", condition=True), name="Seq", seqcontrol=True),
        ],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V019" in _codes(bp)
    assert "SL-V051" not in _codes(bp)


def test_step_auto_variable_variable_root_is_skipped() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Rec.Hold")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "boolean"), _var("Rec", "Rec")]
    bp.datatype_defs = []
    assert "SL-V051" not in _codes(bp)


def test_identifier_too_long_is_flagged() -> None:
    bp = _bp(variables=[_var("A" * 21, "integer")])
    assert "SL-V038" in _codes(bp)


def test_reserved_keyword_identifier_is_flagged() -> None:
    bp = _bp(variables=[_var("ModuleDef", "integer")])
    assert "SL-V039" in _codes(bp)


def test_reserved_boolean_spellings_are_flagged_as_identifiers() -> None:
    for name in ("True", "False"):
        bp = _bp(variables=[_var(name, "integer")])
        assert "SL-V039" in _codes(bp), name


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
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(call, Assignment(VarRef("Sink"), ternary))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "string")]
    codes = _codes(bp)
    assert codes.count("SL-V051") == 2


def test_step_auto_variable_unknown_suffix_is_skipped() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("S1.Other")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_sequence_runtime_accessor_with_a_step_suffix_is_skipped() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.X")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True))],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_sequence_hold_is_allowed_with_seqcontrol() -> None:
    step = SFCStep(kind="init", name="S1", code=SFCCodeBlocks())
    bp = BasePicture(header=_header())
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Seq.Hold")))],
        sequences=[_sequence(step, SFCTransition(name="T1", condition=True), seqcontrol=True)],
    )
    bp.localvariables = [_var("Sink", "boolean")]
    assert "SL-V051" not in _codes(bp)


def test_arithmetic_rejects_non_numeric_operands() -> None:
    assert _codes(_bp(Assignment(VarRef("Sink"), BinOp(1, "+", "text")), variables=[_var("Sink", "integer")])) == [
        "SL-V028"
    ]


def test_assignment_to_plain_string_is_rejected() -> None:
    assert _codes(_bp(Assignment(VarRef("Text"), 1), variables=[_var("Text", "string")])) == ["SL-V045", "SL-V029"]


def test_direct_assignment_is_rejected_for_every_string_family() -> None:
    """``SL-V045`` covers every native string family, not only ``String``.

    The destination datatype decides the finding, so each family reports it and
    the source family does not matter. See docs/validation.md.
    """
    for datatype in ("identstring", "tagstring", "maxstring", "linestring"):
        assert _codes(_bp(Assignment(VarRef("Text"), "value"), variables=[_var("Text", datatype)])) == ["SL-V045"], (
            datatype
        )
    assert _codes(_bp(Assignment(VarRef("Text"), "value"), variables=[_var("Text", "string")])) == ["SL-V045"]


def test_temporal_numeric_pair_rejects_none() -> None:
    assert _temporal_numeric_pair(None, "integer") is False
    assert _temporal_numeric_pair("integer", None) is False


def test_allow_unresolved_external_datatypes_suppresses_unknown_names() -> None:
    bp = _bp(variables=[_var("Bad", "NotAType")])
    assert _codes(bp) == ["SL-V020"]
    assert validate_basepicture(bp, allow_unresolved_external_datatypes=True) == ()
