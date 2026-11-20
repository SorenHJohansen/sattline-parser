# pyright: reportArgumentType=false, reportPrivateUsage=false, reportUnknownArgumentType=false
"""Tests for the strict single-source validation pass.

Wires the ``tests/fixtures/corpus/invalid`` fixtures that parse successfully to
their expected diagnostic codes, asserts the consumer-layer boundary for
cross-module contract mismatches, gates the whole valid/edge corpus against
false positives, and covers every branch of the validators with hand-built ASTs.
"""

import pathlib

import pytest
from lark.exceptions import UnexpectedInput

from sattline_parser import parse_and_validate
from sattline_parser import parse_source_text as parser_core_parse_source_text
from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    BasePicture,
    CodeComment,
    DataType,
    Equation,
    FrameModule,
    GraphObject,
    InteractObject,
    MappingSource,
    ModuleCode,
    ModuleDef,
    ModuleHeader,
    ModuleTypeDef,
    ModuleTypeInstance,
    ParameterMapping,
    ScalarDatatype,
    Sequence,
    SFCAlternative,
    SFCCodeBlocks,
    SFCFork,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
    SingleModule,
    SourceSpan,
    Variable,
)
from sattline_parser.models.clauses import (
    AssignClause,
    ClippingClause,
    ColourSpec,
    EnableClause,
    ModuleArguments,
    ModuleInViewClause,
    PolygonPoint,
    TailedClause,
)
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    NotOp,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.models.tails import LitStringTail, VarTail
from sattline_parser.names import fold_identifier
from sattline_parser.preprocessing.compressed import PreprocessError
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.builtins import (
    BUILTIN_DATATYPE_NAMES,
    builtin_datatype_typo,
    builtin_function_signature,
)
from sattline_parser.validation.diagnostics import (
    Diagnostic,
    DiagnosticCode,
)
from sattline_parser.validation.rules import RETIRED_CODES
from sattline_parser.validation.symbols import build_scope, lookup_datatype, resolve_var
from sattline_parser.validation.typing import (
    TypeFamily,
    datatype_family,
    family_of,
    infer_expr_type,
    is_boolean,
    is_numeric,
    operand_types,
)

from ._parser_core_test_support import _module_header, _repo_path

#: Fixtures for rules the real parser ENFORCES.
_INVALID_VALIDATION_FIXTURES: dict[str, str] = {
    "OpSaveAndStateCombined": "SL-V031",
    "CoordinateInvarTail": "SL-V032",
    "SequenceParallel": "SL-V033",
    "SubSequenceDefinition": "SL-V033",
    "TerminalSeqStep": "SL-V033",
    "DuplicateSiblingSubmodules": "SL-V004",
    "DuplicateSiblingCrossType": "SL-V004",
    "DuplicateSiblingFrameModules": "SL-V004",
    "DuplicateSiblingFrameAndModule": "SL-V004",
    "EmptyRecordFieldAccess": "SL-V019",
    "FrameModuleParameterMappings": "SL-V027",
    "OldOnMappingSource": "SL-V005",
    "ProcedureAsValue": "SL-V060",
    "OldNewOnNonState": "SL-V005",
    "OldNewOnNonStateRecordField": "SL-V006",
    "WriteToConstVariable": "SL-V007",
    "BuiltinWrongArity": "SL-V013",
    "BuiltinOutArgNotVariable": "SL-V014",
    "StringLiteralInCallArgument": "SL-V015",
    "ConsecutiveSeqSteps": "SL-V016",
    "SeqForkUnknownTarget": "SL-V017",
    "BuiltinDatatypeTypo": "SL-V018",
    "AmbiguousDatatypeTypo": "SL-V020",
    "DirectStringAssignment": "SL-V045",
    "StaleMappingTarget": "SL-V048",
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
    "IdentifierTooLong": "SL-V038",
    "AssignmentFamilyMismatch": "SL-V029",
    "IfConditionNotBoolean": "SL-V030",
    "EnableTailNotBoolean": "SL-V030",
    "TransitionConditionNotBoolean": "SL-V030",
}

#: Fixtures for rules the real parser does NOT enforce. Kept as files so the
#: retirement stays visible and re-testable: the code must emit nothing for
#: these, because the editor refuses to CREATE such a declaration but its
#: parser ACCEPTS the same source loaded from disk.
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
    "DeepExpressionChain",
    "ModuleDefNoTrailingEnddef",
    "EncodingStress",
    "FreestandingCommentInModuleCode",
    "GraphObjectsDoubleLayer",
    "GraphObjectsSectionLayer",
    "Malformed",
    "ModuleCodeWithoutModuleDef",
    "NotSattLine",
    "OversizedInput",
    "ReservedNameVarOff",
    "ReservedNameVarOn",
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


# The evidence for each pairing travels in the fixture's header comment, so CI
# has no dependency on any external probe tree. Every case asserts BOTH sides:
# relaxing one half of a rule without its counter-case fails here even though
# the generic valid-corpus loop and the _INVALID_VALIDATION_FIXTURES table
# would still pass.


def _codes(subdir: str, stem: str) -> set[str]:
    return {d.code.value for d in parse_and_validate(_raw(_corpus(f"{subdir}/{stem}.s")))[1]}


def test_temporal_comparison_keeps_both_sides():
    """A duration or time against a numeric literal is clean; two temporal
    operands are rejected by the same operand rule.

    The valid fixture ``TemporalVsNumericCompare.s`` and the invalid fixture
    ``TemporalVsTemporalCompare.s`` pin both sides.
    """
    assert _codes("valid", "TemporalVsNumericCompare") == set()
    assert _codes("invalid", "TemporalVsTemporalCompare") == {"SL-V028"}


def test_opsave_modifier_order_keeps_both_sides():
    """``State OpSave`` is accepted; ``OpSave State`` and ``OpSave Const`` are
    illegal attribute mixes. The valid fixture ``VariableModifiers.s`` and the
    invalid fixtures ``OpSaveAndStateCombined.s`` and ``OpSaveConstCombined.s``
    pin the three forms.
    """
    assert _codes("valid", "VariableModifiers") == set()
    assert _codes("invalid", "OpSaveAndStateCombined") == {"SL-V031"}
    assert _codes("invalid", "OpSaveConstCombined") == {"SL-V031"}


def test_enable_paren_tail_is_accepted_on_graph_and_interact_objects():
    """Graph objects and interactors take ``Enable_`` bare or with a paren tail.

    The valid fixtures ``GraphObjectEnableVariants.s`` and
    ``InteractEnableParenTail.s`` pin both object kinds.
    """
    assert _codes("valid", "GraphObjectEnableVariants") == set()
    assert _codes("valid", "InteractEnableParenTail") == set()


def test_internal_registrations_are_checked_like_documented_builtins():
    """Names bound for compiled programs get arity checks, not silence.

    ``Login`` is not a documented language built-in, but shipped library
    sources call it, so the catalogue carries its signature.
    """
    header = (
        '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-26-12:00:00.000, name: InternalBuiltinArity"\n'
    )
    picture = (
        "BasePicture Invocation\n"
        "   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
        "    ) : MODULEDEFINITION DateCode_ 1\n"
        "\n"
        "LOCALVARIABLES\n"
        '   User: string := "";\n'
        "   Status: integer := 0;\n"
        "\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
    )
    tail = "\nENDDEF (*BasePicture*);\n"

    def codes(statement: str) -> set[str]:
        source = header + picture + f"      {statement}\n" + tail
        return {diagnostic.code.value for diagnostic in parse_and_validate(source)[1]}

    assert codes("Login(User, Status);") == set()
    assert "SL-V013" in codes("Login(User);")
    assert "SL-V013" in codes("Login(User, Status, Status);")
    signature = builtin_function_signature("Login")
    assert signature is not None and signature.kind == "procedure"


def test_builtin_table_and_typo_helpers():
    assert builtin_function_signature("EqualStrings") is not None
    assert builtin_function_signature("NoSuchBuiltin") is None
    equal_strings = builtin_function_signature("EqualStrings")
    assert equal_strings is not None and equal_strings.min_args == 3 and equal_strings.max_args == 3
    copytime = builtin_function_signature("CopyTime")
    assert copytime is not None
    assert [(parameter.name, parameter.direction) for parameter in copytime.parameters] == [
        ("Source", "in var"),
        ("Destination", "out"),
    ]
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
    records = {fold_identifier("Point"): record}
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
    bp.modulecode = ModuleCode(equationblocks=[_equation(Assignment(VarRef("MaxLimit"), 1))])
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V007" in codes


def test_undefined_variable_references_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("Input", "integer"), _var("Mystery", "integer")]
    bp.modulecode = ModuleCode(
        equationblocks=[
            _equation(
                Assignment(VarRef("Input"), 0),
                Assignment(VarRef("Sub.Out"), 1, span=None),
                Assignment(VarRef("Mystery.x"), 1, span=None),
            )
        ]
    )
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
    bp.modulecode = ModuleCode(
        equationblocks=[
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
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V005" in codes
    assert "SL-V006" in codes


def test_old_new_on_state_symbols_not_flagged():
    record_type = DataType(name="CmdType", description=None, datecode=1, var_list=[_var("Flag", "boolean", state=True)])
    bp = _base_picture()
    bp.datatype_defs = [record_type]
    bp.localvariables = [_var("Counter", "integer", state=True), _var("CMD", "CmdType")]
    bp.modulecode = ModuleCode(
        equationblocks=[
            _equation(
                BoolOp("AND", (VarRef("Counter", state="old"), VarRef("CMD.Flag", state="new"))),
            )
        ]
    )
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
    repeated_init.modulecode = ModuleCode(
        sequences=[
            _sequence(
                SFCStep(kind="init", name="First", code=SFCCodeBlocks()),
                SFCTransition(name="TrA", condition=True),
                SFCStep(kind="init", name="Second", code=SFCCodeBlocks()),
                SFCTransition(name="TrB", condition=True),
            )
        ]
    )
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
    bp.modulecode = ModuleCode(equationblocks=[_equation(FuncCallStmt(unknown))])
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V015" in codes


def test_builtin_arity_and_out_arg_checks():
    bp = _base_picture()
    bp.localvariables = [_var("A", "string", init_value=""), _var("B", "string", init_value="")]
    fn_call = FuncCallStmt(FuncCall(name="EqualStrings", args=(VarRef("A"),)))
    copy_call = FuncCallStmt(FuncCall(name="CopyTime", args=(VarRef("A"), BoolOp("OR", (VarRef("A"), VarRef("B"))))))
    ok_call = FuncCallStmt(FuncCall(name="EqualStrings", args=(VarRef("A"), VarRef("B"), True)))
    unknown = FuncCallStmt(FuncCall(name="UserProc", args=(1, 2, 3, 4)))
    bp.modulecode = ModuleCode(equationblocks=[_equation(fn_call, copy_call, ok_call, unknown)])
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V013" in codes
    assert "SL-V014" in codes
    assert codes == {"SL-V013", "SL-V014", "SL-V043", "SL-V047"}


def test_builtin_optional_trailing_arguments_are_accepted():
    bp = _base_picture()
    bp.localvariables = [
        _var("File1", "textfile"),
        _var("Text", "string", init_value=""),
        _var("Async", "integer", init_value=0),
    ]
    call = FuncCallStmt(FuncCall(name="writeline", args=(VarRef("File1"), VarRef("Text"), VarRef("Async"))))
    bp.modulecode = ModuleCode(equationblocks=[_equation(call)])
    assert validate_basepicture(bp, allow_unresolved_external_datatypes=True) == ()


def test_builtin_missing_required_argument_is_still_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("File1", "textfile")]
    call = FuncCallStmt(FuncCall(name="writeline", args=(VarRef("File1"),)))
    bp.modulecode = ModuleCode(equationblocks=[_equation(call)])
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V013" in codes


def test_string_cursor_parameter_accepts_a_const_string_but_checks_the_rest():
    """``accepts_const_string`` exempts the Const write, not the argument rules."""
    bp = _base_picture()
    bp.localvariables = [
        _var("Template", "string", const=True, init_value="Template"),
        _var("Cursor", "integer", init_value=0),
    ]
    const_ok = FuncCallStmt(FuncCall(name="GetStringPos", args=(VarRef("Template"),)))
    wrong_datatype = FuncCallStmt(FuncCall(name="GetStringPos", args=(VarRef("Cursor"),)))
    not_a_reference = FuncCallStmt(FuncCall(name="GetStringPos", args=(1,)))
    bp.modulecode = ModuleCode(equationblocks=[_equation(const_ok, wrong_datatype, not_a_reference)])

    diagnostics = [d.code.value for d in validate_basepicture(bp)]

    assert diagnostics == ["SL-V047", "SL-V014"]


def test_builtin_output_argument_is_checked_against_its_declaration():
    """An ``out`` argument is a declaration check, not a value check."""
    bp = _base_picture()
    bp.localvariables = [
        _var("Source", "string", init_value=""),
        _var("Destination", "integer", init_value=0),
        _var("Status", "integer", init_value=0),
    ]
    call = FuncCallStmt(FuncCall(name="CopyString", args=(VarRef("Source"), VarRef("Destination"), VarRef("Status"))))
    bp.modulecode = ModuleCode(equationblocks=[_equation(call)])

    codes = [d.code.value for d in validate_basepicture(bp)]

    assert "SL-V047" in codes


def test_transition_guard_must_be_boolean():
    """A ``WAIT_FOR`` guard follows the same boolean rule as an IF condition."""
    transition = SFCTransition(name="TrCount", condition=VarRef("Count"))
    bp = _base_picture()
    bp.localvariables = [_var("Count", "integer", init_value=0)]
    bp.modulecode = ModuleCode(sequences=[_sequence(transition, name="Counter")])

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.CONDITION_NOT_BOOLEAN]

    assert [d.code.value for d in diagnostics] == ["SL-V030"]
    assert "transition guard" in diagnostics[0].message


def test_transition_guard_accepts_a_boolean():
    transition = SFCTransition(name="TrDone", condition=VarRef("Done"))
    bp = _base_picture()
    bp.localvariables = [_var("Done", "boolean", init_value=False)]
    bp.modulecode = ModuleCode(sequences=[_sequence(transition, name="Counter")])

    assert [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.CONDITION_NOT_BOOLEAN] == []


def test_builtin_record_field_access_carries_the_declared_field_type():
    """A builtin record field resolves to its declared type, not just to silence.

    ``AsyncOperation.Status`` is an integer field, so assigning it to an integer
    target is clean and assigning it to a boolean target is a type mismatch.
    """
    bp = _typed_bp(
        [_var("AsyncOperation1", "AsyncOperation"), _var("Count", "integer"), _var("Flag", "boolean")],
        Assignment(VarRef("Count"), VarRef("AsyncOperation1.Status"), span=None),
        Assignment(VarRef("Flag"), VarRef("AsyncOperation1.Status"), span=None),
    )
    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V029"]


def test_unresolved_field_on_opaque_or_builtin_record_stays_silent():
    bp = _base_picture()
    bp.localvariables = [
        _var("Group", "GroupData"),
        _var("File", "TextFile"),
        _var("Sink", "boolean", init_value=False),
    ]
    first = Assignment(VarRef("Sink"), VarRef("Group.Executing"), span=None)
    second = Assignment(VarRef("Sink"), VarRef("File.Name"), span=None)
    bp.modulecode = ModuleCode(equationblocks=[_equation(first, second)])
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V019" not in codes


def test_temporal_component_accessors_are_not_undefined():
    bp = _base_picture()
    bp.localvariables = [
        _var("Stamp", "time"),
        _var("Elapsed", "duration"),
        _var("Sink", "integer", init_value=0),
    ]
    first = Assignment(VarRef("Sink"), VarRef("Stamp.Time"), span=None)
    second = Assignment(VarRef("Sink"), VarRef("Elapsed.Milliseconds"), span=None)
    bp.modulecode = ModuleCode(equationblocks=[_equation(first, second)])
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V019" not in codes


def test_assignment_to_sequence_runtime_accessor_is_not_undefined():
    bp = _base_picture()
    step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks(active=[Assignment(VarRef("Seq.Reset"), True)]))
    sequence = _sequence(step, name="Seq")
    bp.modulecode = ModuleCode(sequences=[sequence])
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V019" not in codes


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
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(fn, Assignment(VarRef("Out", span=None), expression_nodes, span=None))]
    )
    diagnostics = validate_basepicture(bp)
    assert "SL-V013" not in {d.code.value for d in diagnostics}
    assert diagnostics == ()


def test_sfc_structural_rules_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("In", "integer", init_value=0)]
    step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks(active=[Assignment(VarRef("In"), 0)]))
    step2 = SFCStep(kind="step", name="Step2", code=SFCCodeBlocks())
    bp.modulecode = ModuleCode(sequences=[_sequence(step, step2)])
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V016" in codes


def test_sfc_fork_target_checks():
    # SEQFORK is a suffix of its host step/transition, never a body element.
    bad_step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks(), fork=SFCFork(targets=("Nope",)))
    bad = _base_picture()
    bad.modulecode = ModuleCode(sequences=[_sequence(bad_step)])
    codes = {d.code.value for d in validate_basepicture(bad)}
    assert "SL-V017" in codes

    good_step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks())
    good_transition = SFCTransition(name="TrGo", condition=True, fork=SFCFork(targets=("Init",)))
    good = _base_picture()
    good.modulecode = ModuleCode(sequences=[_sequence(good_step, good_transition)])
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
    bp.modulecode = ModuleCode(
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
    bp.modulecode = ModuleCode(
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
    assert validate_basepicture(bp) == ()


def test_duplicate_sfc_element_names_flagged():
    bp = _base_picture()
    step_a = SFCStep(kind="step", name="Work", code=SFCCodeBlocks())
    step_b = SFCStep(kind="step", name="work", code=SFCCodeBlocks())
    bp.modulecode = ModuleCode(
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
    codes = {d.code.value for d in validate_basepicture(bp)}
    assert "SL-V021" in codes


def test_sfc_branch_start_checks_skip_leading_comments():
    alt = _base_picture()
    alt.modulecode = ModuleCode(
        sequences=[
            _sequence(
                SFCStep(kind="init", name="Init", code=SFCCodeBlocks()),
                SFCAlternative(
                    branches=[[CodeComment(text="(* c *)"), SFCStep(kind="step", name="Bad", code=SFCCodeBlocks())]]
                ),
            )
        ]
    )
    assert "SL-V023" in {d.code.value for d in validate_basepicture(alt)}

    par = _base_picture()
    par.modulecode = ModuleCode(
        sequences=[
            _sequence(
                SFCStep(kind="init", name="Init", code=SFCCodeBlocks()),
                SFCParallel(branches=[[CodeComment(text="(* c *)"), SFCTransition(name="BadTr", condition=True)]]),
            )
        ]
    )
    assert "SL-V024" in {d.code.value for d in validate_basepicture(par)}


def test_builtin_out_arg_beyond_call_args_not_flagged():
    bp = _base_picture()
    bp.localvariables = [_var("A", "time")]
    bp.modulecode = ModuleCode(equationblocks=[_equation(FuncCallStmt(FuncCall(name="CopyTime", args=(VarRef("A"),))))])
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
    bp.modulecode = ModuleCode(sequences=None, equationblocks=None)
    assert validate_basepicture(bp) == ()
    empty = _base_picture()
    assert validate_basepicture(empty) == ()


def test_identifier_checks_cover_every_equation():
    bp = _base_picture()
    bp.modulecode = ModuleCode(equationblocks=[_equation(name="First"), _equation(name="X" * 21)])
    codes = [diagnostic.code for diagnostic in validate_basepicture(bp)]
    assert codes.count(DiagnosticCode.IDENTIFIER_TOO_LONG) == 1


def test_moduletype_and_nested_module_walks():
    child_type = SingleModule(
        header=_module_header("Child"),
        localvariables=[_var("Local", "integer")],
        modulecode=ModuleCode(equationblocks=[_equation(Assignment(VarRef("Local"), 1))]),
    )
    moduletype = ModuleTypeDef(
        name="T",
        moduleparameters=[_var("P", "integer")],
        localvariables=[_var("L", "integer")],
        submodules=[ModuleTypeInstance(header=_module_header("Inst"), moduletype_name="T")],
        modulecode=ModuleCode(equationblocks=[_equation(Assignment(VarRef("P"), 0))]),
    )
    frame = FrameModule(
        header=_module_header("Frame"),
        submodules=[child_type],
        modulecode=ModuleCode(equationblocks=[_equation(Assignment(VarRef("P", span=None), 0, span=None))]),
    )
    bp = _base_picture()
    bp.localvariables = [_var("P", "integer")]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [frame]
    diagnostics = validate_basepicture(bp)
    assert diagnostics == ()


def _transfer(
    target: str, source: str | None, *, global_: bool = False, source_type: MappingSource = MappingSource.VALUE
) -> ParameterMapping:
    return ParameterMapping(
        target=VarRef(target),
        source_type=source_type,
        is_duration=False,
        is_source_global=global_,
        source=VarRef(source) if source else None,
    )


def _mapping_with_state(target: str, source: str, state: str) -> ParameterMapping:
    """A mapping whose source carries a ``:Old`` or ``:New`` suffix."""
    return ParameterMapping(
        target=VarRef(target),
        source_type=MappingSource.VARIABLE,
        is_duration=False,
        is_source_global=False,
        source=VarRef(source, state=state),
    )


def test_param_transfer_type_mismatch_flagged():
    moduletype = ModuleTypeDef(
        name="ChildType",
        moduleparameters=[_var("EnableFlag", "boolean")],
        modulecode=ModuleCode(equationblocks=[_equation(Assignment(VarRef("EnableFlag"), False))]),
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


def test_param_transfer_undefined_source_is_reported():
    """A typo in a mapping source is one finding at the mapping span."""
    moduletype = ModuleTypeDef(name="T", moduleparameters=[_var("EnableFlag", "boolean")])
    bp = _base_picture()
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Inst"),
            moduletype_name="T",
            parametermappings=[_transfer("EnableFlag", "NoSuchVariable")],
        )
    ]

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V019"]
    assert "NoSuchVariable" in diagnostics[0].message


def test_an_undefined_source_does_not_hide_an_unknown_target():
    moduletype = ModuleTypeDef(name="T", moduleparameters=[_var("EnableFlag", "boolean")])
    bp = _base_picture()
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Inst"),
            moduletype_name="T",
            parametermappings=[_transfer("MissingFlag", "NoSuchVariable")],
        )
    ]

    codes = [d.code.value for d in validate_basepicture(bp)]

    assert codes == ["SL-V019", "SL-V048"]


def test_single_module_undefined_mapping_source_is_reported():
    child = _single_module("Child", [_var("EnableFlag", "boolean")], [_transfer("EnableFlag", "NoSuchVariable")])
    bp = _base_picture()
    bp.submodules = [child]

    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V019"]


def test_mapping_source_is_checked_when_the_target_type_is_unknown():
    """The source resolves in the invoking scope, so it is judged without the formals.

    Only the target side needs the formals: a duplicate target or an absent
    formal stays unproven, while an undefined source is a local defect.
    """
    bp = _base_picture()
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Inst"),
            moduletype_name="NotLoaded",
            parametermappings=[_transfer("EnableFlag", "NoSuchVariable")],
        )
    ]

    diagnostics = validate_basepicture(bp)

    # The unknown module type and the undefined source are both provable.
    assert [d.code.value for d in diagnostics] == ["SL-V058", "SL-V019"]


def test_dotted_mapping_target_compares_the_field_datatype():
    """``Settings.Flag => CounterValue`` is a boolean field mapped from an integer."""
    record = DataType(
        name="Settings",
        description=None,
        datecode=None,
        var_list=[_var("Flag", "boolean"), _var("Level", "real")],
    )
    moduletype = ModuleTypeDef(name="T", moduleparameters=[_var("Settings", "Settings")])
    bp = _base_picture()
    bp.datatype_defs = [record]
    bp.localvariables = [_var("CounterValue", "integer"), _var("GainValue", "real")]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Inst"),
            moduletype_name="T",
            parametermappings=[_transfer("Settings.Flag", "CounterValue"), _transfer("Settings.Level", "GainValue")],
        )
    ]

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V027"]
    assert "boolean" in diagnostics[0].message


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
            ],
        )
    ]
    diagnostics = validate_basepicture(bp)
    assert diagnostics == ()


def test_param_transfer_skips_a_dotted_target_the_type_graph_cannot_resolve():
    """An unknown field is the mapping-target rule's finding, not a transfer one."""
    record = DataType(name="Settings", description=None, datecode=None, var_list=[_var("Flag", "boolean")])
    moduletype = ModuleTypeDef(name="T", moduleparameters=[_var("Settings", "Settings")])
    bp = _base_picture()
    bp.datatype_defs = [record]
    bp.localvariables = [_var("CounterValue", "integer")]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Inst"),
            moduletype_name="T",
            parametermappings=[_transfer("Settings.Missing", "CounterValue")],
        )
    ]

    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V048"]


def test_mapping_source_is_checked_even_when_the_target_field_is_opaque():
    """A typo in the source is independent of an unmodelled target shape."""
    moduletype = ModuleTypeDef(name="T", moduleparameters=[_var("Settings", "ComliMessage")])
    bp = _base_picture()
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Inst"),
            moduletype_name="T",
            parametermappings=[_transfer("Settings.Field", "MissingSource")],
        )
    ]

    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V019"]


def test_param_mapping_absent_target_is_reported_on_a_moduletype_instance():
    """A mapping that names no declared parameter is the rule's headline case."""
    moduletype = ModuleTypeDef(name="T", moduleparameters=[_var("Gain", "real")])
    bp = _base_picture()
    bp.localvariables = [_var("SpeedRef", "real")]
    bp.moduletype_defs = [moduletype]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Inst"),
            moduletype_name="T",
            parametermappings=[_transfer("AbsentParam", "SpeedRef")],
        )
    ]
    diagnostics = validate_basepicture(bp)
    assert [d.code.value for d in diagnostics] == ["SL-V048"]
    assert "AbsentParam" in diagnostics[0].message


def _single_module(
    name: str,
    parameters: list[Variable],
    mappings: list[ParameterMapping] | None = None,
) -> SingleModule:
    return SingleModule(
        header=_module_header(name),
        moduleparameters=parameters,
        parametermappings=mappings or [],
    )


def test_single_module_parameter_mappings_are_checked():
    """A plain submodule declaration carries the same mapping contract as a type."""
    child = _single_module("Child", [_var("EnableFlag", "boolean")], [_transfer("EnableFlag", "Counter")])
    bp = _base_picture()
    bp.localvariables = [_var("Counter", "integer")]
    bp.submodules = [child]

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V027"]
    assert "Child" in diagnostics[0].message


def test_single_module_duplicate_mapping_target_is_reported():
    child = _single_module(
        "Child",
        [_var("Gain", "real")],
        [_transfer("Gain", "SpeedRef"), _transfer("gain", "SpeedRef")],
    )
    bp = _base_picture()
    bp.localvariables = [_var("SpeedRef", "real")]
    bp.submodules = [child]

    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V049"]


def test_single_module_unknown_mapping_target_is_reported():
    child = _single_module("Child", [_var("Gain", "real")], [_transfer("Absent", "SpeedRef")])
    bp = _base_picture()
    bp.localvariables = [_var("SpeedRef", "real")]
    bp.submodules = [child]

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V048"]
    assert "Absent" in diagnostics[0].message


def test_unknown_moduletype_still_reports_duplicate_mapping_targets():
    """An unknown type hides the formals, not the purely local duplicate rule."""
    bp = _base_picture()
    bp.localvariables = [_var("SpeedRef", "real")]
    bp.submodules = [
        ModuleTypeInstance(
            header=_module_header("Inst"),
            moduletype_name="NotLoaded",
            parametermappings=[_transfer("Gain", "SpeedRef"), _transfer("Gain", "SpeedRef")],
        )
    ]

    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V058", "SL-V049"]


def test_unknown_moduletype_name_reports_a_span_and_can_be_suppressed():
    header = ModuleHeader(name="Inst", invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0), declaration_span=SourceSpan(3, 7, 1, 4))
    bp = _base_picture()
    bp.submodules = [ModuleTypeInstance(header=header, moduletype_name="NotLoaded")]

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V058"]
    assert "NotLoaded" in diagnostics[0].message
    assert diagnostics[0].span == SourceSpan(3, 7, 1, 4)
    assert validate_basepicture(bp, allow_unresolved_external_datatypes=True) == ()


def test_frame_module_identifiers_are_checked_like_a_single_module():
    frame = FrameModule(
        header=_module_header("Frame"),
        moduleparameters=[_var("ModuleDef", "integer")],
        localvariables=[_var("A" * 21, "integer")],
        modulecode=ModuleCode(equationblocks=[_equation(name="X" * 21)]),
    )
    bp = _base_picture()
    bp.submodules = [frame]

    codes = [d.code.value for d in validate_basepicture(bp)]

    assert codes.count("SL-V038") == 2
    assert codes.count("SL-V039") == 1


def test_local_datatype_wins_over_an_external_definition_of_the_same_name():
    """A file's own definition decides its own types, as docs/validation.md says."""
    local_integer = DataType(name="Reading", description=None, datecode=1, var_list=[_var("Field", "integer")])
    external_boolean = DataType(name="Reading", description=None, datecode=2, var_list=[_var("Field", "boolean")])

    file_integer = _typed_bp(
        [_var("Rec", "Reading")],
        Assignment(VarRef("Rec.Field"), 1),
        datatypes=[local_integer],
    )
    assert [d.code.value for d in validate_basepicture(file_integer, external_datatypes=[external_boolean])] == []

    # The other direction proves precedence: the file's boolean field wins, so
    # the same integer assignment is now a mismatch.
    file_boolean = _typed_bp(
        [_var("Rec", "Reading")],
        Assignment(VarRef("Rec.Field"), 1),
        datatypes=[external_boolean],
    )
    assert [d.code.value for d in validate_basepicture(file_boolean, external_datatypes=[local_integer])] == ["SL-V029"]


def test_builtin_record_wins_over_local_and_external_datatypes():
    local = DataType(name="BooleanSignal", description=None, datecode=1, var_list=[_var("Value", "integer")])
    external = DataType(name="BooleanSignal", description=None, datecode=2, var_list=[_var("Value", "real")])
    bp = _typed_bp(
        [_var("Signal", "BooleanSignal")],
        Assignment(VarRef("Signal.Value"), True),
        datatypes=[local],
    )

    assert validate_basepicture(bp, external_datatypes=[external]) == ()


def test_parse_and_validate_accepts_external_definitions():
    """A consumer with loaded dependency definitions resolves them in one call."""
    source = """"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
    Rec: Reading;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        Rec.Field = 1;
ENDDEF (*BasePicture*);
"""
    reading = DataType(name="Reading", description=None, datecode=1, var_list=[_var("Field", "integer")])

    _, without = parse_and_validate(source)
    _, with_external = parse_and_validate(source, external_datatypes=[reading])

    assert DiagnosticCode.UNKNOWN_DATATYPE_NAME in {diagnostic.code for diagnostic in without}
    assert without and with_external == ()


def test_parse_and_validate_can_allow_unresolved_external_datatypes():
    """The single-file escape hatch is reachable without calling the validator."""
    source = """"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
    Rec: Reading;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        Rec.Field = 1;
ENDDEF (*BasePicture*);
"""

    _, diagnostics = parse_and_validate(source, allow_unresolved_external_datatypes=True)

    assert DiagnosticCode.UNKNOWN_DATATYPE_NAME not in {diagnostic.code for diagnostic in diagnostics}


def test_const_propagates_through_a_dotted_write_target():
    record = DataType(name="Rec", description=None, datecode=1, var_list=[_var("Field", "integer")])
    bp = _typed_bp(
        [_var("Rec", "Rec", const=True), _var("Mirror", "integer"), _var("Status", "integer")],
        Assignment(VarRef("Rec.Field"), 1),
        FuncCallStmt(FuncCall(name="CopyVariable", args=(VarRef("Mirror"), VarRef("Rec.Field"), VarRef("Status")))),
        datatypes=[record],
    )

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.WRITE_TO_CONST_VARIABLE]

    assert len(diagnostics) == 2
    assert all("Rec.Field" in d.message for d in diagnostics)


def test_every_definition_of_a_duplicated_datatype_name_is_validated():
    bp = _base_picture()
    bp.datatype_defs = [
        DataType(name="Rec", description=None, datecode=1, var_list=[_var("Bad", "NoSuchType")]),
        DataType(name="Rec", description=None, datecode=2, var_list=[_var("Fine", "integer")]),
    ]

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.UNKNOWN_DATATYPE_NAME]

    assert [d.code.value for d in diagnostics] == ["SL-V020"]
    assert "NoSuchType" in diagnostics[0].message


def test_subseqtransition_starting_with_a_step_reports_its_own_code():
    """A leading step in a SUBSEQTRANSITION is SL-V054, not the branch code."""
    step = SFCStep(kind="init", name="Init", code=SFCCodeBlocks())
    sub = SFCTransitionSub(
        name="TSub",
        body=[
            SFCStep(kind="step", name="Inner", code=SFCCodeBlocks()),
            SFCTransition(name="TrInner", condition=True),
        ],
    )
    bp = _base_picture()
    bp.modulecode = ModuleCode(sequences=[_sequence(step, SFCTransition(name="TrDone", condition=True), sub)])

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.SUBSEQTRANSITION_STARTS_WITH_STEP]

    assert [d.code.value for d in diagnostics] == ["SL-V054"]
    assert "SUBSEQTRANSITION" in diagnostics[0].message
    assert "ALTERNATIVESEQ" not in diagnostics[0].message


def test_alternative_branch_starting_with_a_step_keeps_the_branch_code():
    bp = _base_picture()
    bp.modulecode = ModuleCode(
        sequences=[
            _sequence(
                SFCStep(kind="init", name="Init", code=SFCCodeBlocks()),
                SFCAlternative(
                    branches=[[SFCStep(kind="step", name="Bad", code=SFCCodeBlocks())]],
                ),
            )
        ]
    )

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.SFC_ALTERNATIVE_BRANCH_START]

    assert [d.code.value for d in diagnostics] == ["SL-V023"]
    assert "ALTERNATIVESEQ" in diagnostics[0].message


def test_datatype_lookup_has_no_unicode_casefold_fallback():
    record = DataType(name="strasse", description=None, datecode=1, var_list=[])
    records = {fold_identifier("strasse"): record}

    assert lookup_datatype(records, "strasse") is record
    # Full Unicode case folding would equate these two names; SattLine does not.
    assert lookup_datatype(records, "Straße") is None


def test_signature_only_system_records_declare_and_type_their_builtin_arguments():
    """The COMLI and PID parameter types resolve instead of reporting SL-V020."""
    bp = _base_picture()
    bp.localvariables = [
        _var("Mess", "ComliMessage"),
        _var("Data", "ByteRecord"),
        _var("PidPar", "PidType"),
        _var("Signal", "AnalogSignalIn"),
        _var("Output", "AnalogSignalOut"),
    ]
    bp.modulecode = ModuleCode(
        equationblocks=[
            _equation(
                FuncCallStmt(FuncCall(name="getreceivedcomlidata", args=(VarRef("Mess"), VarRef("Data")))),
                FuncCallStmt(FuncCall(name="pid", args=(VarRef("PidPar"), 1.0, VarRef("Signal"), VarRef("Output")))),
            )
        ]
    )

    assert validate_basepicture(bp) == ()


def test_anytype_is_exempt_from_the_condition_and_ternary_rules():
    bp = _typed_bp(
        [_var("AnyVar", "AnyType"), _var("Count", "integer"), _var("Flag", "boolean")],
        IfStmt(branches=((VarRef("AnyVar"), (Assignment(VarRef("Flag"), True),)),), else_block=None),
        Assignment(VarRef("Count"), TernaryOp(branches=((True, VarRef("AnyVar")),), else_expr=VarRef("Count"))),
    )

    codes = [d.code.value for d in validate_basepicture(bp)]

    assert "SL-V030" not in codes
    assert "SL-V044" not in codes


def test_anytype_is_exempt_from_the_enable_tail_rule():
    bp = _base_picture()
    bp.localvariables = [_var("AnyVar", "AnyType")]
    bp.moduledef = ModuleDef(
        graph_objects=[
            GraphObject("RectangleObject", properties={"enable_tail": VarRef("AnyVar")}),
        ]
    )

    assert [d.code.value for d in validate_basepicture(bp) if d.code is DiagnosticCode.CONDITION_NOT_BOOLEAN] == []


def test_validator_signature_view_is_cached_and_has_no_write_position_copy():
    first = builtin_function_signature("CopyTime")
    second = builtin_function_signature("copytime")

    assert first is not None and first is second
    assert [(p.name, p.direction) for p in first.parameters] == [("Source", "in var"), ("Destination", "out")]


def test_diagnostic_model_defaults():
    diag = Diagnostic(code=DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS, message="m")
    assert diag.span is None
    assert diag.code.value == "SL-V016"
    assert isinstance(DiagnosticCode.DUPLICATE_VARIABLE_NAME, DiagnosticCode)


def _typed_bp(variables: list[Variable], *items: object, datatypes: list[DataType] | None = None) -> BasePicture:
    """A base picture whose single equation holds ``items``, for typing tests."""
    bp = _base_picture()
    bp.localvariables = variables
    if datatypes is not None:
        bp.datatype_defs = datatypes
    bp.modulecode = ModuleCode(equationblocks=[_equation(*items)])
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
    """The rule is narrower than "temporal is always fine".

    A duration or time compared against an integer or real literal is accepted:
    ``Elapsed == 5``, ``Elapsed > 2.5`` and ``Stamp == 5``. Two temporal
    operands are rejected with the same code: ``ZeroDur == ZeroFull``,
    ``NegFive == NegHour`` and ``DurFull == DurBare``.

    The valid fixture ``TemporalVsNumericCompare.s`` and the invalid fixture
    ``TemporalVsTemporalCompare.s`` pin both sides.
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
    # Both operands of each comparison are temporal and each offending operand
    # gets its own finding, so two comparisons yield four diagnostics.
    assert [d.code.value for d in validate_basepicture(temporal_side)] == ["SL-V028"] * 4


def test_operand_diagnostics_point_at_each_operand_not_the_whole_comparison():
    """Each operand finding carries its own span and names its operand."""
    _bp, diagnostics = parse_and_validate(_raw(_corpus("invalid/TemporalVsTemporalCompare.s")))
    operand_findings = [d for d in diagnostics if d.code is DiagnosticCode.OPERAND_NOT_NUMERIC]

    assert len(operand_findings) == 12
    first_comparison = operand_findings[:2]
    spans = [d.span for d in first_comparison]
    assert all(span is not None for span in spans)
    assert spans[0] != spans[1]
    assert [span.column for span in spans if span is not None] == [14, 25]
    assert "ZeroDur" in first_comparison[0].message
    assert "ZeroFull" in first_comparison[1].message


def test_operand_rule_allows_boolean_equality():
    boolean = _typed_bp(
        [_var("Run", "boolean"), _var("Sink", "boolean")],
        Assignment(VarRef("Sink"), Compare(VarRef("Run"), "==", VarRef("Run"))),
    )
    assert [d.code.value for d in validate_basepicture(boolean)] == []


def test_operand_rule_flags_incompatible_equality():
    mixed = _typed_bp(
        [_var("Run", "boolean"), _var("Count", "integer"), _var("Sink", "boolean")],
        Assignment(VarRef("Sink"), Compare(VarRef("Run"), "==", VarRef("Count"))),
    )
    assert [d.code.value for d in validate_basepicture(mixed)] == ["SL-V041"]


def test_assignment_rule_allows_numeric_widening_and_same_family():
    """Integer into real and same-family assignment are accepted, so silent."""
    bp = _typed_bp(
        [
            _var("Count", "integer"),
            _var("Rate", "real"),
            _var("Flag1", "boolean"),
            _var("Flag2", "boolean"),
        ],
        Assignment(VarRef("Rate"), VarRef("Count")),
        Assignment(VarRef("Count"), VarRef("Count")),
        Assignment(VarRef("Flag2"), VarRef("Flag1")),
        Assignment(VarRef("Rate"), 1.5),
    )
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_string_assignment_rule_covers_every_string_family():
    """Every native string family is copied, never assigned directly.

    The five families share the copy-only rule, so the destination datatype
    decides the finding and the source family is irrelevant.
    """
    families = ("string", "identstring", "tagstring", "maxstring", "linestring")
    targets = [("Dest" + str(index), name) for index, name in enumerate(families)]
    bp = _typed_bp(
        [*(_var(target, name) for target, name in targets), _var("Source", "string")],
        *(Assignment(VarRef(target), VarRef("Source")) for target, _name in targets),
    )
    codes = [d.code.value for d in validate_basepicture(bp)]
    assert codes == ["SL-V045"] * len(families)
    messages = [d.message for d in validate_basepicture(bp)]
    assert all("CopyString() or CopyVar()" in message for message in messages)
    assert "Dest0" in messages[0]


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


def test_ternary_condition_is_checked_and_branch_types_merge():
    """An inline IF expression is condition-checked; numeric branches merge to real."""
    bp = _typed_bp(
        [_var("Count", "integer"), _var("Rate", "real"), _var("Flag1", "boolean")],
        Assignment(
            VarRef("Flag1"), TernaryOp(branches=((VarRef("Count"), VarRef("Count")),), else_expr=VarRef("Rate"))
        ),
    )
    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V029", "SL-V030"]


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


def test_attribute_combination_rejects_opsave_followed_by_state_or_const():
    """The attribute order is significant.

    ``OpSave State`` is rejected, ``State OpSave`` is accepted, and
    ``OpSave Const`` is rejected. The invalid corpus fixtures
    ``OpSaveAndStateCombined.s`` and ``OpSaveConstCombined.s`` and the valid
    fixture ``VariableModifiers.s`` pin the three forms.
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
    """``State OpSave`` is accepted, so the reversed order must stay clean."""
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
    module_def = ModuleDef(clipping=ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (integer_tail,)))
    bp = _base_picture()
    bp.localvariables = [_var("Source", "integer")]
    bp.moduledef = module_def
    assert "SL-V032" in [d.code.value for d in validate_basepicture(bp)]

    module_def.clipping = ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (real_tail,))
    bp.localvariables = [_var("Source", "real")]
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_coordinate_tail_rule_covers_bare_variable_tails():
    """A coordinate position is never an integer, computed or bare."""
    module_def = ModuleDef(clipping=ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (VarRef("Source"),)))
    bp = _base_picture()
    bp.localvariables = [_var("Source", "integer")]
    bp.moduledef = module_def
    assert "SL-V032" in [d.code.value for d in validate_basepicture(bp)]

    bp.localvariables = [_var("Source", "real")]
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_coordinate_tail_rule_skips_reference_names():
    """An InVar_ "Name" tail is a reference, not a value, so it stays silent."""
    module_def = ModuleDef(
        clipping=ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (VarTail("in", "ClipX"),)),
    )
    bp = _base_picture()
    bp.moduledef = module_def
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_coordinate_tail_rule_exempts_anytype():
    """``AnyType`` proves nothing about a coordinate value, so the rule is silent.

    Whether the language accepts such a tail is an open question, so the rule
    reports only a value it can prove is not real.
    """
    module_def = ModuleDef(clipping=ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (VarRef("Raw"),)))
    bp = _base_picture()
    bp.localvariables = [_var("Raw", "AnyType")]
    bp.moduledef = module_def
    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_graph_enable_tail_reports_undefined_variable():
    """A parenthesised Enable_ tail is a real expression use (SL-V019)."""
    bp = _base_picture()
    bp.moduledef = ModuleDef(
        graph_objects=[
            GraphObject("RectangleObject", properties={"enable_tail": VarRef("MissingEnable")}),
        ]
    )

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.UNDEFINED_VARIABLE]

    assert [d.code.value for d in diagnostics] == ["SL-V019"]
    assert "MissingEnable" in diagnostics[0].message


def test_graph_enable_tail_must_be_boolean():
    """An Enable_ expression tail uses the boolean-condition rule (SL-V030)."""
    bp = _base_picture()
    bp.localvariables = [_var("Count", "integer")]
    bp.moduledef = ModuleDef(
        graph_objects=[
            GraphObject("RectangleObject", properties={"enable_tail": BinOp(VarRef("Count"), "+", 1)}),
        ]
    )

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.CONDITION_NOT_BOOLEAN]

    assert [d.code.value for d in diagnostics] == ["SL-V030"]
    assert "Enable_ tail condition" in diagnostics[0].message


def test_graph_colour_tail_reports_undefined_variable_once():
    """A colour tail is checked, and the flat tails view does not duplicate it."""
    missing = VarRef("MissingColour")
    colour = ColourSpec(
        kind="outline",
        assignments=(TailedClause(key="Colour0", value=1, tail=missing),),
    )
    bp = _base_picture()
    bp.moduledef = ModuleDef(
        graph_objects=[
            GraphObject("RectangleObject", properties={"colours": [colour], "tails": [missing]}),
        ]
    )

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.UNDEFINED_VARIABLE]

    assert [d.code.value for d in diagnostics] == ["SL-V019"]
    assert "MissingColour" in diagnostics[0].message


def test_interact_enable_and_assign_tails_report_undefined_variables():
    """Interact clauses carry expression tails that must resolve in scope."""
    bp = _base_picture()
    bp.moduledef = ModuleDef(
        interact_objects=[
            InteractObject(
                "ComBut_",
                properties={
                    "enables": [EnableClause(True, VarRef("MissingEnable"))],
                    "assigns": [AssignClause("Value", 0, VarRef("MissingAssign"))],
                    "body": [VarRef("MissingBody")],
                    "tails": [VarRef("MissingFlat")],
                },
            )
        ]
    )

    messages = [d.message for d in validate_basepicture(bp) if d.code is DiagnosticCode.UNDEFINED_VARIABLE]

    assert len(messages) == 4
    assert any("MissingEnable" in message for message in messages)
    assert any("MissingAssign" in message for message in messages)
    assert any("MissingBody" in message for message in messages)
    assert any("MissingFlat" in message for message in messages)


def test_module_in_view_tail_is_walked():
    """A ``Module_In_View`` tail is an annotation, so unresolved names are reported."""
    bp = _base_picture()
    bp.header = ModuleHeader(
        name="Base",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        arguments=ModuleArguments(module_in_view=ModuleInViewClause(True, VarRef("MissingView"))),
    )

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.UNDEFINED_VARIABLE]

    assert [d.code.value for d in diagnostics] == ["SL-V019"]
    assert "MissingView" in diagnostics[0].message


def test_header_enable_tail_reports_undefined_and_non_boolean():
    """The unit header is checked in the base scope, not skipped."""
    missing = _base_picture()
    missing.header = ModuleHeader(
        name="Base",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        arguments=ModuleArguments(enable=EnableClause(True, VarRef("MissingHeaderEnable"))),
    )
    undefined = [d for d in validate_basepicture(missing) if d.code is DiagnosticCode.UNDEFINED_VARIABLE]
    assert [d.code.value for d in undefined] == ["SL-V019"]

    integer_tail = _base_picture()
    integer_tail.localvariables = [_var("Count", "integer")]
    integer_tail.header = ModuleHeader(
        name="Base",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        arguments=ModuleArguments(enable=EnableClause(True, BinOp(VarRef("Count"), "+", 1))),
    )
    not_boolean = [d for d in validate_basepicture(integer_tail) if d.code is DiagnosticCode.CONDITION_NOT_BOOLEAN]
    assert [d.code.value for d in not_boolean] == ["SL-V030"]


def test_header_coordinate_tail_reports_undefined_variable():
    bp = _base_picture()
    bp.header = ModuleHeader(
        name="Base",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        invoke_coord_tails=[VarRef("MissingCoord")],
    )

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.UNDEFINED_VARIABLE]

    assert [d.code.value for d in diagnostics] == ["SL-V019"]
    assert "MissingCoord" in diagnostics[0].message


def test_submodule_header_tail_uses_parent_scope():
    """A submodule header is evaluated in the invoking module's scope."""
    header = ModuleHeader(
        name="Child",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        invoke_coord_tails=[VarRef("ParentVar")],
    )
    child = SingleModule(header=header, localvariables=[_var("ChildVar", "real")])
    bp = _base_picture()
    bp.localvariables = [_var("ParentVar", "real")]
    bp.submodules = [child]

    assert [d.code.value for d in validate_basepicture(bp)] == []

    header.invoke_coord_tails = [VarRef("ChildVar")]
    assert [d.code.value for d in validate_basepicture(bp) if d.code is DiagnosticCode.UNDEFINED_VARIABLE] == [
        "SL-V019"
    ]


def test_moduletype_layout_coordinate_tail_is_checked():
    """Module-type layout blocks use the module-type scope."""
    moduletype = ModuleTypeDef(
        name="Type",
        localvariables=[_var("Source", "integer")],
        moduledef=ModuleDef(
            clipping=ClippingClause(
                ((-1.0, -1.0), (1.0, 1.0)),
                (BinOp(VarRef("Source"), "+", 1),),
            )
        ),
    )
    bp = _base_picture()
    bp.moduletype_defs = [moduletype]

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.COORDINATE_NOT_REAL]

    assert [d.code.value for d in diagnostics] == ["SL-V032"]


def test_bound_tail_names_are_not_diagnosed_in_annotations():
    """InVar_/OutVar_ names stay silent; query reports them as unresolved uses."""
    bp = _base_picture()
    bp.header = ModuleHeader(
        name="Base",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        arguments=ModuleArguments(enable=EnableClause(True, VarTail("in", "MissingHeaderEnable"))),
        invoke_coord_tails=[VarTail("out", LitStringTail("LitString", "MissingCoord"))],
    )
    bp.moduledef = ModuleDef(
        graph_objects=[
            GraphObject("RectangleObject", properties={"enable_tail": VarTail("in", "MissingGraphEnable")}),
            GraphObject("RectangleObject", properties={"tails": [VarTail("in", "MissingCoordinate")]}),
        ]
    )

    assert [d.code.value for d in validate_basepicture(bp)] == []


def test_a_polygon_point_expression_tail_is_walked():
    """A point tail is an ordinary expression, so an undefined name is reported."""
    point = PolygonPoint(1.0, 2.0, x_tails=(NotOp(VarRef("MissingPointTail")),))
    bp = _base_picture()
    bp.moduledef = ModuleDef(
        graph_objects=[
            GraphObject("PolygonObject", properties={"points": [point]}),
        ]
    )

    assert "SL-V019" in [diagnostic.code.value for diagnostic in validate_basepicture(bp)]


def test_clipping_tail_is_checked_once():
    """The clipping clause owns its tails, so each tail is checked once."""
    tail = BinOp(VarRef("Source"), "+", 1)
    module_def = ModuleDef(
        clipping=ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (tail,)),
    )
    bp = _base_picture()
    bp.localvariables = [_var("Source", "integer")]
    bp.moduledef = module_def

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.COORDINATE_NOT_REAL]

    assert [d.code.value for d in diagnostics] == ["SL-V032"]


def test_an_untyped_builtin_with_unknown_arity_is_not_rejected():
    """``GetPrivilegeFlag`` has no transcribed parameter list, so a call is not judged."""
    bp = _base_picture()
    bp.localvariables = [_var("Flag", "boolean")]
    bp.modulecode = ModuleCode(
        equationblocks=[
            _equation(
                FuncCallStmt(FuncCall("GetPrivilegeFlag", (VarRef("Flag"),))),
                FuncCallStmt(FuncCall("ResetPrivilegeFlag", (VarRef("Flag"),))),
            )
        ]
    )

    assert validate_basepicture(bp) == ()


def test_a_typed_builtin_still_reports_arity():
    bp = _base_picture()
    bp.modulecode = ModuleCode(equationblocks=[_equation(FuncCallStmt(FuncCall("Abs", ())))])

    assert [d.code.value for d in validate_basepicture(bp)] == ["SL-V013"]


def test_a_temporal_field_accessor_is_not_an_undefined_field():
    """A temporal value reached through a record still exposes its accessors."""
    measured = DataType(name="Measured", description=None, datecode=None, var_list=[_var("Stamp", "time")])
    readings = DataType(name="Readings", description=None, datecode=None, var_list=[_var("Entry", "Measured")])
    bp = _base_picture()
    bp.datatype_defs = [measured, readings]
    bp.localvariables = [_var("Readings", "Readings"), _var("Sink", "integer")]
    bp.modulecode = ModuleCode(
        equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Readings.Entry.Stamp.Time")))]
    )

    assert validate_basepicture(bp) == ()


def test_a_field_of_a_duplicated_record_name_stays_silent():
    """A duplicated name has more than one valid shape, so absence is unproven."""
    first = DataType(name="SensorType", description=None, datecode=None, var_list=[_var("Value", "integer")])
    second = DataType(name="SensorType", description=None, datecode=None, var_list=[_var("Level", "real")])
    bp = _base_picture()
    bp.datatype_defs = [first, second]
    bp.localvariables = [_var("Sensor", "SensorType"), _var("Sink", "integer")]
    bp.modulecode = ModuleCode(equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Sensor.Value")))])

    assert validate_basepicture(bp) == ()


def test_known_record_bad_field_is_undefined_on_write_and_read():
    """A field absent from a record declared in this file is a typo, not opacity."""
    record = DataType(name="Reading", description=None, datecode=None, var_list=[_var("Count", "integer")])
    bp = _base_picture()
    bp.datatype_defs = [record]
    bp.localvariables = [_var("Reading", "Reading"), _var("Sink", "integer")]
    bp.modulecode = ModuleCode(
        equationblocks=[
            _equation(
                Assignment(VarRef("Reading.Missing"), 1),
                Assignment(VarRef("Sink"), VarRef("Reading.Missing")),
            )
        ]
    )

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V019", "SL-V019"]
    assert all("Reading.Missing" in diagnostic.message for diagnostic in diagnostics)


def test_known_nested_record_bad_field_is_undefined():
    inner = DataType(name="Inner", description=None, datecode=None, var_list=[_var("Value", "integer")])
    outer = DataType(name="Outer", description=None, datecode=None, var_list=[_var("Nested", "Inner")])
    bp = _base_picture()
    bp.datatype_defs = [inner, outer]
    bp.localvariables = [_var("Outer", "Outer"), _var("Sink", "integer")]
    bp.modulecode = ModuleCode(equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Outer.Nested.Missing")))])

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V019"]
    assert "Outer.Nested.Missing" in diagnostics[0].message


def test_a_field_on_an_unloaded_nested_record_stays_silent():
    """The middle record is not loaded, so the leaf field is unproven."""
    outer = DataType(name="Outer", description=None, datecode=None, var_list=[_var("Nested", "NotLoaded")])
    bp = _base_picture()
    bp.datatype_defs = [outer]
    bp.localvariables = [_var("Outer", "Outer"), _var("Sink", "integer")]
    bp.modulecode = ModuleCode(equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Outer.Nested.Missing")))])

    assert validate_basepicture(bp, allow_unresolved_external_datatypes=True) == ()


def test_a_field_on_an_opaque_builtin_record_stays_silent():
    bp = _base_picture()
    bp.localvariables = [_var("Message", "ComliMessage"), _var("Sink", "integer")]
    bp.modulecode = ModuleCode(equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Message.NoSuchField")))])

    assert validate_basepicture(bp) == ()


def test_sequence_ends_with_step_skips_open_sequences():
    """A closed SEQUENCE must close on a transition; OPENSEQUENCE may end on a step."""
    for seq_type, expected in (
        (const.GRAMMAR_VALUE_SEQUENCE, ["SL-V033"]),
        (const.GRAMMAR_VALUE_OPENSEQUENCE, []),
    ):
        picture = _base_picture()
        picture.modulecode = ModuleCode(
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


def test_on_off_are_treated_exactly_like_true_false():
    """`On`/`Off` are boolean literals and reserved words, like `True`/`False`.

    A declaration is a parse error, and a constructed AST reports the same
    reserved-identifier rule (SL-V039) that `True`/`False` report.
    """
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

    # Declaring either name is a parse error at the declaration position.
    for declarations in (
        "   On: boolean := False;\n   Flag: boolean := False;\n",
        "   Off: boolean := False;\n   Flag: boolean := False;\n",
    ):
        with pytest.raises(UnexpectedInput):
            parse_and_validate(header + picture + "LOCALVARIABLES\n" + declarations + tail)

    # A record field and a datatype name are declaration positions too.
    for typedefs in (
        "TYPEDEFINITIONS\n   Rec = RECORD DateCode_ 2\n      On: boolean;\n   ENDDEF\n",
        "TYPEDEFINITIONS\n   Off = RECORD DateCode_ 2\n      F: boolean;\n   ENDDEF\n",
    ):
        with pytest.raises(UnexpectedInput):
            parse_and_validate(header + picture + typedefs + "LOCALVARIABLES\n   Flag: boolean := False;\n" + tail)

    # Constructed ASTs use the same reserved-identifier rule as True/False.
    for name in ("On", "Off", "True", "False"):
        bp = _base_picture()
        bp.localvariables = [_var(name, "boolean")]
        assert [d.code.value for d in validate_basepicture(bp) if d.code is DiagnosticCode.RESERVED_KEYWORD_NAME] == [
            "SL-V039"
        ], name

    # GroupData stays legal: it is a reserved *type*, not a boolean spelling.
    _, diagnostics = parse_and_validate(
        header + picture + "LOCALVARIABLES\n   GroupData: boolean := False;\n   Flag: boolean := False;\n" + tail
    )
    assert "SL-V039" not in [d.code.value for d in diagnostics]

    # Reading a reserved spelling is fine: `On` is a boolean literal now.
    _, diagnostics = parse_and_validate(header + picture + "LOCALVARIABLES\n   Flag: boolean := False;\n" + tail)
    assert "SL-V019" not in [d.code.value for d in diagnostics]


def test_system_datatype_declarations_resolve_to_declared_fields():
    """System/configuration datatypes are real records, not opaque names.

    A variable may be declared with any of them without a local ``DATATYPE``
    definition, and a field path through it carries the declared field type
    rather than staying unknown.
    """
    from sattline_parser.validation.type_graph import TypeGraph  # noqa: PLC0415

    header = (
        '"Syntax version 2.23, date: 2026-11-02-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-11-02-12:00:00.000, name: SystemTypes"\n'
    )
    picture = "BasePicture Invocation\n   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n    ) : MODULEDEFINITION DateCode_ 1\n\n"
    declarations = (
        "LOCALVARIABLES\n"
        "   Step: StepStatus;\n"
        "   Elapsed: Timer;\n"
        "   GroupInfo: ScanGroupInfo;\n"
        "   Operation: AsyncOperation;\n"
        "   Interact: EventInteract;\n"
        "   Count: integer := 0;\n"
        "   High: integer := 0;\n"
    )
    tail = (
        "\nModuleDef\nClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "      High = Elapsed.High;\n"
        "\nENDDEF (*BasePicture*);\n"
    )

    source = header + picture + declarations + tail
    picture_ast, diagnostics = parse_and_validate(source)
    assert [diagnostic.code.value for diagnostic in diagnostics] == []

    graph = TypeGraph.from_basepicture(picture_ast)
    high = graph.field("Timer", "High")
    assert high is not None and high.datatype is ScalarDatatype.INTEGER
    block = graph.field("StepStatus", "block")
    assert block is None
    transit = graph.field("StepStatus", "transit")
    assert transit is not None and transit.datatype is ScalarDatatype.BOOLEAN
    group_object = graph.field("ScanGroupInfo", "ScanGroupName")
    assert group_object is not None and group_object.datatype is ScalarDatatype.STRING


def test_frame_modules_inherit_the_enclosing_scope():
    """A frame module is display-only: it adds no scope of its own.

    Parameters and locals declared by the enclosing module stay visible inside
    a frame module and inside frames nested further down.
    """
    source = (
        '"Syntax version 2.23, date: 2026-11-02-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-11-02-12:00:00.000, name: FrameScope"\n'
        "BasePicture Invocation\n"
        "   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
        "    ) : MODULEDEFINITION DateCode_ 1\n"
        "\n"
        "MODULEPARAMETERS\n"
        "   ParentParam: boolean := False;\n"
        "\n"
        "LOCALVARIABLES\n"
        "   ParentFlag: boolean := False;\n"
        "\n"
        "SUBMODULES\n"
        "   F1 Invocation\n"
        "      ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
        "       ) : MODULEDEFINITION DateCode_ 3 ( Frame_Module )\n"
        "      SUBMODULES\n"
        "         F2 Invocation\n"
        "            ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5\n"
        "             ) : MODULEDEFINITION DateCode_ 4 ( Frame_Module )\n"
        "            ModuleDef\n"
        "            ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "            ModuleCode\n"
        "               EQUATIONBLOCK Frame2 COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
        "                  ParentFlag = ParentParam;\n"
        "            ENDDEF (*F2*);\n"
        "      ModuleDef\n"
        "      ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "      ModuleCode\n"
        "         EQUATIONBLOCK Frame1 COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
        "            ParentFlag = ParentParam;\n"
        "      ENDDEF (*F1*);\n"
        "\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK Main COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
        "      ParentFlag = ParentParam;\n"
        "\nENDDEF (*BasePicture*);\n"
    )
    picture, diagnostics = parse_and_validate(source)
    assert [(diagnostic.code.value, diagnostic.message) for diagnostic in diagnostics] == []
    assert [parameter.name for parameter in picture.moduleparameters] == ["ParentParam"]
    assert isinstance(picture.submodules[0], FrameModule)

    ordinary_source = source.replace("DateCode_ 3 ( Frame_Module )", "DateCode_ 3")
    _, ordinary_diagnostics = parse_and_validate(ordinary_source)
    assert [diagnostic.code.value for diagnostic in ordinary_diagnostics] == ["SL-V019"] * 4
    assert sum("ParentFlag" in diagnostic.message for diagnostic in ordinary_diagnostics) == 2
    assert sum("ParentParam" in diagnostic.message for diagnostic in ordinary_diagnostics) == 2


def test_ordinary_modules_bound_variable_scope_and_frames_are_transparent():
    parent_assignment = Assignment(VarRef("ParentOutput"), VarRef("ParentInput"))
    frame = FrameModule(
        header=_module_header("Frame"),
        localvariables=[_var("ParentInput", "integer")],
        modulecode=ModuleCode(equationblocks=[_equation(parent_assignment)]),
    )
    nested_frame = FrameModule(
        header=_module_header("NestedFrame"),
        modulecode=ModuleCode(equationblocks=[_equation(Assignment(VarRef("Own"), VarRef("ParentInput")))]),
    )
    ordinary = SingleModule(
        header=_module_header("Ordinary"),
        localvariables=[_var("Own", "boolean")],
        submodules=[nested_frame],
        modulecode=ModuleCode(equationblocks=[_equation(parent_assignment)]),
    )
    bp = _base_picture()
    bp.localvariables = [_var("ParentInput", "boolean"), _var("ParentOutput", "boolean")]
    bp.submodules = [frame, ordinary]

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V019", "SL-V019", "SL-V019"]
    assert "ParentOutput" in diagnostics[0].message
    assert all("ParentInput" in d.message for d in diagnostics[1:])


def test_sfc_element_names_resolve_across_module_bounds():
    """A dotted SFC accessor may name an element from another module block.

    Shipped library code assigns ``Seq.Reset`` from an equation block while the
    sequence lives in a nested module, so the element set is program-wide.
    """
    header = (
        '"Syntax version 2.23, date: 2026-11-02-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-11-02-12:00:00.000, name: SfcScope"\n'
    )
    typedefs = (
        "TYPEDEFINITIONS\n"
        "   Inner = MODULEDEFINITION DateCode_ 2\n"
        "      ModuleDef\n"
        "      ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "      ModuleCode\n"
        "         SEQUENCE InnerSeq ( SeqControl ) COORD 0.0,0.0 OBJSIZE 1.0,1.0\n"
        "            SEQSTEP InnerStep\n"
        "            SEQTRANSITION TrDone WAIT_FOR True\n"
        "         ENDSEQUENCE\n"
        "      ENDDEF (*Inner*);\n"
        "\n"
    )
    picture = "BasePicture Invocation\n   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n    ) : MODULEDEFINITION DateCode_ 1\n\n"
    locals_block = "LOCALVARIABLES\n   Flag: boolean := False;\n\n"
    body = (
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK Main COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
        "      Flag = InnerStep.x;\n"
        "      InnerSeq.Reset = False;\n"
        "      Unknown.x = False;\n"
        "\nENDDEF (*BasePicture*);\n"
    )
    diagnostics = parse_and_validate(header + picture + typedefs + locals_block + body)[1]
    codes = [diagnostic.code.value for diagnostic in diagnostics]
    # The nested element resolves; a genuinely unknown root still reports.
    assert codes == ["SL-V019"]
    assert "Unknown" in diagnostics[0].message


def test_identifier_folding_uses_the_cp1252_byte_table():
    from sattline_parser.names import fold_identifier, identifiers_equal  # noqa: PLC0415

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


def test_equation_and_sequence_name_findings_carry_a_span() -> None:
    source = (
        '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-26-12:00:00.000, name: NameSpans"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK VeryLongEquationName1 COORD 0.0,0.0 OBJSIZE 1.0,1.0 :\n"
        "   SEQUENCE VeryLongSequenceName12 COORD 0.0,0.0 OBJSIZE 1.0,1.0\n"
        "      SEQINITSTEP Init\n"
        "      SEQTRANSITION Done WAIT_FOR True\n"
        "   ENDSEQUENCE\n"
        "ENDDEF (*BasePicture*);\n"
    )

    diagnostics = [d for d in parse_and_validate(source)[1] if d.code.value == "SL-V038"]

    assert {d.message.split()[0] for d in diagnostics} == {"Equation", "Sequence"}
    assert all(d.span is not None for d in diagnostics)


def test_out_of_range_numeric_literals_are_reported() -> None:
    source = (
        '"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n'
        '"Original file date: ---"\n'
        '"Program date: 2026-10-26-12:00:00.000, name: ClampedLiterals"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   Big: integer := 2147483648;\n"
        "   Huge: real := 1.0E39;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ENDDEF (*BasePicture*);\n"
    )

    diagnostics = [d for d in parse_and_validate(source)[1] if d.code.value == "SL-V059"]

    assert len(diagnostics) == 2
    assert all(d.span is not None for d in diagnostics)
    # The node holds the clamped value, so the sentence quotes the text the
    # source wrote: a written 2147483648 is not 2147483647.
    messages = " ".join(d.message for d in diagnostics)
    assert "2147483648" in messages
    assert "1.0E39" in messages
    assert "2147483647" not in messages
    assert all("outside the supported" in d.message for d in diagnostics)


def test_procedure_call_in_a_value_position_is_reported():
    """A known procedure returns no value; an unknown callee stays unproven."""
    bp = _typed_bp(
        [_var("Text", "string"), _var("Sink", "integer")],
        Assignment(VarRef("Sink"), FuncCall("ClearString", [VarRef("Text")])),
        Assignment(VarRef("Sink"), FuncCall("StringLength", [VarRef("Text")])),
        Assignment(VarRef("Sink"), FuncCall("UserProcedure", [VarRef("Text")])),
    )

    diagnostics = [d for d in validate_basepicture(bp) if d.code is DiagnosticCode.PROCEDURE_IN_VALUE_POSITION]

    assert [d.code.value for d in diagnostics] == ["SL-V060"]
    assert "clearstring" in diagnostics[0].message
    assert diagnostics[0].span is None


def test_a_procedure_statement_call_is_not_a_value_position():
    """The statement form is the legal way to call a procedure."""
    bp = _typed_bp(
        [_var("Text", "string")],
        FuncCallStmt(FuncCall("ClearString", [VarRef("Text")])),
    )

    assert validate_basepicture(bp) == ()


def test_setioattribute_const_argument_is_exempt_from_the_caller_write_rule():
    """The argument is the value written into the addressed I/O object."""
    bp = _typed_bp(
        [_var("Fixed", "integer", const=True)],
        FuncCallStmt(FuncCall("SetIoAttribute", [4, 0, 0, 0, 1120, VarRef("Fixed")])),
    )

    assert DiagnosticCode.WRITE_TO_CONST_VARIABLE not in {d.code for d in validate_basepicture(bp)}


def test_another_builtin_output_argument_keeps_the_const_write_rule():
    """The exemption is per builtin parameter, not a blanket ``inout`` rule."""
    bp = _typed_bp(
        [_var("Source", "string"), _var("Limit", "integer", const=True)],
        FuncCallStmt(FuncCall("CopyString", [VarRef("Source"), VarRef("Source"), VarRef("Limit")])),
    )

    assert DiagnosticCode.WRITE_TO_CONST_VARIABLE in {d.code for d in validate_basepicture(bp)}


def test_mapping_source_with_old_on_a_non_state_variable_is_reported():
    """The mapping source resolves in the invoking scope, so :Old applies there."""
    child = SingleModule(
        header=_module_header("Child"),
        moduleparameters=[_var("P", "integer")],
        parametermappings=[_mapping_with_state("P", "Plain", "old")],
    )
    bp = _base_picture()
    bp.localvariables = [_var("Plain", "integer")]
    bp.submodules = [child]

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V005"]
    assert "Plain" in diagnostics[0].message


def test_mapping_source_old_on_a_non_state_field_is_reported():
    """A dotted mapping source follows the field rule, not the variable rule."""
    child = SingleModule(
        header=_module_header("Child"),
        moduleparameters=[_var("P", "integer")],
        parametermappings=[_mapping_with_state("P", "Rec.Flag", "old")],
    )
    record = DataType(name="Rec", description=None, datecode=None, var_list=[_var("Flag", "integer")])

    bp = _base_picture()
    bp.datatype_defs = [record]
    bp.localvariables = [_var("Rec", "Rec")]
    bp.submodules = [child]

    diagnostics = validate_basepicture(bp)

    assert [d.code.value for d in diagnostics] == ["SL-V006"]


def test_external_datatype_does_not_mark_the_file_record_duplicated():
    """The file wins over a same-named dependency, so its field typo is judged."""
    external = DataType(name="Rec", description=None, datecode=None, var_list=[_var("Value", "integer")])
    own = DataType(name="Rec", description=None, datecode=None, var_list=[_var("Count", "integer")])
    bp = _base_picture()
    bp.datatype_defs = [own]
    bp.localvariables = [_var("Holder", "Rec"), _var("Sink", "integer")]
    bp.modulecode = ModuleCode(equationblocks=[_equation(Assignment(VarRef("Sink"), VarRef("Holder.Missing")))])

    diagnostics = validate_basepicture(bp, external_datatypes=[external])

    assert [d.code.value for d in diagnostics] == ["SL-V019"]
    assert "Holder.Missing" in diagnostics[0].message
