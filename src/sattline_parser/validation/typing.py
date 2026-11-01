"""Scalar type rules, literal inference, and expression typing.

An expression is rejected when the *static* type of an operand is wrong, before
any value is computed. This module owns the type facts the rules share:

* primitive families (numeric, boolean, string, temporal);
* literal inference, including duration and time literals;
* record field resolution through a :class:`~sattline_parser.validation.type_graph.TypeGraph`;
* assignment, builtin-argument, and branch compatibility;
* a bounded edit-distance suggestion for datatype names.

Only rules that are established live here. :func:`infer_expression_datatype`
returns ``None`` for anything it cannot determine, and every caller skips
``None``. Silence means unknown, never legal.
"""

from __future__ import annotations

import re
from collections.abc import Sequence as AbcSequence
from enum import StrEnum
from typing import Protocol, cast

from sattline_parser.builtins.functions import get_function_signature
from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    DataType,
    FloatLiteral,
    IntLiteral,
    Simple_DataType,
    Variable,
)
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    NotOp,
    SLExpression,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.validation.names import fold_identifier
from sattline_parser.validation.symbols import Scope, is_sfc_runtime_constant, resolve_var
from sattline_parser.validation.type_graph import TypeGraph


class TypeFamily(StrEnum):
    """Coarse type classes the rules group primitives into."""

    NUMERIC = "numeric"
    BOOLEAN = "boolean"
    STRING = "string"
    TEMPORAL = "temporal"


#: Primitive -> family. Derived from :class:`Simple_DataType` so a future
#: primitive cannot be silently forgotten; anything absent maps to ``None``.
_FAMILIES: dict[Simple_DataType, TypeFamily] = {
    Simple_DataType.INTEGER: TypeFamily.NUMERIC,
    Simple_DataType.REAL: TypeFamily.NUMERIC,
    Simple_DataType.BOOLEAN: TypeFamily.BOOLEAN,
    Simple_DataType.STRING: TypeFamily.STRING,
    Simple_DataType.IDENTSTRING: TypeFamily.STRING,
    Simple_DataType.TAGSTRING: TypeFamily.STRING,
    Simple_DataType.MAXSTRING: TypeFamily.STRING,
    Simple_DataType.LINESTRING: TypeFamily.STRING,
    Simple_DataType.TIME: TypeFamily.TEMPORAL,
    Simple_DataType.DURATION: TypeFamily.TEMPORAL,
}

_STRING_SIMPLE_TYPES: frozenset[Simple_DataType] = frozenset(
    {
        Simple_DataType.IDENTSTRING,
        Simple_DataType.TAGSTRING,
        Simple_DataType.STRING,
        Simple_DataType.LINESTRING,
        Simple_DataType.MAXSTRING,
    }
)

_ANYTYPE = fold_identifier("anytype")

_PLAIN_DURATION_LITERAL_RE = re.compile(r"\d+(?:\.\d+)?")
_DURATION_COMPONENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d+d", re.IGNORECASE),
    re.compile(r"\d+h", re.IGNORECASE),
    re.compile(r"\d+m(?!s)", re.IGNORECASE),
    re.compile(r"\d+(?:\.\d+)?s", re.IGNORECASE),
    re.compile(r"\d+ms", re.IGNORECASE),
)
_TIME_LITERAL_RE = re.compile(r"\d{4}-\d{2}-\d{2}-\d{2}:\d{2}:\d{2}\.\d{3}")
_TYPO_SUGGESTION_MAX_DISTANCE = 2


def datatype_family(datatype: Simple_DataType | str) -> TypeFamily | None:
    """Family of a resolved datatype name, or ``None`` for records/unknowns."""
    try:
        member = Simple_DataType.from_any(datatype)
    except ValueError:
        return None
    return _FAMILIES.get(member)


def family_of(datatype: Simple_DataType | str | None) -> TypeFamily | None:
    return None if datatype is None else datatype_family(datatype)


def is_numeric(datatype: Simple_DataType | str) -> bool:
    return datatype_family(datatype) is TypeFamily.NUMERIC


def is_boolean(datatype: Simple_DataType | str) -> bool:
    return datatype_family(datatype) is TypeFamily.BOOLEAN


def _normalize(datatype: Simple_DataType | str | None) -> Simple_DataType | str | None:
    if datatype is None or isinstance(datatype, Simple_DataType):
        return datatype
    return normalize_builtin_datatype(datatype)


def is_numeric_datatype(datatype: Simple_DataType | str | None) -> bool:
    normalized = _normalize(datatype)
    return normalized in {Simple_DataType.INTEGER, Simple_DataType.REAL}


def is_boolean_datatype(datatype: Simple_DataType | str | None) -> bool:
    return _normalize(datatype) == Simple_DataType.BOOLEAN


def is_string_simple_type(datatype: Simple_DataType | str | None) -> bool:
    normalized = _normalize(datatype)
    return isinstance(normalized, Simple_DataType) and normalized in _STRING_SIMPLE_TYPES


def is_anytype_datatype(datatype: Simple_DataType | str | None) -> bool:
    return datatype is not None and fold_identifier(format_datatype(datatype)) == _ANYTYPE


def normalize_builtin_datatype(datatype: str) -> Simple_DataType | str:
    try:
        return Simple_DataType.from_any(datatype)
    except ValueError:
        return datatype


def format_datatype(datatype: Simple_DataType | str | None) -> str:
    if datatype is None:
        return "unknown"
    if isinstance(datatype, Simple_DataType):
        return datatype.value
    return str(datatype)


def split_dotted_name(name: str) -> tuple[str, tuple[str, ...]]:
    parts = tuple(part for part in str(name).split(".") if part)
    if not parts:
        return "", ()
    return parts[0], parts[1:]


class FieldSpec(Protocol):
    """Structural view of one record field, for graph implementations."""

    @property
    def datatype(self) -> Simple_DataType | str: ...


class FieldGraph(Protocol):
    """Structural view of a record field graph."""

    def field(self, record_type: str, field_name: str) -> FieldSpec | None: ...


def resolve_variable_field_datatype(
    variable: Variable,
    field_path: tuple[str, ...],
    type_graph: FieldGraph,
) -> Simple_DataType | str | None:
    current: Simple_DataType | str = variable.datatype
    for field_name in field_path:
        if isinstance(current, Simple_DataType):
            return None
        field = type_graph.field(str(current), field_name)
        if field is None:
            return None
        current = field.datatype
    return current


def resolve_ref_datatype(
    ref: VarRef,
    scope: Scope,
    type_graph: FieldGraph,
) -> Simple_DataType | str | None:
    base_name, field_path = split_dotted_name(ref.name)
    if not base_name:
        return None
    variable = scope.lookup(base_name)
    if variable is None:
        return None
    return resolve_variable_field_datatype(variable, field_path, type_graph)


def is_valid_duration_literal(value: object) -> bool:
    if not isinstance(value, str):
        return False

    text = value.strip()
    if not text:
        return False

    if text[0] in "+-":
        text = text[1:]
    if not text:
        return False

    if _PLAIN_DURATION_LITERAL_RE.fullmatch(text):
        return True

    position = 0
    matched_component = False
    for pattern in _DURATION_COMPONENT_PATTERNS:
        match = pattern.match(text, position)
        if match is None:
            continue
        matched_component = True
        position = match.end()

    return matched_component and position == len(text)


def has_time_literal_marker(value: object) -> bool:
    return isinstance(value, dict) and const.GRAMMAR_VALUE_TIME_VALUE in value


def extract_time_literal(value: object) -> str | None:
    if not isinstance(value, dict) or const.GRAMMAR_VALUE_TIME_VALUE not in value:
        return None
    mapping = cast("dict[str, object]", value)
    literal = mapping.get(const.GRAMMAR_VALUE_TIME_VALUE)
    return literal if isinstance(literal, str) else None


def is_valid_time_literal(value: object) -> bool:
    return isinstance(value, str) and _TIME_LITERAL_RE.fullmatch(value.strip()) is not None


def infer_literal_datatype(value: object, *, is_duration: bool = False) -> Simple_DataType | str | None:
    if isinstance(value, bool):
        return Simple_DataType.BOOLEAN
    if isinstance(value, IntLiteral | int) and not isinstance(value, bool):
        return Simple_DataType.INTEGER
    if isinstance(value, FloatLiteral | float):
        return Simple_DataType.REAL
    if is_duration and isinstance(value, str) and is_valid_duration_literal(value):
        return Simple_DataType.DURATION
    if isinstance(value, str):
        return Simple_DataType.STRING
    if has_time_literal_marker(value):
        return const.GRAMMAR_VALUE_TIME_VALUE
    return None


def literal_matches_expected_datatype(
    literal: object,
    expected: Simple_DataType | str | None,
    *,
    is_duration: bool = False,
) -> bool:
    if has_time_literal_marker(literal) and not is_valid_time_literal(extract_time_literal(literal)):
        return False

    actual = infer_literal_datatype(literal, is_duration=is_duration)
    if assignment_type_matches(actual, expected):
        return True

    return (isinstance(literal, str) and _is_duration_datatype(expected) and is_valid_duration_literal(literal)) or (
        isinstance(literal, str) and _is_time_datatype(expected) and is_valid_time_literal(literal)
    )


def _is_duration_datatype(datatype: Simple_DataType | str | None) -> bool:
    if isinstance(datatype, Simple_DataType):
        return datatype == Simple_DataType.DURATION
    return isinstance(datatype, str) and fold_identifier(datatype) == fold_identifier(Simple_DataType.DURATION.value)


def _is_time_datatype(datatype: Simple_DataType | str | None) -> bool:
    if isinstance(datatype, Simple_DataType):
        return datatype == Simple_DataType.TIME
    return isinstance(datatype, str) and fold_identifier(datatype) == fold_identifier(Simple_DataType.TIME.value)


def builtin_type_matches(
    actual: Simple_DataType | str,
    expected: Simple_DataType | str,
    *,
    direction: str,
) -> bool:
    normalized_actual = _normalize(actual)
    normalized_expected = _normalize(expected)
    if is_anytype_datatype(normalized_expected):
        return True
    expected_name = fold_identifier(format_datatype(normalized_expected))
    if expected_name == "TOBJECT":
        # tObject is the documented opaque base object; file handles and other
        # builtin objects are passed where a tObject parameter is declared.
        return True
    if expected_name == "ASYNCOPERATION" and normalized_actual == Simple_DataType.INTEGER:
        # The asynchronous-operation handle is integer-backed in source code.
        return True

    if isinstance(normalized_expected, Simple_DataType):
        if not isinstance(normalized_actual, Simple_DataType):
            return False
        if normalized_actual == normalized_expected:
            return True
        if is_string_simple_type(normalized_actual) and is_string_simple_type(normalized_expected):
            return True
        return bool(
            direction == "in"
            and normalized_expected == Simple_DataType.REAL
            and normalized_actual == Simple_DataType.INTEGER
        )

    return fold_identifier(format_datatype(normalized_actual)) == fold_identifier(format_datatype(normalized_expected))


def assignment_type_matches(
    actual: Simple_DataType | str | None,
    expected: Simple_DataType | str | None,
) -> bool:
    normalized_actual = _normalize(actual)
    normalized_expected = _normalize(expected)
    if normalized_actual is None or normalized_expected is None:
        return True
    if is_anytype_datatype(normalized_actual) or is_anytype_datatype(normalized_expected):
        return True
    if is_numeric_datatype(normalized_actual) and is_numeric_datatype(normalized_expected):
        # The parser accepts both numeric directions: a narrowing real into
        # integer is not rejected because no such assignment is established.
        return True
    if normalized_actual == const.GRAMMAR_VALUE_TIME_VALUE:
        return normalized_expected in {Simple_DataType.TIME, Simple_DataType.DURATION}
    if isinstance(normalized_expected, Simple_DataType):
        if not isinstance(normalized_actual, Simple_DataType):
            return False
        return builtin_type_matches(normalized_actual, normalized_expected, direction="in")
    if isinstance(normalized_actual, Simple_DataType):
        return False
    return fold_identifier(format_datatype(normalized_actual)) == fold_identifier(format_datatype(normalized_expected))


def merge_numeric_types(datatypes: AbcSequence[Simple_DataType | str | None]) -> Simple_DataType | None:
    numeric_types = {Simple_DataType.INTEGER, Simple_DataType.REAL}
    normalized = [_normalize(datatype) for datatype in datatypes]
    if not normalized or any(datatype not in numeric_types for datatype in normalized):
        return None
    return Simple_DataType.REAL if Simple_DataType.REAL in normalized else Simple_DataType.INTEGER


def merge_compatible_types(
    datatypes: AbcSequence[Simple_DataType | str | None],
) -> Simple_DataType | str | None:
    filtered = [_normalize(datatype) for datatype in datatypes if datatype is not None]
    if not filtered:
        return None

    first = filtered[0]
    if all(datatype == first for datatype in filtered[1:]):
        return first

    numeric = merge_numeric_types(filtered)
    if numeric is not None:
        return numeric

    if all(is_string_simple_type(datatype) for datatype in filtered):
        return Simple_DataType.STRING

    return None


def expression_is_zero_literal(node: object) -> bool:
    if isinstance(node, IntLiteral | int) and not isinstance(node, bool):
        return int(node) == 0
    if isinstance(node, FloatLiteral | float):
        return float(node) == 0.0
    if isinstance(node, UnaryOp) and node.op in {const.KEY_PLUS, const.KEY_MINUS, "+", "-"}:
        return expression_is_zero_literal(node.operand)
    return False


def infer_expression_datatype(
    expr: object,
    scope: Scope,
    type_graph: TypeGraph,
) -> Simple_DataType | str | None:
    """Static datatype of an expression node, or ``None`` when unproven."""
    if isinstance(expr, bool):
        return Simple_DataType.BOOLEAN
    if isinstance(expr, IntLiteral | int) and not isinstance(expr, bool):
        return Simple_DataType.INTEGER
    if isinstance(expr, FloatLiteral | float):
        return Simple_DataType.REAL
    if isinstance(expr, str):
        return Simple_DataType.STRING
    if isinstance(expr, VarRef):
        resolved = resolve_ref_datatype(expr, scope, type_graph)
        if resolved is None and is_sfc_runtime_constant(expr.name):
            return Simple_DataType.BOOLEAN
        return resolved
    if isinstance(expr, Compare | BoolOp | NotOp):
        return Simple_DataType.BOOLEAN
    if isinstance(expr, BinOp):
        return merge_numeric_types(
            [
                infer_expression_datatype(expr.left, scope, type_graph),
                infer_expression_datatype(expr.right, scope, type_graph),
            ]
        )
    if isinstance(expr, UnaryOp):
        return merge_numeric_types([infer_expression_datatype(expr.operand, scope, type_graph)])
    if isinstance(expr, TernaryOp):
        branch_types = [infer_expression_datatype(value, scope, type_graph) for _condition, value in expr.branches]
        if expr.else_expr is not None:
            branch_types.append(infer_expression_datatype(expr.else_expr, scope, type_graph))
        return merge_compatible_types(branch_types)
    if isinstance(expr, FuncCall):
        signature = get_function_signature(expr.name)
        if signature is None or signature.return_type is None:
            return None
        return normalize_builtin_datatype(signature.return_type)
    return None


def infer_expr_type(
    expr: SLExpression,
    scope: Scope,
    records: dict[str, DataType],
    type_graph: TypeGraph | None = None,
) -> str | None:
    """Compatibility wrapper: the inferred datatype as a string, or ``None``."""
    graph = type_graph if type_graph is not None else TypeGraph.from_datatypes(records.values())
    inferred = infer_expression_datatype(expr, scope, graph)
    return None if inferred is None else format_datatype(inferred)


def assignment_is_compatible(source_type: str, target_type: str) -> bool:
    """Whether ``target = source`` is legal under the family-level rule.

    Kept as the coarse predicate used by the first-generation validator.
    New rules use :func:`assignment_type_matches`, which also handles records,
    AnyType, and time literals.
    """
    source_family = datatype_family(source_type)
    target_family = datatype_family(target_type)
    if source_family is None or target_family is None:
        return True
    return source_family is target_family


def operand_types(
    expr: Compare | BinOp,
    scope: Scope,
    records: dict[str, DataType],
    type_graph: TypeGraph | None = None,
) -> tuple[str | None, str | None]:
    """Static types of a binary operator's two operands."""
    return (
        infer_expr_type(expr.left, scope, records, type_graph),
        infer_expr_type(expr.right, scope, records, type_graph),
    )


def assignment_types(
    assignment: Assignment,
    scope: Scope,
    records: dict[str, DataType],
    type_graph: TypeGraph | None = None,
) -> tuple[str | None, str | None]:
    """(target type, source type) for an assignment, either side may be ``None``."""
    target = resolve_var(assignment.target, scope, records)
    source = infer_expr_type(assignment.value, scope, records, type_graph)
    return (None if target is None else target.datatype_text), source


def _bounded_levenshtein(left: str, right: str, *, max_distance: int = _TYPO_SUGGESTION_MAX_DISTANCE) -> int | None:
    left_folded = fold_identifier(left)
    right_folded = fold_identifier(right)

    if left_folded == right_folded:
        return 0
    if abs(len(left_folded) - len(right_folded)) > max_distance:
        return None

    previous = list(range(len(right_folded) + 1))
    for row_index, left_char in enumerate(left_folded, start=1):
        current = [row_index]
        row_min = current[0]
        for col_index, right_char in enumerate(right_folded, start=1):
            cost = 0 if left_char == right_char else 1
            current_value = min(
                previous[col_index] + 1,
                current[col_index - 1] + 1,
                previous[col_index - 1] + cost,
            )
            current.append(current_value)
            row_min = min(row_min, current_value)
        if row_min > max_distance:
            return None
        previous = current

    distance = previous[-1]
    return distance if distance <= max_distance else None


def suggest_datatype_name(name: str, known_datatypes: AbcSequence[str]) -> str | None:
    """Return the closest known datatype name within a bounded edit distance.

    Candidates that are a strict prefix of the unknown name are skipped: such
    names extend the candidate (``Timer`` extends ``time``) rather than
    misspelling it.
    """
    best_match: str | None = None
    best_distance: int | None = None
    name_folded = fold_identifier(name)
    for candidate in known_datatypes:
        distance = _bounded_levenshtein(name, candidate, max_distance=_TYPO_SUGGESTION_MAX_DISTANCE)
        if distance is None:
            continue
        candidate_folded = fold_identifier(candidate)
        if name_folded.startswith(candidate_folded):
            continue
        if best_distance is None or distance < best_distance:
            best_match = candidate
            best_distance = distance
    return best_match


__all__ = [
    "TypeFamily",
    "assignment_is_compatible",
    "assignment_type_matches",
    "assignment_types",
    "builtin_type_matches",
    "datatype_family",
    "expression_is_zero_literal",
    "extract_time_literal",
    "family_of",
    "format_datatype",
    "has_time_literal_marker",
    "infer_expr_type",
    "infer_expression_datatype",
    "infer_literal_datatype",
    "is_anytype_datatype",
    "is_boolean",
    "is_boolean_datatype",
    "is_numeric",
    "is_numeric_datatype",
    "is_string_simple_type",
    "is_valid_duration_literal",
    "is_valid_time_literal",
    "literal_matches_expected_datatype",
    "merge_compatible_types",
    "merge_numeric_types",
    "normalize_builtin_datatype",
    "operand_types",
    "resolve_ref_datatype",
    "resolve_variable_field_datatype",
    "split_dotted_name",
    "suggest_datatype_name",
]
