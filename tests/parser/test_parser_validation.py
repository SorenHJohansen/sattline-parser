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
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.builtins import (
    BUILTIN_DATATYPE_NAMES,
    builtin_datatype_typo,
    builtin_function_signature,
    is_builtin_function,
)
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode, DiagnosticSeverity
from sattline_parser.validation.literals import is_valid_duration, is_valid_time
from sattline_parser.validation.symbols import build_scope, resolve_var

from ._parser_core_test_support import *

_INVALID_VALIDATION_FIXTURES: dict[str, str] = {
    "DuplicateDatatypeName": "SL-V001",
    "DuplicateModuletypeName": "SL-V002",
    "DuplicateVariableNames": "SL-V003",
    "DuplicateSiblingSubmodules": "SL-V004",
    "OldNewOnNonState": "SL-V005",
    "OldNewOnNonStateRecordField": "SL-V006",
    "WriteToConstVariable": "SL-V007",
    "InitValueTypeMismatch": "SL-V008",
    "BadBareDurationString": "SL-V009",
    "BadBareTimeString": "SL-V010",
    "BadDurationLiteral": "SL-V011",
    "BadTimeLiteral": "SL-V012",
    "BuiltinWrongArity": "SL-V013",
    "BuiltinOutArgNotVariable": "SL-V014",
    "StringLiteralInCallArgument": "SL-V015",
    "ConsecutiveSeqSteps": "SL-V016",
    "SeqForkUnknownTarget": "SL-V017",
    "BuiltinDatatypeTypo": "SL-V018",
    "UndefinedVariableRef": "SL-V019",
    "UnknownDatatypeName": "SL-V020",
    "DuplicateSFCElementNames": "SL-V021",
    "SFCInitStepNotFirst": "SL-V022",
    "SFCInitStepRepeated": "SL-V022",
    "SFCAlternativeBranchStartsWithStep": "SL-V023",
    "SFCParallelBranchStartsWithTransition": "SL-V024",
    "ConstVarAsBuiltinOutArg": "SL-V007",
    "DuplicateRecordFieldName": "SL-V025",
    "DatatypeShadowsBuiltinName": "SL-V026",
    "CrossModuleContractMismatch": "SL-V027",
}

_PARSE_REJECTED_FIXTURES = [
    "EncodingStress",
    "FreestandingCommentInModuleCode",
    "GraphObjectsDoubleLayer",
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


def test_duplicate_variable_names_in_scope_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("Counter", "integer"), _var("counter", "integer")]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V003" in codes


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


def test_init_value_type_mismatch_flagged_for_scalars():
    bp = _base_picture()
    bp.localvariables = [
        _var("BadInt", "integer", init_value="not a number"),
        _var("BadReal", "real", init_value=True),
        _var("BadBool", "boolean", init_value="yes"),
        _var("BadFloatInt", "integer", init_value=1.5),
    ]
    diagnostics = validate_basepicture(bp)
    assert sum(1 for d in diagnostics if d.code.value == "SL-V008") == 4


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


def test_bare_duration_and_time_init_flagged():
    bp = _base_picture()
    bp.localvariables = [
        _var("D1", "duration", init_value="5xyz"),
        _var("D2", "duration", init_value=7),
        _var("D3", "duration", init_value={"Time_Value": "30s"}),
        _var("T1", "time", init_value="2026/04/23 12:00:00"),
        _var("T2", "time", init_value=0),
    ]
    diagnostics = validate_basepicture(bp)
    assert sum(1 for d in diagnostics if d.code.value in ("SL-V009", "SL-V010")) == 5


def test_keyworded_duration_and_time_init_checks():
    valid = _base_picture()
    valid.localvariables = [
        _var("D", "duration", init_is_duration=True, init_value="30s"),
    ]
    time_valid = _base_picture()
    time_valid.localvariables = [_var("T", "time", init_value={"Time_Value": "2026-01-01-00:00:00.000"})]
    assert validate_basepicture(valid) == ()
    assert validate_basepicture(time_valid) == ()

    bad = _base_picture()
    bad.localvariables = [
        _var("D", "duration", init_is_duration=True, init_value="not-a-duration"),
        _var("T", "time", init_value={"Time_Value": None}),
        _var("T2", "time", init_value={"Time_Value": "bad"}),
    ]
    codes = {d.code.value for d in validate_basepicture(bad)}
    assert "SL-V011" in codes
    assert "SL-V010" in codes
    assert "SL-V012" in codes


def test_datatype_typo_flagged_and_declared_records_exempt():
    bp = _base_picture()
    record = DataType(name="SensorType", description=None, datecode=1, var_list=[_var("Raw", "real")])
    bp.datatype_defs = [record]
    bp.localvariables = [_var("Counter", "intege"), _var("Sensor", "SensorType"), _var("Other", "duration")]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V018" in codes


def test_duplicate_definition_names_flagged():
    first = DataType(name="SensorType", description=None, datecode=1, var_list=[])
    second = DataType(name="SensorType", description=None, datecode=2, var_list=[])
    mt_first = ModuleTypeDef(name="Controller", datecode=1)
    mt_second = ModuleTypeDef(name="controller", datecode=2)
    bp = _base_picture()
    bp.datatype_defs = [first, second]
    bp.moduletype_defs = [mt_first, mt_second]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V001" in codes
    assert "SL-V002" in codes


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
    known = SFCTransition(name="TrGo", condition=True)
    fork_unknown = SFCFork(targets=("Nope",))
    fork_known = SFCFork(targets=("TrGo",))

    bad = _base_picture()
    bad.modulecodes = [ModuleCode(sequences=[_sequence(known, fork_unknown)])]
    codes = {d.code.value for d in validate_basepicture(bad)}
    assert "SL-V017" in codes

    good = _base_picture()
    good.modulecodes = [ModuleCode(sequences=[_sequence(known, fork_known)])]
    assert validate_basepicture(good) == ()


def test_sfc_walk_covers_all_body_item_kinds():
    bp = _base_picture()
    bp.localvariables = [_var("V", "integer", init_value=0)]
    step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks(enter=[Assignment(VarRef("V"), 1)], exit=[]))
    transition = SFCTransition(name="TrMatch", condition=Compare(VarRef("V"), ">", 0))
    transition_sub = SFCTransitionSub(name="TSub", body=[SFCStep(kind="step", name="SubStep", code=SFCCodeBlocks())])
    alterni = SFCAlternative(branches=[[SFCTransition(name="TrAlt", condition=True)]])
    parallel = SFCParallel(
        branches=[
            [
                SFCStep(kind="step", name="ParStep", code=SFCCodeBlocks()),
                SFCTransition(name="TrPar", condition=True),
            ]
        ]
    )
    subsequence = SFCSubsequence(name="SubSeq", body=[SFCTransition(name="TrInner", condition=True)])
    break_node = SFCBreak()
    comment = CodeComment(text="(* hi *)")
    bp.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    step,
                    transition,
                    transition_sub,
                    alterni,
                    parallel,
                    subsequence,
                    break_node,
                    comment,
                    SFCFork(targets=("TrMatch", "TSub", "TrAlt", "SubStep", "ParStep", "TrPar", "TrInner")),
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
        SFCTransitionSub(name="TSub", body=[]),
    ]
    alt_transition = SFCTransition(name="TrAlt", condition=True)
    branch = SFCAlternative(branches=[[alt_transition, SFCStep(kind="step", name="Nested", code=SFCCodeBlocks())]])
    bp.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    init_step,
                    *transitions[:1],
                    run_step,
                    *transitions[1:],
                    branch,
                    SFCFork(targets=("Run", "T1", "TSub", "TrAlt", "Nested")),
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


def test_sfc_init_step_placement_flagged():
    repeated = _base_picture()
    repeated.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    SFCStep(kind="init", name="First", code=SFCCodeBlocks()),
                    SFCTransition(name="TrA", condition=True),
                    SFCStep(kind="init", name="Second", code=SFCCodeBlocks()),
                )
            ]
        )
    ]
    not_first = _base_picture()
    not_first.modulecodes = [
        ModuleCode(
            sequences=[
                _sequence(
                    SFCStep(kind="step", name="StepA", code=SFCCodeBlocks()),
                    SFCTransition(name="TrA", condition=True),
                    SFCStep(kind="init", name="Late", code=SFCCodeBlocks()),
                )
            ]
        )
    ]
    assert "SL-V022" in {d.code.value for d in validate_basepicture(repeated)}
    assert "SL-V022" in {d.code.value for d in validate_basepicture(not_first)}


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


def test_datatype_shadows_builtin_name_flagged():
    bp = _base_picture()
    bp.datatype_defs = [DataType(name="Integer", description=None, datecode=1, var_list=[])]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V026" in codes


def test_duplicate_record_field_name_flagged():
    record = DataType(
        name="Pair",
        description=None,
        datecode=1,
        var_list=[_var("Left", "real"), _var("left", "boolean")],
    )
    bp = _base_picture()
    bp.datatype_defs = [record]
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V025" in codes


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
        modulecodes=[ModuleCode(equations=[_equation(Assignment(VarRef("EnableFlag"), 0))])],
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
