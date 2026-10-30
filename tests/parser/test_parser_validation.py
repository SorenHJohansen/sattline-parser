# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportArgumentType=false
# ruff: noqa: F403, F405
"""Tests for the strict single-source validation pass.

Wires the ``tests/fixtures/corpus/invalid`` fixtures that parse successfully to
their expected diagnostic codes, asserts the consumer-layer boundary for
cross-module contract mismatches, gates the whole valid/edge corpus against
false positives, and covers every branch of the validators with hand-built ASTs.
"""

import pathlib

from sattline_parser import parse_and_validate
from sattline_parser.preprocessing.compressed import PreprocessError
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.builtins import (
    BUILTIN_DATATYPE_NAMES,
    builtin_datatype_typo,
    builtin_function_signature,
    is_builtin_function,
)
from sattline_parser.validation.diagnostics import (
    RETIRED_CODES,
    Diagnostic,
    DiagnosticCode,
    DiagnosticSeverity,
)
from sattline_parser.validation.literals import is_valid_duration, is_valid_time
from sattline_parser.validation.symbols import SFC_RUNTIME_CONSTANTS, build_scope, resolve_var
from sattline_parser.validation.typing import (
    TypeFamily,
    assignment_is_compatible,
    datatype_family,
    family_of,
    infer_expr_type,
    is_boolean,
    is_numeric,
    operand_types,
)

from ._parser_core_test_support import *

#: Fixtures for rules the real parser ENFORCES.
_INVALID_VALIDATION_FIXTURES: dict[str, str] = {
    "OpSaveAndStateCombined": "SL-V031",
    "CoordinateInvarTail": "SL-V032",
    "ReservedNameVarOff": "SL-V034",
    "ReservedNameVarOn": "SL-V034",
    "SequenceParallel": "SL-V033",
    "SubSequenceDefinition": "SL-V033",
    "TerminalSeqStep": "SL-V033",
    "DuplicateSiblingSubmodules": "SL-V004",
    "OldNewOnNonState": "SL-V005",
    "OldNewOnNonStateRecordField": "SL-V006",
    "WriteToConstVariable": "SL-V007",
    "BuiltinWrongArity": "SL-V013",
    "BuiltinOutArgNotVariable": "SL-V014",
    "StringLiteralInCallArgument": "SL-V015",
    "ConsecutiveSeqSteps": "SL-V016",
    "SeqForkUnknownTarget": "SL-V017",
    "BuiltinDatatypeTypo": "SL-V018",
    "UndefinedVariableRef": "SL-V019",
    "UnknownDatatypeName": "SL-V020",
    "DuplicateSFCElementNames": "SL-V021",
    "SFCAlternativeBranchStartsWithStep": "SL-V023",
    "SFCParallelBranchStartsWithTransition": "SL-V024",
    "ConstVarAsBuiltinOutArg": "SL-V007",
    "CrossModuleContractMismatch": "SL-V027",
    "NonNumericComparisonOperand": "SL-V028",
    "TemporalVsTemporalCompare": "SL-V028",
    "OpSaveConstCombined": "SL-V031",
    "WriteToOldState": "SL-V035",
    "AssignmentFamilyMismatch": "SL-V029",
    "IfConditionNotBoolean": "SL-V030",
}

#: Fixtures for rules the real parser does NOT enforce. Kept as files so the
#: retirement stays visible and re-testable: the code must emit nothing for
#: these, because the editor refuses to CREATE such a declaration but its
#: parser ACCEPTS the same source loaded from disk (2026-10-05 batch run).
_RETIRED_VALIDATION_FIXTURES: dict[str, str] = {
    "DuplicateDatatypeName": "SL-V001",
    "DuplicateModuletypeName": "SL-V002",
    "DuplicateVariableNames": "SL-V003",
    "InitValueTypeMismatch": "SL-V008",
    "BadBareDurationString": "SL-V009",
    "BadBareTimeString": "SL-V010",
    "BadDurationLiteral": "SL-V011",
    "BadTimeLiteral": "SL-V012",
    "SFCInitStepNotFirst": "SL-V022",
    "SFCInitStepRepeated": "SL-V022",
    "DuplicateRecordFieldName": "SL-V025",
    "DatatypeShadowsBuiltinName": "SL-V026",
}

_PARSE_REJECTED_FIXTURES = [
    # A coded file that spells `SeqControl`/`SeqTimer` raw: those are identifiers
    # in coded mode, so the sequence-control slot rejects the unit.
    "CodedRawKeyword",
    "CoordInVarTail",
    "ModuleDefNoTrailingEnddef",
    "EncodingStress",
    "FreestandingCommentInModuleCode",
    "GraphObjectsDoubleLayer",
    "GraphObjectsSectionLayer",
    "Malformed",
    "ModuleCodeWithoutModuleDef",
    "NotSattLine",
    "OversizedInput",
    "UnterminatedComment",
]


def _corpus(path: str) -> pathlib.Path:
    return _repo_path("tests", "fixtures", "corpus", path)


def _raw(p: pathlib.Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1")


def _var(
    name: str,
    datatype: object,
    const: bool | None = False,
    state: bool | None = False,
    init_value: object | None = None,
    init_is_duration: bool = False,
) -> Variable:
    return Variable(
        name=name, datatype=datatype, const=const, state=state, init_value=init_value, init_is_duration=init_is_duration
    )


def _equation(*items: object, name: str = "Main") -> Equation:
    return Equation(name=name, position=(0.0, 0.0), size=(1.0, 1.0), code=[i for i in items if i is not None])


def _sequence(*items: object, name: str = "Seq", type: str = "SEQUENCE") -> Sequence:
    return Sequence(
        name=name, type=type, position=(0.0, 0.0), size=(1.0, 1.0), code=[i for i in items if i is not None]
    )


def _base_picture() -> BasePicture:
    return BasePicture(header=_module_header())


def test_invalid_validation_fixtures_report_expected_codes():
    for stem, expected_code in _INVALID_VALIDATION_FIXTURES.items():
        bp, diagnostics = parse_and_validate(_raw(_corpus(f"invalid/{stem}.s")))
        codes = {d.code.value for d in diagnostics}
        assert DiagnosticCode(expected_code) in {d.code for d in diagnostics}, f"{stem}: got {sorted(codes)}"
        assert bp is not None


def test_retired_validation_fixtures_report_nothing():
    """The real parser accepts these, so we must not reject them either.

    Each was implemented because the editor's UI refuses to CREATE the
    declaration, then disproved by loading the same source from disk. See
    ``RETIRED_CODES``.
    """
    for stem, expected_code in _RETIRED_VALIDATION_FIXTURES.items():
        bp, diagnostics = parse_and_validate(_raw(_corpus(f"invalid/{stem}.s")))
        codes = sorted({d.code.value for d in diagnostics})
        assert expected_code not in codes, f"{stem}: still reports {expected_code} (all: {codes})"
        assert bp is not None


def test_every_retired_code_is_documented_and_actually_unemitted():
    """No retired code may be emitted anywhere in the corpus.

    Guards against a retirement that only removed the fixture mapping while the
    check itself kept firing.
    """
    retired_values = {code.value for code in RETIRED_CODES}
    assert retired_values, "RETIRED_CODES must not be empty"

    for subdir in ("valid", "edge_cases", "invalid"):
        for path in sorted(_corpus(subdir).glob("*.s")):
            try:
                _bp, diagnostics = parse_and_validate(_raw(path))
            except (UnexpectedInput, PreprocessError):
                # Parse- or decode-rejected files never reach validation, so they
                # cannot leak a retired code either.
                continue
            leaked = retired_values & {d.code.value for d in diagnostics}
            assert not leaked, f"{subdir}/{path.name} still emits {sorted(leaked)}"


def test_cross_module_contract_mismatch_flagged():
    _bp, diagnostics = parse_and_validate(_raw(_corpus("invalid/CrossModuleContractMismatch.s")))
    assert "SL-V027" in {d.code.value for d in diagnostics}
    assert any("EnableFlag" in d.message and "CounterValue" in d.message for d in diagnostics)


def test_parse_rejected_fixtures_still_raise_parse_errors():
    for stem in _PARSE_REJECTED_FIXTURES:
        with pytest.raises(UnexpectedInput):
            parser_core_parse_source_text(_raw(_corpus(f"invalid/{stem}.s")))


def test_valid_and_edge_corpus_have_no_validation_diagnostics():
    for subdir in ("valid", "edge_cases"):
        for path in sorted(_corpus(subdir).glob("*.s")):
            bp, diagnostics = parse_and_validate(_raw(path))
            assert diagnostics == (), f"{subdir}/{path.name}: {[(d.code.value, d.message) for d in diagnostics]}"
            assert bp is not None


# These pairings were previously pinned by reading probes/*.x straight out of
# the probe tree. The evidence now travels in each fixture's header comment, so
# CI has no dependency on probes/. Every case asserts BOTH sides: relaxing one
# half of a rule without its counter-case fails here even though the generic
# valid-corpus loop and the _INVALID_VALIDATION_FIXTURES table would still pass.


def _codes(subdir: str, stem: str) -> set[str]:
    return {d.code.value for d in parse_and_validate(_raw(_corpus(f"{subdir}/{stem}.s")))[1]}


def test_temporal_comparison_keeps_both_sides():
    """A duration/time against a NUMERIC LITERAL is clean (EdgeDurCmpInt,
    EdgeDurCmpReal, EdgeTimeCmpInt); against another temporal operand it is
    still SL-V028 (EdgeBareDurZero, EdgeNegDurVal, ValidDurAndTime)."""
    assert _codes("valid", "TemporalVsNumericCompare") == set()
    assert _codes("invalid", "TemporalVsTemporalCompare") == {"SL-V028"}


def test_opsave_modifier_order_keeps_both_sides():
    """`State OpSave` compiles (OpSaveStateReversed); the `OpSave State` and
    `OpSave Const` spellings are both an illegal attribute mix
    (EdgeOpSaveAndState, OpSaveConst)."""
    assert _codes("valid", "VariableModifiers") == set()
    assert _codes("invalid", "OpSaveAndStateCombined") == {"SL-V031"}
    assert _codes("invalid", "OpSaveConstCombined") == {"SL-V031"}


def test_enable_paren_tail_is_accepted_on_graph_and_interact_objects():
    """Graph objects take Enable_ bare and with a paren tail (EdgePropEnable,
    EdgePropParenTail). Interactors do too: ABB's own libraries use
    `Enable_ = True : (EnableAck AND …)` on ComBut_ (GC/ABBLib/EventLib.x), so the
    single-probe verdict that made the InVar_ tail mandatory there is superseded
    by corpus evidence."""
    assert _codes("valid", "GraphObjectEnableVariants") == set()
    assert _codes("valid", "InteractEnableParenTail") == set()


def test_duration_literal_format_table():
    for value in (
        "0d0h0m0s0ms",
        "1d2h3m4s500ms",
        "-0d0h5m0s0ms",
        "1h",
        "4m",
        "30s",
        "7m6s123ms",
        "5d5h3m6.5s",
        "2h15m30s",
        "12.345",
        "0",
        "3600",
        "500ms",
    ):
        assert is_valid_duration(value), value
    for value in ("not-a-duration", "", "-", "5xyz", "1d2m3", "12.34.5", "d", "h", "1d h", "-x"):
        assert not is_valid_duration(value), value


def test_time_literal_format_table():
    for value in ("2026-01-01-00:00:00.000", "2026-12-31-23:59:59.999"):
        assert is_valid_time(value), value
    for value in ("2026/04/23 12:00:00", "not-a-timestamp", "", "2026-01-01-00:00:00"):
        assert not is_valid_time(value), value


def test_builtin_table_and_typo_helpers():
    assert is_builtin_function("equALstrings")
    assert builtin_function_signature("EqualStrings") is not None
    assert builtin_function_signature("NoSuchBuiltin") is None
    equal_strings = builtin_function_signature("EqualStrings")
    assert equal_strings is not None and equal_strings.min_args == 3 and equal_strings.max_args == 3
    copytime = builtin_function_signature("CopyTime")
    assert copytime is not None and copytime.out_arg_positions == frozenset({2})
    assert builtin_datatype_typo("intege") == "integer"
    assert builtin_datatype_typo("SensorType") is None
    assert builtin_datatype_typo("intege") in BUILTIN_DATATYPE_NAMES
    for name in BUILTIN_DATATYPE_NAMES:
        assert builtin_function_signature(name) is None


def test_scope_and_resolution_helpers():
    outer = build_scope(None, [_var("Timer", "integer")])
    inner = build_scope(outer, [_var("Local", "boolean")])
    assert inner.lookup("Timer") is not None
    assert inner.lookup("LOCAL") is not None
    assert inner.lookup("Missing") is None
    assert outer.lookup("Local") is None
    records = {}
    assert resolve_var(VarRef(name="Nothing"), inner, records) is None
    assert resolve_var(VarRef(name="Local"), inner, records) is not None


def test_qualification_resolves_record_fields():
    record = DataType(name="Point", description=None, datecode=1, var_list=[_var("X", "real")])
    records = {"point": record}
    bp = _base_picture()
    bp.datatype_defs = [record]
    bp.localvariables = [_var("Pos", "Point")]
    scope = build_scope(None, bp.localvariables)
    assert resolve_var(VarRef(name="Pos.X"), scope, records) is not None
    assert resolve_var(VarRef(name="Pos.Missing"), scope, records) is None
    assert resolve_var(VarRef(name="Pos"), scope, records) is not None
    diagnostics = validate_basepicture(bp)
    assert diagnostics == ()


def test_write_to_const_variable_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("MaxLimit", "integer", const=True)]
    bp.modulecodes = [ModuleCode(equations=[_equation(Assignment(VarRef("MaxLimit"), 1))])]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V007" in codes


def test_undefined_variable_references_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("Input", "integer"), _var("Mystery", "integer")]
    bp.modulecodes = [
        ModuleCode(
            equations=[
                _equation(
                    Assignment(VarRef("Input"), 0),
                    Assignment(VarRef("Sub.Out"), 1, span=None),
                    Assignment(VarRef("Mystery.x"), 1, span=None),
                )
            ]
        )
    ]
    codes = [d.code.value for d in validate_basepicture(bp)]
    assert codes.count("SL-V019") == 2


def test_old_new_on_non_state_variable_and_field_flagged():
    record_type = DataType(
        name="CmdType",
        description=None,
        datecode=1,
        var_list=[_var("Flag", "boolean", state=True), _var("Other", "boolean")],
    )
    bp = _base_picture()
    bp.datatype_defs = [record_type]
    bp.localvariables = [_var("Counter", "integer"), _var("CMD", "CmdType")]
    bp.modulecodes = [
        ModuleCode(
            equations=[
                _equation(
                    IfStmt(
                        branches=(
                            (
                                Compare(VarRef("Counter", state="old"), "==", 0),
                                (Assignment(VarRef("Out", span=None), 1, span=None),),
                            ),
                        ),
                        else_block=None,
                    ),
                    Assignment(VarRef("Out", span=None), VarRef("CMD.Other", state="old"), span=None),
                )
            ]
        )
    ]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V005" in codes
    assert "SL-V006" in codes


def test_old_new_on_state_symbols_not_flagged():
    record_type = DataType(name="CmdType", description=None, datecode=1, var_list=[_var("Flag", "boolean", state=True)])
    bp = _base_picture()
    bp.datatype_defs = [record_type]
    bp.localvariables = [_var("Counter", "integer", state=True), _var("CMD", "CmdType")]
    bp.modulecodes = [
        ModuleCode(
            equations=[
                _equation(
                    BoolOp("AND", (VarRef("Counter", state="old"), VarRef("CMD.Flag", state="new"))),
                )
            ]
        )
    ]
    assert validate_basepicture(bp) == ()


def test_scalar_init_types_accepted():
    bp = _base_picture()
    bp.datatype_defs = [DataType(name="Point", description=None, datecode=1, var_list=[_var("X", "real")])]
    bp.localvariables = [
        _var("I", "integer", init_value=3),
        _var("R", "real", init_value=3),
        _var("RF", "real", init_value=3.5),
        _var("B", "boolean", init_value=True),
        _var("S", "string", init_value="x"),
        _var("Rec", "Point", init_value={"Time_Value": "2026-01-01-00:00:00.000"}),
        _var("Weird", "integer", init_value=[1, 2]),
    ]
    assert validate_basepicture(bp) == ()


def test_retired_rules_stay_silent_on_hand_built_asts():
    """Direct AST coverage for the retired rules, independent of the fixtures.

    Mirrors the deleted per-rule tests: every shape that used to be reported is
    now built explicitly and must produce nothing. If a check is ever
    reintroduced, this fails even if the fixture files are edited.
    """
    duplicate_variable = _base_picture()
    duplicate_variable.localvariables = [_var("Counter", "integer"), _var("counter", "integer")]
    assert validate_basepicture(duplicate_variable) == ()

    scalar_inits = _base_picture()
    scalar_inits.localvariables = [
        _var("BadInt", "integer", init_value="not a number"),
        _var("BadReal", "real", init_value=True),
        _var("BadFloatInt", "integer", init_value=1.5),
    ]
    assert validate_basepicture(scalar_inits) == ()

    keyworded_inits = _base_picture()
    keyworded_inits.localvariables = [
        _var("D", "duration", init_is_duration=True, init_value="not-a-duration"),
        _var("D2", "duration", init_value=7),
        _var("T", "time", init_value={"Time_Value": "2026/04/23 12:00:00"}),
        _var("T2", "time", init_value={"Time_Value": None}),
    ]
    assert validate_basepicture(keyworded_inits) == ()

    duplicate_definitions = _base_picture()
    duplicate_definitions.datatype_defs = [
        DataType(name="SensorType", description=None, datecode=1, var_list=[]),
        DataType(name="SensorType", description=None, datecode=2, var_list=[]),
    ]
    duplicate_definitions.moduletype_defs = [
        ModuleTypeDef(name="Controller", datecode=1),
        ModuleTypeDef(name="controller", datecode=2),
    ]
    assert validate_basepicture(duplicate_definitions) == ()

    shadowing = _base_picture()
    shadowing.datatype_defs = [DataType(name="Integer", description=None, datecode=1, var_list=[])]
    assert validate_basepicture(shadowing) == ()

    duplicate_field = _base_picture()
    duplicate_field.datatype_defs = [
        DataType(
            name="Pair",
            description=None,
            datecode=1,
            var_list=[_var("Left", "real"), _var("left", "boolean")],
        )
    ]
    assert validate_basepicture(duplicate_field) == ()

    repeated_init = _base_picture()
    repeated_init.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    SFCStep(kind="init", name="First", code=SFCCodeBlocks()),
                    SFCTransition(name="TrA", condition=True),
                    SFCStep(kind="init", name="Second", code=SFCCodeBlocks()),
                    SFCTransition(name="TrB", condition=True),
                )
            ]
        )
    ]
    # Ends on a transition, so the only rule left is the one we retired.
    assert validate_basepicture(repeated_init) == ()


def test_datatype_typo_flagged_and_declared_records_exempt():
    bp = _base_picture()
    record = DataType(name="SensorType", description=None, datecode=1, var_list=[_var("Raw", "real")])
    bp.datatype_defs = [record]
    bp.localvariables = [_var("Counter", "intege"), _var("Sensor", "SensorType"), _var("Other", "duration")]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V018" in codes


def test_duplicate_sibling_submodules_flagged():
    bp = _base_picture()
    bp.submodules = [
        ModuleTypeInstance(header=_module_header("A"), moduletype_name="T"),
        ModuleTypeInstance(header=_module_header("a"), moduletype_name="T"),
    ]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V004" in codes


def test_string_literal_call_argument_flagged_for_any_call():
    bp = _base_picture()
    bp.localvariables = [_var("Input", "string", init_value="")]
    unknown = FuncCall(name="UserProc", args=("text",))
    bp.modulecodes = [ModuleCode(equations=[_equation(FuncCallStmt(unknown))])]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V015" in codes


def test_builtin_arity_and_out_arg_checks():
    bp = _base_picture()
    bp.localvariables = [_var("A", "string", init_value=""), _var("B", "string", init_value="")]
    fn_call = FuncCallStmt(FuncCall(name="EqualStrings", args=(VarRef("A"),)))
    copy_call = FuncCallStmt(FuncCall(name="CopyTime", args=(VarRef("A"), BoolOp("OR", (VarRef("A"), VarRef("B"))))))
    ok_call = FuncCallStmt(FuncCall(name="EqualStrings", args=(VarRef("A"), VarRef("B"), True)))
    unknown = FuncCallStmt(FuncCall(name="UserProc", args=(1, 2, 3, 4)))
    bp.modulecodes = [ModuleCode(equations=[_equation(fn_call, copy_call, ok_call, unknown)])]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V013" in codes
    assert "SL-V014" in codes
    assert codes == {"SL-V013", "SL-V014"}


def test_expression_walk_covers_all_node_kinds():
    fn = FuncCallStmt(FuncCall(name="Equal", args=(VarRef("A"), VarRef("B"))))
    expression_nodes = FuncCall(
        name="Mix",
        args=(
            UnaryOp("-", VarRef("A")),
            BinOp(VarRef("A"), "+", VarRef("B")),
            TernaryOp(branches=((True, 1),), else_expr=0),
            NotOp(True),
            Compare(VarRef("A"), "<", 1),
        ),
    )
    bp = _base_picture()
    bp.localvariables = [
        _var("A", "integer", init_value=0),
        _var("B", "integer", init_value=0),
        _var("Out", "integer", init_value=0),
    ]
    bp.modulecodes = [
        ModuleCode(equations=[_equation(fn, Assignment(VarRef("Out", span=None), expression_nodes, span=None))])
    ]
    diagnostics = validate_basepicture(bp)
    assert "SL-V013" not in {d.code.value for d in diagnostics}
    assert diagnostics == ()


def test_sfc_structural_rules_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("In", "integer", init_value=0)]
    step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks(active=[Assignment(VarRef("In"), 0)]))
    step2 = SFCStep(kind="step", name="Step2", code=SFCCodeBlocks())
    bp.modulecodes = [ModuleCode(sequences=[_sequence(step, step2)])]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V016" in codes


def test_sfc_fork_target_checks():
    # SEQFORK is a suffix of its host step/transition, never a body element.
    bad_step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks(), fork=SFCFork(targets=("Nope",)))
    bad = _base_picture()
    bad.modulecodes = [ModuleCode(sequences=[_sequence(bad_step)])]
    codes = {d.code.value for d in validate_basepicture(bad)}
    assert "SL-V017" in codes

    good_step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks())
    good_transition = SFCTransition(name="TrGo", condition=True, fork=SFCFork(targets=("Init",)))
    good = _base_picture()
    good.modulecodes = [ModuleCode(sequences=[_sequence(good_step, good_transition)])]
    assert validate_basepicture(good) == ()


def test_sfc_walk_covers_all_body_item_kinds():
    bp = _base_picture()
    bp.localvariables = [_var("V", "integer", init_value=0)]
    step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks(enter=[Assignment(VarRef("V"), 1)], exit=[]))
    transition = SFCTransition(name="TrMatch", condition=Compare(VarRef("V"), ">", 0))
    # A SUBSEQTRANSITION body is a transition_body: T (S T | M)*, so it opens with
    # a transition and closes on one after its step.
    transition_sub = SFCTransitionSub(
        name="TSub",
        body=[
            SFCTransition(name="TrSubOpen", condition=True),
            SFCStep(kind="step", name="SubStep", code=SFCCodeBlocks()),
            SFCTransition(name="TrSubClose", condition=True),
        ],
    )
    # An ALTERNATIVEBRANCH body is a transition_body as well.
    alterni = SFCAlternative(
        branches=[
            [
                SFCTransition(name="TrAlt", condition=True),
                SFCStep(kind="step", name="AltStep", code=SFCCodeBlocks()),
                SFCTransition(name="TrAltClose", condition=True),
            ]
        ]
    )
    # A PARALLELBRANCH body is a step_body: M* S (T M* S)*.
    parallel = SFCParallel(
        branches=[
            [
                SFCStep(kind="step", name="ParStep", code=SFCCodeBlocks()),
                SFCTransition(name="TrPar", condition=True),
                SFCStep(kind="step", name="ParStep2", code=SFCCodeBlocks()),
            ]
        ]
    )
    # A SUBSEQUENCE body is a closed_body: (S T | M)+.
    subsequence = SFCSubsequence(
        name="SubSeq",
        body=[
            SFCStep(kind="step", name="SubInner", code=SFCCodeBlocks()),
            SFCTransition(name="TrInner", condition=True),
        ],
    )
    comment = CodeComment(text="(* hi *)")
    second_step = SFCStep(kind="step", name="AfterSub", code=SFCCodeBlocks())
    trailing = SFCTransition(name="TrTail", condition=True)
    after_transition = SFCStep(kind="step", name="AfterTr", code=SFCCodeBlocks())
    after_sub = SFCStep(kind="step", name="AfterTSub", code=SFCCodeBlocks())
    # A fork hosted on a *transition* must name steps.
    transition.fork = SFCFork(
        targets=("Init", "AfterTr", "SubStep", "AltStep", "ParStep", "SubInner"),
        has_break=True,
    )
    # Positions: Init(S) TrMatch(T) ... every step is followed by a transition
    # and every transition by a step, with the SUBSEQUENCE as a structural unit.
    bp.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    step,
                    transition,
                    after_transition,
                    transition_sub,
                    after_sub,
                    alterni,
                    parallel,
                    trailing,
                    subsequence,
                    comment,
                    second_step,
                    SFCTransition(name="TrFinal", condition=True),
                )
            ]
        )
    ]
    assert validate_basepicture(bp) == ()


def test_sfc_step_and_transition_names_collected_for_fork():
    bp = _base_picture()
    init_step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks())
    run_step = SFCStep(kind="step", name="Run", code=SFCCodeBlocks())
    transitions = [
        SFCTransition(name="T0", condition=True),
        SFCTransition(name="T1", condition=True),
    ]
    mid_step = SFCStep(kind="step", name="Mid", code=SFCCodeBlocks())
    transition_sub = SFCTransitionSub(
        name="TSub",
        body=[
            SFCTransition(name="TrSubOpen", condition=True),
            SFCStep(kind="step", name="Nested", code=SFCCodeBlocks()),
            SFCTransition(name="TrSubClose", condition=True),
        ],
    )
    alt_transition = SFCTransition(name="TrAlt", condition=True)
    branch = SFCAlternative(
        branches=[
            [
                alt_transition,
                SFCStep(kind="step", name="NestedAlt", code=SFCCodeBlocks()),
                SFCTransition(name="TrAltClose", condition=True),
            ]
        ]
    )
    # Step targets only: the host is a transition, so the target kind is checked.
    transitions[0].fork = SFCFork(targets=("Run", "Mid", "Nested", "NestedAlt", "AfterSub", "Tail"))
    bp.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    init_step,
                    transitions[0],
                    run_step,
                    transitions[1],
                    mid_step,
                    transition_sub,
                    SFCStep(kind="step", name="AfterSub", code=SFCCodeBlocks()),
                    branch,
                    SFCStep(kind="step", name="Tail", code=SFCCodeBlocks()),
                    SFCTransition(name="TrEnd", condition=True),
                )
            ]
        )
    ]
    assert validate_basepicture(bp) == ()


def test_duplicate_sfc_element_names_flagged():
    bp = _base_picture()
    step_a = SFCStep(kind="step", name="Work", code=SFCCodeBlocks())
    step_b = SFCStep(kind="step", name="work", code=SFCCodeBlocks())
    bp.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    SFCStep(kind="init", name="Start", code=SFCCodeBlocks()),
                    SFCTransition(name="TrA", condition=True),
                    step_a,
                    SFCTransition(name="TrB", condition=True),
                    step_b,
                )
            ]
        )
    ]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V021" in codes


def test_sfc_branch_start_checks_skip_leading_comments():
    alt = _base_picture()
    alt.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    SFCStep(kind="init", name="Init", code=SFCCodeBlocks()),
                    SFCAlternative(
                        branches=[[CodeComment(text="(* c *)"), SFCStep(kind="step", name="Bad", code=SFCCodeBlocks())]]
                    ),
                )
            ]
        )
    ]
    assert "SL-V023" in {d.code.value for d in validate_basepicture(alt)}

    par = _base_picture()
    par.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    SFCStep(kind="init", name="Init", code=SFCCodeBlocks()),
                    SFCParallel(branches=[[CodeComment(text="(* c *)"), SFCTransition(name="BadTr", condition=True)]]),
                )
            ]
        )
    ]
    assert "SL-V024" in {d.code.value for d in validate_basepicture(par)}


def test_builtin_out_arg_beyond_call_args_not_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("A", "time")]
    bp.modulecodes = [ModuleCode(equations=[_equation(FuncCallStmt(FuncCall(name="CopyTime", args=(VarRef("A"),))))])]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert codes == {"SL-V013"}


def test_unknown_datatype_name_flagged_and_groupdata_exempt():
    bp = _base_picture()
    bp.localvariables = [_var("Part", "Zzzyx"), _var("Conn", "GroupData")]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V020" in codes
    assert "SL-V018" not in codes


def test_modulecode_without_sequences_or_equations_is_clean():
    bp = _base_picture()
    bp.modulecodes = [ModuleCode(sequences=None, equations=None)]
    assert validate_basepicture(bp) == ()
    empty = _base_picture()
    assert validate_basepicture(empty) == ()


def test_moduletype_and_nested_module_walks():
    child_type = SingleModule(
        header=_module_header("Child"),
        moduledef=None,
        localvariables=[_var("Local", "integer")],
        modulecodes=[ModuleCode(equations=[_equation(Assignment(VarRef("Local"), 1))])],
    )
    moduletype = ModuleTypeDef(
        name="T",
        moduleparameters=[_var("P", "integer")],
        localvariables=[_var("L", "integer")],
        submodules=[ModuleTypeInstance(header=_module_header("Inst"), moduletype_name="T")],
        modulecodes=[ModuleCode(equations=[_equation(Assignment(VarRef("P"), 0))])],
    )
    frame = FrameModule(
        header=_module_header("Frame"),
        submodules=[child_type],
        modulecodes=[ModuleCode(equations=[_equation(Assignment(VarRef("P", span=None), 0, span=None))])],
    )
    bp = _base_picture()
    bp.localvariables = [_var("P", "integer")]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [frame]
    diagnostics = validate_basepicture(bp)
    assert diagnostics == ()


def _transfer(
    target: str, source: str | None, *, global_: bool = False, source_type: str = "value"
) -> ParameterMapping:
    return ParameterMapping(
        target=VarRef(target),
        source_type=source_type,
        is_duration=False,
        is_source_global=global_,
        source=VarRef(source) if source else None,
    )


def test_param_transfer_type_mismatch_flagged():
    moduletype = ModuleTypeDef(
        name="ChildType",
        moduleparameters=[_var("EnableFlag", "boolean")],
        modulecodes=[ModuleCode(equations=[_equation(Assignment(VarRef("EnableFlag"), False))])],
    )
    bp = _base_picture()
    bp.localvariables = [_var("CounterValue", "integer")]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Child"),
            moduletype_name="ChildType",
            parametermappings=[_transfer("EnableFlag", "CounterValue")],
        )
    ]
    diagnostics = validate_basepicture(bp)
    assert [d.code.value for d in diagnostics] == ["SL-V027"]
    assert "EnableFlag" in diagnostics[0].message and "CounterValue" in diagnostics[0].message


def test_param_transfer_record_vs_builtin_mismatch_flagged():
    moduletype = ModuleTypeDef(name="RecType", moduleparameters=[_var("Payload", "Rec")])
    bp = _base_picture()
    bp.datatype_defs = [DataType(name="Rec", description=None, datecode=None)]
    bp.localvariables = [_var("CounterValue", "integer")]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Child"),
            moduletype_name="RecType",
            parametermappings=[_transfer("Payload", "CounterValue")],
        )
    ]
    diagnostics = validate_basepicture(bp)
    assert [d.code.value for d in diagnostics] == ["SL-V027"]


def test_param_transfer_same_record_and_anytype_clean():
    moduletype = ModuleTypeDef(
        name="MixedType",
        moduleparameters=[_var("Payload", "Rec"), _var("Any", "AnyType")],
    )
    bp = _base_picture()
    bp.datatype_defs = [
        DataType(name="Rec", description=None, datecode=None),
        DataType(name="AnyType", description=None, datecode=None),
    ]
    bp.localvariables = [_var("RecValue", "Rec")]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Child"),
            moduletype_name="MixedType",
            parametermappings=[
                _transfer("Payload", "RecValue"),  # record == record, names match
                _transfer("Any", "RecValue"),  # AnyType formal accepts anything
            ],
        )
    ]
    diagnostics = validate_basepicture(bp)
    assert diagnostics == ()


def test_param_transfer_compatibilities_clean():
    moduletype = ModuleTypeDef(
        name="MixType",
        moduleparameters=[
            _var("Speed", "real"),
            _var("Running", "boolean"),
            _var("Count", "integer"),
            _var("Gain", "real"),
            _var("SharedBias", "real"),
            _var("Ghost", "real"),  # declared but only used for skip-path mappings
        ],
    )
    bp = _base_picture()
    bp.localvariables = [
        _var("SpeedRef", "real"),
        _var("RunFlag", "boolean"),
        _var("Counter", "integer"),
    ]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Mix"),
            moduletype_name="MixType",
            parametermappings=[
                _transfer("Speed", "SpeedRef"),  # real => real
                _transfer("Running", "RunFlag"),  # boolean => boolean
                _transfer("Count", "Counter"),  # integer => integer
                _transfer("Gain", "Counter"),  # integer => real: numeric widening
                _transfer("SharedBias", None, global_=True),  # GLOBAL source: unresolved
                _transfer("Ghost", "MissingVar"),  # source variable not declared: skip
                _transfer("AbsentParam", "SpeedRef"),  # unknown target param: skip
            ],
        )
    ]
    diagnostics = validate_basepicture(bp)
    assert diagnostics == ()


def test_diagnostic_model_defaults():
    diag = Diagnostic(code=DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS, message="m")
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.span is None
    assert diag.code.value == "SL-V016"
    assert isinstance(DiagnosticCode.DUPLICATE_VARIABLE_NAME, DiagnosticCode)


def _typed_bp(variables: list[Variable], *items: object, datatypes: list[DataType] | None = None) -> BasePicture:
    """A base picture whose single equation holds ``items``, for typing tests."""
    bp = _base_picture()
    bp.localvariables = variables
    if datatypes is not None:
        bp.datatype_defs = datatypes
    bp.modulecodes = [ModuleCode(equations=[_equation(*items)])]
    return bp


def test_operand_rule_skips_call_results_and_record_fields():
    """Unproven operand types must stay silent: builtin returns and record fields."""
    bp = _typed_bp(
        [_var("Rate", "real"), _var("Running", "boolean"), _var("Rec", "Rec")],
        Assignment(VarRef("Running"), Compare(FuncCall("Test", []), "==", VarRef("Rate"))),
        datatypes=[DataType(name="Rec", description=None, datecode=None, var_list=[_var("Speed", "real")])],
    )
    assert [d.code.value for d in validate_basepicture(bp) if d.code.value.startswith("SL-V02")] == []


def test_operand_rule_allows_temporal_against_numeric_literal_only():
    """Proved 2026-10-05 by six probes, and the rule is narrower than "temporal ok".

    ACCEPTED: ``Elapsed == 5``, ``Elapsed > 2.5``, ``Stamp == 5`` - a duration or
    time compared against an integer/real LITERAL (EdgeDurCmpInt/Real,
    EdgeTimeCmpInt).
    REJECTED with this same code: ``ZeroDur == ZeroFull``, ``NegFive == NegHour``,
    ``DurFull == DurBare`` - temporal against temporal (EdgeBareDurZero,
    EdgeNegDurVal, ValidDurAndTime).

    So a numeric operand may meet a temporal one; two temporal operands may not.
    """
    numeric_side = _typed_bp(
        [_var("Elapsed", "duration"), _var("Stamp", "time"), _var("Sink", "boolean")],
        Assignment(VarRef("Sink"), Compare(VarRef("Elapsed"), "==", 5)),
        Assignment(VarRef("Sink"), Compare(VarRef("Elapsed"), ">", 2.5)),
        Assignment(VarRef("Sink"), Compare(VarRef("Stamp"), "==", 5)),
    )
    assert [d.code.value for d in validate_basepicture(numeric_side)] == []

    temporal_side = _typed_bp(
        [_var("DurFull", "duration"), _var("Stamp", "time"), _var("Sink", "boolean")],
        Assignment(VarRef("Sink"), Compare(VarRef("DurFull"), "==", VarRef("DurFull"))),
        Assignment(VarRef("Sink"), Compare(VarRef("Stamp"), ">", VarRef("DurFull"))),
    )
    # Both operands of each comparison are temporal, and the rule reports once
    # per offending operand, so two comparisons yield four diagnostics.
    assert [d.code.value for d in validate_basepicture(temporal_side)] == ["SL-V028"] * 4


def test_operand_rule_still_flags_boolean_operands():
    boolean = _typed_bp(
        [_var("Run", "boolean"), _var("Sink", "boolean")],
        Assignment(VarRef("Sink"), Compare(VarRef("Run"), "==", VarRef("Run"))),
    )
    assert [d.code.value for d in validate_basepicture(boolean)] == ["SL-V028", "SL-V028"]


def test_assignment_rule_allows_numeric_widening_and_same_family():
    """integer into real and same-family assignment are probed-accept, so silent."""
    bp = _typed_bp(
        [
            _var("Count", "integer"),
            _var("Rate", "real"),
            _var("Flag1", "boolean"),
            _var("Flag2", "boolean"),
            _var("Label", "identstring"),
            _var("Tag", "tagstring"),
        ],
        Assignment(VarRef("Rate"), VarRef("Count")),
        Assignment(VarRef("Count"), VarRef("Count")),
        Assignment(VarRef("Flag2"), VarRef("Flag1")),
        Assignment(VarRef("Tag"), VarRef("Label")),
        Assignment(VarRef("Rate"), 1.5),
    )
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_assignment_rule_skips_unresolved_target_and_unknown_source():
    """Neither a missing variable nor an unprovable source type is a mismatch."""
    bp = _typed_bp(
        [_var("Count", "integer")],
        Assignment(VarRef("Ghost"), VarRef("Count")),
        Assignment(VarRef("Count"), FuncCall("Untyped", [])),
    )
    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V019"]


def test_condition_rule_flags_non_boolean_and_allows_boolean():
    bp = _typed_bp(
        [_var("Count", "integer"), _var("Rate", "real"), _var("Flag1", "boolean"), _var("Flag2", "boolean")],
        IfStmt(
            branches=(
                (VarRef("Count"), (Assignment(VarRef("Flag1"), True),)),
                (Compare(VarRef("Count"), ">", 0), (Assignment(VarRef("Flag2"), False),)),
            ),
            else_block=None,
        ),
    )
    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V030"]


def test_condition_rule_skips_call_result_condition():
    bp = _typed_bp(
        [_var("Rate", "real"), _var("Flag1", "boolean")],
        IfStmt(branches=((FuncCall("Untyped", []), (Assignment(VarRef("Flag1"), True),)),), else_block=None),
    )
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_ternary_condition_is_checked_and_branch_types_must_agree():
    """An inline IF expression is condition-checked; mixed branch types are unproven."""
    bp = _typed_bp(
        [_var("Count", "integer"), _var("Rate", "real"), _var("Flag1", "boolean")],
        Assignment(
            VarRef("Flag1"), TernaryOp(branches=((VarRef("Count"), VarRef("Count")),), else_expr=VarRef("Rate"))
        ),
    )
    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V030"]


def test_ternary_with_agreeing_branches_infers_type():
    ternary = TernaryOp(branches=((True, VarRef("Count")),), else_expr=VarRef("Count"))
    assert infer_expr_type(ternary, build_scope(None, [_var("Count", "integer")]), {}) == "integer"


def test_datatype_family_helpers():
    assert datatype_family("integer") is TypeFamily.NUMERIC
    assert datatype_family("real") is TypeFamily.NUMERIC
    assert datatype_family("boolean") is TypeFamily.BOOLEAN
    assert datatype_family("duration") is TypeFamily.TEMPORAL
    assert datatype_family("time") is TypeFamily.TEMPORAL
    assert datatype_family("identstring") is TypeFamily.STRING
    assert datatype_family("MyRecord") is None
    assert is_numeric("real") and not is_numeric("boolean")
    assert is_boolean("boolean") and not is_boolean("integer")
    assert family_of(None) is None
    assert operand_types(Compare(True, "==", 1), build_scope(None, []), {}) == ("boolean", "integer")


def test_string_literal_expression_infers_string():
    assert infer_expr_type("text", build_scope(None, []), {}) == "string"


def test_ternary_with_unknown_branch_type_is_unproven():
    """A branch whose type cannot be proved makes the whole ternary unknown."""
    ternary = TernaryOp(branches=((True, VarRef("Count")),), else_expr=VarRef("Rec"))
    assert infer_expr_type(ternary, build_scope(None, [_var("Count", "integer"), _var("Rec", "Rec")]), {}) is None


def test_assignment_between_custom_types_is_left_permissive():
    """Record identity is not part of any probed rule, so same-name records pass."""
    assert assignment_is_compatible("Rec", "Rec") is True
    assert assignment_is_compatible("Rec", "integer") is True
    assert assignment_is_compatible("integer", "Rec") is True
    assert assignment_is_compatible("boolean", "integer") is False
    assert assignment_is_compatible("integer", "boolean") is False
    assert assignment_is_compatible("duration", "time") is True
    assert assignment_is_compatible("time", "duration") is True
    assert assignment_is_compatible("integer", "real") is True


def test_attribute_combination_rejects_opsave_followed_by_state_or_const():
    """ORDER-SENSITIVE, corrected 2026-10-05 by OpSaveStateReversed.x.

    `OpSave State` is rejected (EdgeOpSaveAndState.x) but `State OpSave`
    COMPILES, so the earlier belief that the pair was invalid "in either order"
    was wrong. `OpSave Const` is rejected (OpSaveConst.x).
    """
    opsave_state = Variable(
        name="SavedStateVar", datatype="integer", opsave=True, state=True, attribute_order=("opsave", "state")
    )
    opsave_const = Variable(
        name="Mixed", datatype="integer", opsave=True, const=True, attribute_order=("opsave", "const")
    )
    for variable in (opsave_state, opsave_const):
        codes = [d.code.value for d in validate_basepicture(_typed_bp([variable]))]
        assert "SL-V031" in codes, f"{variable.name}: {codes}"


def test_attribute_combination_allows_state_before_opsave():
    """OpSaveStateReversed.x compiles, so reversed order must stay clean."""
    reversed_order = Variable(
        name="Mixed", datatype="integer", state=True, opsave=True, attribute_order=("state", "opsave")
    )
    assert [d.code.value for d in validate_basepicture(_typed_bp([reversed_order]))] == []


def test_attribute_combination_is_silent_without_declared_order():
    """No recorded order means no evidence of sequence, so stay silent."""
    unknown_order = Variable(name="SavedStateVar", datatype="integer", opsave=True, state=True)
    assert [d.code.value for d in validate_basepicture(_typed_bp([unknown_order]))] == []


def test_attribute_combination_leaves_single_modifiers_clean():
    """Opsave alone and State alone are both editor-accepted controls."""
    saved = Variable(name="SavedOnly", datatype="integer", opsave=True, attribute_order=("opsave",))
    live = Variable(name="LiveOnly", datatype="integer", state=True, attribute_order=("state",))
    guarded = Variable(name="ConstOnly", datatype="integer", const=True, attribute_order=("const",))
    codes = [d.code.value for d in validate_basepicture(_typed_bp([saved, live, guarded]))]
    assert codes == []


def test_coordinate_tail_type_rule_scopes_to_computed_expressions():
    """A real-typed tail passes and an integer-typed tail is reported (SL-V032)."""
    integer_tail = BinOp(left=VarRef("Source"), op="+", right=1)
    real_tail = BinOp(left=VarRef("Source"), op="+", right=1.0)
    module_def = ModuleDef(clipping_bounds=((-1.0, -1.0), (1.0, 1.0)), clipping_tails=[integer_tail])
    bp = _base_picture()
    bp.localvariables = [_var("Source", "integer")]
    bp.moduledefs = [module_def]
    assert "SL-V032" in [d.code.value for d in validate_basepicture(bp)]

    module_def.clipping_tails = [real_tail]
    bp.localvariables = [_var("Source", "real")]
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_coordinate_tail_rule_covers_bare_variable_tails():
    """A coordinate position is never an integer, computed or bare."""
    module_def = ModuleDef(clipping_bounds=((-1.0, -1.0), (1.0, 1.0)), clipping_tails=[VarRef("Source")])
    bp = _base_picture()
    bp.localvariables = [_var("Source", "integer")]
    bp.moduledefs = [module_def]
    assert "SL-V032" in [d.code.value for d in validate_basepicture(bp)]

    bp.localvariables = [_var("Source", "real")]
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_coordinate_tail_rule_skips_reference_names():
    """An InVar_ "Name" tail is a reference, not a value, so it stays silent."""
    module_def = ModuleDef(clipping_bounds=((-1.0, -1.0), (1.0, 1.0)), clipping_tails=["ClipX"])
    bp = _base_picture()
    bp.moduledefs = [module_def]
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_sequence_ends_with_step_skips_open_sequences():
    """A closed SEQUENCE must close on a transition; OPENSEQUENCE may end on a step."""
    for seq_type, expected in (
        (const.GRAMMAR_VALUE_SEQUENCE, ["SL-V033"]),
        (const.GRAMMAR_VALUE_OPENSEQUENCE, []),
    ):
        picture = _base_picture()
        picture.modulecodes = [
            ModuleCode(
                sequences=[
                    Sequence(
                        name="Seq",
                        type=seq_type,
                        position=(0.0, 0.0),
                        size=(1.0, 1.0),
                        code=[
                            SFCStep(kind="step", name="Last", code=SFCCodeBlocks()),
                            CodeComment(text="a trailing comment is not the last element"),
                        ],
                    )
                ]
            )
        ]
        assert [d.code.value for d in validate_basepicture(picture)] == expected, seq_type


def test_trailing_enddef_requires_a_semicolon():
    """A trailing module-level ENDDEF is optional, but its `;` is mandatory.

    The real tool rejects `... ModuleDef ... ENDDEF` (no `;`) with
    `Error on line 15: >>><<< SemicolonSym Expected`, while ENDDEF absent
    entirely is fine. Only `base_picture_module` is tightened: RECORD ENDDEFs and
    ScanGroup ENDDEFs keep their optional `;` (UnCompressedFullGrammar.s uses both
    and the real tool compiles it cleanly).
    """
    header = (
        '"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-08-19-12:00:00.000, name: TrailingEnddefSemicolon"\n'
    )
    good = header + (
        "BasePicture Invocation\n"
        "   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
        "    ) : MODULEDEFINITION DateCode_ 1\n\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    )
    # no trailing ENDDEF at all -> accepted
    assert parser_core_parse_source_text(good) is not None
    # trailing ENDDEF with its `;` -> accepted
    assert parser_core_parse_source_text(good + "ENDDEF;\n") is not None
    # trailing ENDDEF without `;` -> rejected
    with pytest.raises(UnexpectedInput):
        parser_core_parse_source_text(good + "ENDDEF\n")


def test_reserved_runtime_names_cannot_be_declared():
    """SL-V034: `On`/`Off` are readable but never declarable.

    The real parser rejects `On: boolean := False;` with `>>>On<<< AliasSym
    Expected`. Reads stay exempt from SL-V019, so the same names must still be
    usable in expressions - only the declaration is illegal.
    """
    reserved = SFC_RUNTIME_CONSTANTS
    assert reserved == {"on", "off"}, "reserved set changed - re-check the probes"

    header = (
        '"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-08-19-12:00:00.000, name: ReservedName"\n'
    )
    picture = "BasePicture Invocation\n   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n    ) : MODULEDEFINITION DateCode_ 1\n\n"
    tail = (
        "\nModuleDef\nClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK E COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
        "      Flag = On;\n"
        "\nENDDEF (*BasePicture*);\n"
    )

    def codes(decls: str, typedefs: str = "") -> list[str]:
        # TYPEDEFINITIONS precedes LOCALVARIABLES in a SattLine module body.
        src = header + picture + typedefs + "LOCALVARIABLES\n" + decls + tail
        return [d.code.value for d in parse_and_validate(src)[1]]

    # declaring either reserved name is rejected
    assert "SL-V034" in codes("   On: boolean := False;\n   Flag: boolean := False;\n")
    assert "SL-V034" in codes("   Off: boolean := False;\n   Flag: boolean := False;\n")
    # a record field counts as a variable declaration
    assert "SL-V034" in codes(
        "   Flag: boolean := False;\n",
        typedefs="TYPEDEFINITIONS\n   Rec = RECORD DateCode_ 2\n      On: boolean;\n   ENDDEF\n",
    )
    # ...and so does a datatype name
    assert "SL-V034" in codes(
        "   Flag: boolean := False;\n",
        typedefs="TYPEDEFINITIONS\n   Off = RECORD DateCode_ 2\n      F: boolean;\n   ENDDEF\n",
    )
    # GroupData stays legal: it is a reserved *type*, not a runtime constant
    assert "SL-V034" not in codes("   GroupData: boolean := False;\n   Flag: boolean := False;\n")
    # reading a reserved name is still fine - SL-V019 must not fire
    assert "SL-V019" not in codes("   Flag: boolean := False;\n")


def test_identifier_folding_uses_the_cp1252_byte_table():
    from sattline_parser.validation.names import fold_identifier, identifiers_equal  # noqa: PLC0415

    # ASCII folds to upper case
    assert fold_identifier("count") == "COUNT"
    assert identifiers_equal("Count", "COUNT")
    # CP1252 high bytes fold through the table, one byte at a time
    assert fold_identifier("é") == "É"
    assert identifiers_equal("Straße", "STRAßE")
    assert identifiers_equal("Œuvre", "œuvre")
    assert fold_identifier("ÿ") == "Ÿ"
    # ...but full Unicode case folding is NOT applied
    assert not identifiers_equal("Straße", "STRASSE")  # casefold would equate these
    assert not identifiers_equal("ﬁle", "FILE")  # ligature is not a case pair
    assert not identifiers_equal("µ", "\u039c")  # micro sign vs Greek mu


def test_identifier_identity_rejects_a_unicode_casefold_match():
    header = (
        '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-26-12:00:00.000, name: NameIdentity"\n'
    )
    picture = (
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   Straße: integer := 0;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK E COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
    )
    tail = "\nENDDEF (*BasePicture*);\n"

    def codes(reference: str) -> set[str]:
        source = header + picture + f"      Straße = {reference};\n" + tail
        return {diagnostic.code.value for diagnostic in parse_and_validate(source)[1]}

    # same spelling and byte-case variants resolve
    assert codes("Straße") == set()
    assert codes("STRAßE") == set()
    # a full-Unicode casefold match must NOT resolve
    assert "SL-V019" in codes("STRASSE")


def test_old_state_is_not_a_write_target():
    header = (
        '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-26-12:00:00.000, name: OldStateWrite"\n'
    )
    picture = (
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   Counter: integer State := 0;\n"
        "   Mirror: integer := 0;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK E COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
    )
    tail = "\nENDDEF (*BasePicture*);\n"

    def codes(statement: str) -> set[str]:
        source = header + picture + f"      {statement}\n" + tail
        return {diagnostic.code.value for diagnostic in parse_and_validate(source)[1]}

    assert "SL-V035" in codes("Counter:Old = Mirror;")
    assert "SL-V035" in codes("CopyVariable(Mirror, Counter:Old, Mirror);")
    # reads and New writes stay legal
    assert "SL-V035" not in codes("Mirror = Counter:Old;")
    assert "SL-V035" not in codes("Counter:New = Mirror;")
    # a suffix on a non-State variable is the older SL-V005 finding, not SL-V035
    assert codes("Mirror:Old = 1;") == {"SL-V005"}


def test_datecode_normalisation_and_generation():
    from sattline_parser.validation.datecode import (  # noqa: PLC0415
        compute_datecode,
        normalized_datecode,
    )

    # declared stamps: non-negative values reduce modulo 2 000 000 000
    assert normalized_datecode(0) == 0
    assert normalized_datecode(123456) == 123456
    assert normalized_datecode(2_000_000_007) == 7
    # a negative literal is refused rather than given Python's modulo sign
    with pytest.raises(ValueError, match="negative"):
        normalized_datecode(-1)
    # generated stamps follow the clock formula
    assert compute_datecode(123, 1000) == 2400
    assert compute_datecode(123, 0) == 0


def test_on_off_runtime_constants_are_boolean_expressions():
    header = (
        '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-26-12:00:00.000, name: OnOffTyping"\n'
    )
    picture = (
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   Flag: boolean := False;\n"
        "   Num: integer := 0;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK E COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
    )
    tail = "\nENDDEF (*BasePicture*);\n"

    def codes(statement: str) -> set[str]:
        return {
            diagnostic.code.value
            for diagnostic in parse_and_validate(header + picture + f"      {statement}\n" + tail)[1]
        }

    # On/Off are boolean primaries, so these are ordinary assignments
    assert codes("Flag = On;") == set()
    assert codes("Flag = Off;") == set()
    assert "SL-V029" in codes("Num = On;")
    # ...and numeric comparison against them is rejected (error 0x17)
    assert "SL-V028" in codes("Flag = Num > Off;")
