"""Tests for the validation type graph and type helpers."""

from __future__ import annotations

from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    FloatLiteral,
    InitValue,
    IntLiteral,
    ModuleHeader,
    ParameterMapping,
    Simple_DataType,
    Variable,
)
from sattline_parser.models.expressions import (
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    NotOp,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.names import fold_identifier
from sattline_parser.validation.diagnostics import Diagnostic
from sattline_parser.validation.parameter_mappings import check_parameter_mappings
from sattline_parser.validation.symbols import build_scope
from sattline_parser.validation.type_graph import TypeGraph
from sattline_parser.validation.typing import (
    assignment_type_matches,
    builtin_type_matches,
    expression_is_zero_literal,
    extract_time_literal,
    format_datatype,
    has_time_literal_marker,
    infer_expression_datatype,
    infer_literal_datatype,
    is_anytype_datatype,
    is_boolean_datatype,
    is_numeric_datatype,
    is_string_simple_type,
    is_valid_duration_literal,
    is_valid_time_literal,
    literal_matches_expected_datatype,
    merge_compatible_types,
    merge_numeric_types,
    normalize_builtin_datatype,
    resolve_ref_datatype,
    resolve_variable_field_datatype,
    split_dotted_name,
    suggest_datatype_name,
)


def _var(name: str, datatype: Simple_DataType | str, *, state: bool | None = False) -> Variable:
    return Variable(name=name, datatype=datatype, state=state)


def _record(name: str, *fields: Variable) -> DataType:
    return DataType(name=name, description=None, datecode=None, var_list=list(fields))


def _graph() -> TypeGraph:
    inner = _record("Inner", _var("Value", "real"), _var("Flag", "boolean", state=True))
    outer = _record("Outer", _var("Part", "Inner"), _var("Count", "integer"))
    return TypeGraph.from_datatypes([inner, outer])


# --- type graph ---------------------------------------------------------------


def test_type_graph_resolves_records_and_fields() -> None:
    graph = _graph()
    assert graph.has_record("Outer") is True
    assert graph.has_record("Missing") is False
    record = graph.record("outer")
    assert record is not None and record.name == "Outer"
    assert graph.record("Missing") is None
    field = graph.field("Outer", "count")
    assert field is not None and field.datatype == Simple_DataType.INTEGER
    assert graph.field("Outer", "Missing") is None
    assert graph.field("Missing", "Count") is None
    assert graph.field_type("Outer", "Count") == Simple_DataType.INTEGER
    assert graph.field_type("Outer", "Missing") is None


def test_type_graph_includes_builtin_records() -> None:
    graph = _graph()
    assert graph.has_record("BooleanSignal") is True
    field = graph.field("BooleanSignal", "Value")
    assert field is not None and field.datatype == Simple_DataType.BOOLEAN


def test_type_graph_leaf_paths_for_simple_and_record_types() -> None:
    graph = _graph()
    assert list(graph.iter_leaf_field_paths(Simple_DataType.INTEGER)) == [()]
    assert set(graph.iter_leaf_field_paths("Outer")) == {
        ("Part", "Value"),
        ("Part", "Flag"),
        ("Count",),
    }


def test_type_graph_leaf_paths_for_unknown_empty_and_cyclic_types() -> None:
    graph = TypeGraph.from_datatypes(
        [
            _record("Empty"),
            _record("CycleA", _var("Next", "CycleB")),
            _record("CycleB", _var("Next", "CycleA")),
        ]
    )
    assert list(graph.iter_leaf_field_paths("Unknown")) == [()]
    assert list(graph.iter_leaf_field_paths("Empty")) == [()]
    assert set(graph.iter_leaf_field_paths("CycleA")) == {("Next", "Next")}


def test_type_graph_all_addressable_paths() -> None:
    graph = _graph()
    assert set(graph.iter_all_addressable_paths(_var("Root", "Outer"))) == {
        ("Part", "Value"),
        ("Part", "Flag"),
        ("Count",),
    }


def test_type_graph_field_state_is_preserved() -> None:
    graph = _graph()
    field = graph.field("Inner", "Flag")
    assert field is not None and field.state is True


# --- datatype predicates ------------------------------------------------------


def test_datatype_predicates_accept_names_and_enum_members() -> None:
    assert is_numeric_datatype("integer") is True
    assert is_numeric_datatype(Simple_DataType.REAL) is True
    assert is_numeric_datatype("boolean") is False
    assert is_numeric_datatype(None) is False
    assert is_boolean_datatype("boolean") is True
    assert is_boolean_datatype("integer") is False
    assert is_string_simple_type("tagstring") is True
    assert is_string_simple_type("integer") is False
    assert is_string_simple_type("MyRecord") is False


def test_format_datatype() -> None:
    assert format_datatype(None) == "unknown"
    assert format_datatype(Simple_DataType.INTEGER) == "integer"
    assert format_datatype("MyRecord") == "MyRecord"


def test_normalize_builtin_datatype() -> None:
    assert normalize_builtin_datatype("integer") is Simple_DataType.INTEGER
    assert normalize_builtin_datatype("MyRecord") == "MyRecord"


def test_split_dotted_name() -> None:
    assert split_dotted_name("A.B.C") == ("A", ("B", "C"))
    assert split_dotted_name("A") == ("A", ())
    assert split_dotted_name("") == ("", ())


def test_resolve_variable_field_datatype() -> None:
    graph = _graph()
    variable = _var("Root", "Outer")
    assert resolve_variable_field_datatype(variable, (), graph) == "Outer"
    assert resolve_variable_field_datatype(variable, ("Count",), graph) == Simple_DataType.INTEGER
    assert resolve_variable_field_datatype(variable, ("Part", "Value"), graph) == Simple_DataType.REAL
    assert resolve_variable_field_datatype(variable, ("Missing",), graph) is None
    assert resolve_variable_field_datatype(variable, ("Count", "X"), graph) is None


def test_resolve_ref_datatype() -> None:
    graph = _graph()
    scope = build_scope(None, [_var("Root", "Outer")])
    assert resolve_ref_datatype(VarRef("Root.Count"), scope, graph) == Simple_DataType.INTEGER
    assert resolve_ref_datatype(VarRef("Root.Missing"), scope, graph) is None
    assert resolve_ref_datatype(VarRef("Missing"), scope, graph) is None
    assert resolve_ref_datatype(VarRef(""), scope, graph) is None


# --- literals -----------------------------------------------------------------


def test_is_valid_duration_literal() -> None:
    assert is_valid_duration_literal("5") is True
    assert is_valid_duration_literal("-2.5") is True
    assert is_valid_duration_literal("1h30m") is True
    assert is_valid_duration_literal("250ms") is True
    assert is_valid_duration_literal("") is False
    assert is_valid_duration_literal("-") is False
    assert is_valid_duration_literal("abc") is False
    assert is_valid_duration_literal(5) is False


def test_time_literal_helpers() -> None:
    literal = {"Time_Value": "2026-01-01-00:00:00.000"}
    assert has_time_literal_marker(literal) is True
    assert has_time_literal_marker("x") is False
    assert extract_time_literal(literal) == "2026-01-01-00:00:00.000"
    assert extract_time_literal("x") is None
    assert extract_time_literal({"Time_Value": 5}) is None
    assert is_valid_time_literal("2026-01-01-00:00:00.000") is True
    assert is_valid_time_literal("2026-01-01") is False
    assert is_valid_time_literal(5) is False


def test_infer_literal_datatype() -> None:
    assert infer_literal_datatype(True) is Simple_DataType.BOOLEAN
    assert infer_literal_datatype(IntLiteral(3)) is Simple_DataType.INTEGER
    assert infer_literal_datatype(FloatLiteral(3.5)) is Simple_DataType.REAL
    assert infer_literal_datatype("1h", is_duration=True) is Simple_DataType.DURATION
    assert infer_literal_datatype("text") is Simple_DataType.STRING
    assert infer_literal_datatype({"Time_Value": "2026-01-01-00:00:00.000"}) == "Time_Value"
    assert infer_literal_datatype(object()) is None


def test_literal_matches_expected_datatype() -> None:
    assert literal_matches_expected_datatype(True, Simple_DataType.BOOLEAN) is True
    assert literal_matches_expected_datatype("1h", Simple_DataType.DURATION, is_duration=True) is True
    assert literal_matches_expected_datatype("1h", Simple_DataType.DURATION) is True
    assert literal_matches_expected_datatype("2026-01-01-00:00:00.000", Simple_DataType.TIME) is True
    assert literal_matches_expected_datatype({"Time_Value": "bad"}, Simple_DataType.TIME) is False
    assert literal_matches_expected_datatype(1, Simple_DataType.STRING) is False


def test_literal_matches_duration_and_time_by_datatype_name() -> None:
    assert literal_matches_expected_datatype("2h", "duration") is True
    assert literal_matches_expected_datatype("2026-01-01-00:00:00.000", "time") is True
    assert literal_matches_expected_datatype("2h", "MyRecord") is False


# --- compatibility ------------------------------------------------------------


def test_builtin_type_matches() -> None:
    assert builtin_type_matches("integer", "integer", direction="in") is True
    assert builtin_type_matches("integer", "real", direction="in") is True
    assert builtin_type_matches("integer", "real", direction="out") is False
    assert builtin_type_matches("identstring", "tagstring", direction="in") is True
    assert builtin_type_matches("MyRecord", "MyRecord", direction="in") is True
    assert builtin_type_matches("MyRecord", "Other", direction="in") is False
    assert builtin_type_matches("integer", "anytype", direction="in") is True
    assert builtin_type_matches("MyRecord", Simple_DataType.INTEGER, direction="in") is False
    assert builtin_type_matches("textfile", "tObject", direction="in") is True
    assert builtin_type_matches("MyRecord", "tObject", direction="in") is True
    # a scalar is not an object handle, so it stays a mismatch
    assert builtin_type_matches("integer", "tObject", direction="in") is False
    assert builtin_type_matches("real", "tObject", direction="in") is False
    assert builtin_type_matches("integer", "AsyncOperation", direction="inout") is True
    assert builtin_type_matches("real", "AsyncOperation", direction="inout") is False


def test_assignment_type_matches() -> None:
    assert assignment_type_matches(None, "integer") is True
    assert assignment_type_matches("integer", None) is True
    assert assignment_type_matches("anytype", "integer") is True
    assert assignment_type_matches("integer", "anytype") is True
    assert assignment_type_matches("real", "integer") is True
    assert assignment_type_matches("integer", "real") is True
    assert assignment_type_matches("Time_Value", "time") is True
    assert assignment_type_matches("Time_Value", "duration") is True
    assert assignment_type_matches("Time_Value", "integer") is False
    assert assignment_type_matches("MyRecord", "MyRecord") is True
    assert assignment_type_matches("MyRecord", "Other") is False
    assert assignment_type_matches("MyRecord", Simple_DataType.INTEGER) is False


def test_merge_numeric_and_compatible_types() -> None:
    assert merge_numeric_types(("integer", "real")) is Simple_DataType.REAL
    assert merge_numeric_types(("integer", "integer")) is Simple_DataType.INTEGER
    assert merge_numeric_types(("integer", "boolean")) is None
    assert merge_numeric_types(()) is None
    assert merge_compatible_types(()) is None
    assert merge_compatible_types(("integer", "integer")) == Simple_DataType.INTEGER
    assert merge_compatible_types(("integer", "real")) is Simple_DataType.REAL
    assert merge_compatible_types(("identstring", "tagstring")) is Simple_DataType.STRING
    assert merge_compatible_types(("integer", "boolean")) is None


def test_expression_is_zero_literal() -> None:
    assert expression_is_zero_literal(0) is True
    assert expression_is_zero_literal(0.0) is True
    assert expression_is_zero_literal(1) is False
    assert expression_is_zero_literal(UnaryOp("-", 0)) is True
    assert expression_is_zero_literal(UnaryOp("-", 1)) is False
    assert expression_is_zero_literal("0") is False


# --- expression inference -----------------------------------------------------


def test_infer_expression_datatype_primitives_and_refs() -> None:
    graph = _graph()
    scope = build_scope(None, [_var("Root", "Outer"), _var("Flag", "boolean")])
    assert infer_expression_datatype(True, scope, graph) is Simple_DataType.BOOLEAN
    assert infer_expression_datatype(IntLiteral(1), scope, graph) is Simple_DataType.INTEGER
    assert infer_expression_datatype(FloatLiteral(1.5), scope, graph) is Simple_DataType.REAL
    assert infer_expression_datatype("text", scope, graph) is Simple_DataType.STRING
    assert infer_expression_datatype(VarRef("Flag"), scope, graph) is Simple_DataType.BOOLEAN
    assert infer_expression_datatype(VarRef("On"), scope, graph) is Simple_DataType.BOOLEAN
    assert infer_expression_datatype(VarRef("Missing"), scope, graph) is None


def test_infer_expression_datatype_operators() -> None:
    graph = _graph()
    scope = build_scope(None, [_var("Count", "integer"), _var("Rate", "real")])
    assert (
        infer_expression_datatype(Compare(VarRef("Count"), "==", VarRef("Count")), scope, graph)
        is Simple_DataType.BOOLEAN
    )
    assert infer_expression_datatype(BoolOp("AND", (True, False)), scope, graph) is Simple_DataType.BOOLEAN
    assert infer_expression_datatype(NotOp(True), scope, graph) is Simple_DataType.BOOLEAN
    assert infer_expression_datatype(BinOp(VarRef("Count"), "+", VarRef("Rate")), scope, graph) is Simple_DataType.REAL
    assert infer_expression_datatype(UnaryOp("-", VarRef("Count")), scope, graph) is Simple_DataType.INTEGER
    ternary = TernaryOp(branches=((True, VarRef("Count")),), else_expr=VarRef("Rate"))
    assert infer_expression_datatype(ternary, scope, graph) is Simple_DataType.REAL
    empty_ternary = TernaryOp(branches=(), else_expr=None)
    assert infer_expression_datatype(empty_ternary, scope, graph) is None


def test_infer_expression_datatype_builtin_calls() -> None:
    graph = _graph()
    scope = build_scope(None, [])
    assert infer_expression_datatype(FuncCall("StringLength", (VarRef("X"),)), scope, graph) is Simple_DataType.INTEGER
    assert infer_expression_datatype(FuncCall("ResetPrivilegeFlag", ()), scope, graph) is None
    assert infer_expression_datatype(FuncCall("UserProc", ()), scope, graph) is None
    assert infer_expression_datatype(object(), scope, graph) is None


def test_is_anytype_datatype() -> None:
    assert is_anytype_datatype("anytype") is True
    assert is_anytype_datatype("AnyType") is True
    assert is_anytype_datatype("integer") is False
    assert is_anytype_datatype(None) is False


def test_suggest_datatype_name() -> None:
    assert suggest_datatype_name("intege", ["integer", "real"]) == "integer"
    assert suggest_datatype_name("SensorType", ["integer", "real"]) is None
    assert suggest_datatype_name("timer", ["time"]) is None
    assert suggest_datatype_name("intege", []) is None


# --- parameter mappings -------------------------------------------------------


def _mapping(
    target: str,
    *,
    source: str | None = None,
    literal: InitValue | None = None,
    is_duration: bool = False,
    is_global: bool = False,
) -> ParameterMapping:
    return ParameterMapping(
        target=VarRef(target),
        source_type="value",
        is_duration=is_duration,
        is_source_global=is_global,
        source=VarRef(source) if source else None,
        source_literal=literal,
    )


def _codes(errors: list[Diagnostic]) -> list[str]:
    return [error.code.value for error in errors]


def test_parameter_mapping_duplicate_target() -> None:
    graph = _graph()
    expected = {fold_identifier("Flag"): _var("Flag", "boolean")}
    errors: list[Diagnostic] = []
    check_parameter_mappings([_mapping("Flag"), _mapping("flag")], expected, build_scope(None, []), graph, errors)
    assert _codes(errors) == ["SL-V049"]


def test_parameter_mapping_field_access_on_non_record() -> None:
    graph = _graph()
    expected = {fold_identifier("Flag"): _var("Flag", "boolean")}
    errors: list[Diagnostic] = []
    check_parameter_mappings([_mapping("Flag.Sub")], expected, build_scope(None, []), graph, errors)
    assert _codes(errors) == ["SL-V048"]


def test_parameter_mapping_unknown_field_on_record() -> None:
    graph = _graph()
    expected = {fold_identifier("Root"): _var("Root", "Outer")}
    errors: list[Diagnostic] = []
    check_parameter_mappings([_mapping("Root.Missing")], expected, build_scope(None, []), graph, errors)
    assert _codes(errors) == ["SL-V048"]


def test_parameter_mapping_unknown_field_on_external_record_is_silent() -> None:
    graph = _graph()
    expected = {fold_identifier("Ext"): _var("Ext", "ExternalRecord")}
    errors: list[Diagnostic] = []
    check_parameter_mappings([_mapping("Ext.Missing")], expected, build_scope(None, []), graph, errors)
    assert errors == []


def test_parameter_mapping_unknown_target_and_missing_expected_are_silent() -> None:
    graph = _graph()
    errors: list[Diagnostic] = []
    check_parameter_mappings(
        [_mapping("Missing")], {fold_identifier("Flag"): _var("Flag", "boolean")}, build_scope(None, []), graph, errors
    )
    check_parameter_mappings([_mapping("Flag")], None, build_scope(None, []), graph, errors)
    assert errors == []


def test_parameter_mapping_literal_matches_and_mismatches() -> None:
    graph = _graph()
    expected = {fold_identifier("Count"): _var("Count", "integer")}
    errors: list[Diagnostic] = []
    check_parameter_mappings([_mapping("Count", literal=3)], expected, build_scope(None, []), graph, errors)
    assert errors == []
    check_parameter_mappings([_mapping("Count", literal="text")], expected, build_scope(None, []), graph, errors)
    assert _codes(errors) == ["SL-V050"]


def test_parameter_mapping_invalid_duration_and_time_literals() -> None:
    graph = _graph()
    expected = {fold_identifier("Dur"): _var("Dur", "duration"), fold_identifier("Stamp"): _var("Stamp", "time")}
    errors: list[Diagnostic] = []
    check_parameter_mappings(
        [_mapping("Dur", literal="not-a-duration", is_duration=True)], expected, build_scope(None, []), graph, errors
    )
    check_parameter_mappings(
        [_mapping("Stamp", literal={"Time_Value": "bad"})], expected, build_scope(None, []), graph, errors
    )
    assert _codes(errors) == ["SL-V050", "SL-V050"]


def test_parameter_mapping_global_and_variable_sources_are_skipped() -> None:
    graph = _graph()
    expected = {fold_identifier("Count"): _var("Count", "integer")}
    errors: list[Diagnostic] = []
    check_parameter_mappings(
        [_mapping("Count", source="Rate", is_global=True)], expected, build_scope(None, []), graph, errors
    )
    check_parameter_mappings(
        [_mapping("Count", source="Rate")], expected, build_scope(None, [_var("Rate", "real")]), graph, errors
    )
    assert errors == []


def test_parameter_mapping_duration_literal_uses_is_duration() -> None:
    graph = _graph()
    expected = {fold_identifier("Dur"): _var("Dur", "duration")}
    errors: list[Diagnostic] = []
    check_parameter_mappings(
        [_mapping("Dur", literal="1h", is_duration=True)], expected, build_scope(None, []), graph, errors
    )
    assert errors == []


def test_type_graph_from_basepicture() -> None:
    bp = BasePicture(header=ModuleHeader(name="BasePicture", invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0)))
    bp.datatype_defs = [_record("Rec", _var("Count", "integer"))]
    graph = TypeGraph.from_basepicture(bp)
    assert graph.has_record("Rec") is True


def test_suggest_datatype_name_exact_match_returns_none() -> None:
    assert suggest_datatype_name("integer", ["integer"]) is None
