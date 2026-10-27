"""Static type inference and operand-compatibility rules for expressions.

The real SattLine validator rejects an expression when the *static* type of an
operand is wrong, before any value is computed. Probes run 2026-10-01 pinned
three such rules and their verbatim messages:

* ``Only integer and real allowed for this operator <expr>`` — the operand of a
  comparison or arithmetic operator is neither ``integer`` nor ``real``. The
  same message fires for ``boolean`` (``ViolRealVsBool.x``) and for ``duration``
  (``EdgeBareDurZero.x``, ``ValidDurAndTime.x``), so this is one *type class*
  rule, not a per-datatype special case.
* ``Datatype error in assignment: <lhs> = <rhs>`` — the assigned value's type
  does not belong to the target's type class (``ViolIntFromBool.x``).
* ``Condition in IF-sentence is not boolean`` — an ``IF``/``ELSIF`` condition
  is not ``boolean`` (``ViolIntCond.x``).

Only rules with probe evidence live here. Everything the probes did not settle
is deliberately left permissive: :func:`infer_expr_type` returns ``None`` for
anything it cannot prove (record-typed fields, function-call results, SFC
runtime accessors) and every caller skips ``None``. Silence here means
"unproven", never "legal".
"""

from __future__ import annotations

from enum import StrEnum

from sattline_parser.models.ast_model import DataType, Simple_DataType
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    Compare,
    NotOp,
    SLExpression,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.validation.symbols import Scope, is_sfc_runtime_constant, resolve_var


class TypeFamily(StrEnum):
    """Coarse type classes the real validator groups primitives into.

    The grouping is not invented: it is the minimum needed to express the three
    probed messages. ``NUMERIC`` exists because the tool's wording names exactly
    ``integer`` and ``real``; the string-like and temporal families exist so
    that assignments *within* a family stay legal without further probing.
    """

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


def datatype_family(datatype: str) -> TypeFamily | None:
    """Family of a resolved datatype name, or ``None`` for records/unknowns.

    ``Variable`` normalises every built-in primitive name to
    :class:`Simple_DataType` and leaves a record name as a plain ``str``, so a
    string that is not a known primitive is a custom type.
    """
    try:
        member = Simple_DataType.from_any(datatype)
    except ValueError:
        return None
    return _FAMILIES.get(member)


def is_numeric(datatype: str) -> bool:
    return datatype_family(datatype) is TypeFamily.NUMERIC


def is_boolean(datatype: str) -> bool:
    return datatype_family(datatype) is TypeFamily.BOOLEAN


def infer_expr_type(expr: SLExpression, scope: Scope, records: dict[str, DataType]) -> str | None:
    """Static type of ``expr`` as a datatype name, or ``None`` when unproven.

    The returned name is what to hand to :func:`datatype_family` /
    :func:`is_numeric`; it is deliberately *not* a full type object, because
    record identity is not part of any probed rule.
    """
    if isinstance(expr, bool):
        return Simple_DataType.BOOLEAN.value
    if isinstance(expr, int):
        return Simple_DataType.INTEGER.value
    if isinstance(expr, float):
        return Simple_DataType.REAL.value
    if isinstance(expr, str):
        return Simple_DataType.STRING.value
    if isinstance(expr, VarRef):
        resolved = resolve_var(expr, scope, records)
        if resolved is None:
            # ``On``/``Off`` are boolean literals in the native expression reader
            # (00487a60) and lower to true/false (0047d720), not variables.
            return Simple_DataType.BOOLEAN.value if is_sfc_runtime_constant(expr.name) else None
        return resolved.datatype_text
    if isinstance(expr, Compare | BoolOp | NotOp):
        return Simple_DataType.BOOLEAN.value
    if isinstance(expr, BinOp):
        # The result class is the promoted class of the operands, but only when
        # the left operand already proves it is numeric; otherwise the fold
        # result is unknown and callers must not reason about it.
        return _promoted_numeric(infer_expr_type(expr.left, scope, records))
    if isinstance(expr, UnaryOp):
        return infer_expr_type(expr.operand, scope, records)
    if isinstance(expr, TernaryOp):
        return _branch_type(expr, scope, records)
    # Remaining case: FuncCall. Built-in return types are not modelled (see
    # validation.builtins), so a call result is always unproven.
    return None


def _promoted_numeric(left_type: str | None) -> str | None:
    return left_type if left_type is not None and is_numeric(left_type) else None


def _branch_type(expr: TernaryOp, scope: Scope, records: dict[str, DataType]) -> str | None:
    """Type of an ``IF ... THEN ... ELSE ... ENDIF`` expression.

    All branches must agree; a branch of unknown type makes the whole thing
    unknown rather than defaulting to the first one.
    """
    types = [infer_expr_type(value, scope, records) for _, value in expr.branches]
    if expr.else_expr is not None:
        types.append(infer_expr_type(expr.else_expr, scope, records))
    if not types or any(family_of(t) is None for t in types):
        return None
    first = types[0]
    return first if all(t == first for t in types) else None


def family_of(datatype: str | None) -> TypeFamily | None:
    return None if datatype is None else datatype_family(datatype)


def assignment_is_compatible(source_type: str, target_type: str) -> bool:
    """Whether ``target = source`` is legal under the probed rules.

    Legal when both sides share a family, which keeps ``integer`` into ``real``
    (probed and accepted) and every same-primitive assignment working. Illegal
    across families, which is what ``Output = Flag1`` (integer target, boolean
    source) reports.

    A narrowing ``real`` into ``integer`` is *not* rejected: the probe set
    contains no such assignment, so there is no evidence either way and
    flagging it would be a guess.
    """
    source_family = datatype_family(source_type)
    target_family = datatype_family(target_type)
    if source_family is None or target_family is None:
        return True
    return source_family is target_family


def operand_types(expr: Compare | BinOp, scope: Scope, records: dict[str, DataType]) -> tuple[str | None, str | None]:
    """Static types of a binary operator's two operands."""
    return infer_expr_type(expr.left, scope, records), infer_expr_type(expr.right, scope, records)


def assignment_types(
    assignment: Assignment, scope: Scope, records: dict[str, DataType]
) -> tuple[str | None, str | None]:
    """(target type, source type) for an assignment, either side may be ``None``."""
    target = resolve_var(assignment.target, scope, records)
    source = infer_expr_type(assignment.value, scope, records)
    return (None if target is None else target.datatype_text), source
