"""Validation of tails attached to headers, graphics, interact, and module layout.

The walker emits every tail once, either through the clause that owns it or
through the flat ``properties["tails"]`` view. This module turns those events
into findings in the scope that encloses the container:

* expression tails are walked like any other expression, so undefined
  variables (SL-V019) and ordinary operator diagnostics fire;
* an ``Enable_`` tail must be boolean (SL-V030);
* a coordinate-position tail must be real (SL-V032);
* a bound ``InVar_``/``OutVar_`` name produces no diagnostic. The parser does
  not evidence how such a name resolves, so the query layer reports it as an
  unresolved use instead.
"""

from __future__ import annotations

from collections.abc import Collection

from sattline_parser.models import WalkEvent, walk
from sattline_parser.models import ast_model as m
from sattline_parser.models.ast_model import SourceSpan
from sattline_parser.models.clauses import (
    AssignClause,
    EnableClause,
    FlagClause,
    ProcedureCall,
    TailedClause,
)
from sattline_parser.models.expressions import SLExpression
from sattline_parser.models.tails import is_expression_tail
from sattline_parser.names import fold_identifier
from sattline_parser.validation.code import walk_expression
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.symbols import Scope
from sattline_parser.validation.type_graph import TypeGraph
from sattline_parser.validation.typing import infer_expr_type, is_boolean

__all__ = ["check_annotation_tails"]

#: The tail contexts that carry a type rule beyond the ordinary expression walk.
_ENABLE = "enable"
_COORDINATE = "coordinate"


def _tail_context(event: WalkEvent) -> str | None:
    """Name the rule context for a tail, or return ``None`` for a non-tail child.

    The walker's relation strings are part of its contract. A clause tail is
    reached through ``tail``, a procedure argument through ``args[i]``, a
    header coordinate tail through ``invoke_coord_tails[i]``, and a property
    tail through ``properties.<key>`` or ``properties.<key>[i]``.
    """
    if not event.parents:
        return None
    parent = event.parents[-1]
    relation = event.relation

    if isinstance(parent, m.ModuleHeader):
        if relation == "enable_tail":
            return _ENABLE
        if relation.startswith("invoke_coord_tails"):
            # Module_In_View and assignment tails are folded into this field,
            # so only the undefined-variable walk is safe here.
            return "header"
        return None

    if isinstance(parent, m.ModuleDef):
        if relation.startswith("clipping_tails") or relation.startswith("properties.tails"):
            return _COORDINATE
        return None

    if isinstance(parent, m.GraphObject):
        if relation == "properties.enable_tail":
            return _ENABLE
        if relation.startswith("properties.tails"):
            # The flat list mixes coordinate tails with attribute tails that
            # are not modelled as clauses, so no position rule applies here.
            return "annotation"
        return None

    if isinstance(parent, m.InteractObject):
        if relation.startswith("properties.tails"):
            return "annotation"
        if relation.startswith("properties.body"):
            return "annotation"
        return None

    if isinstance(parent, EnableClause):
        return _ENABLE if relation == "tail" else None

    if isinstance(parent, TailedClause | AssignClause | FlagClause):
        return "annotation" if relation == "tail" else None

    if isinstance(parent, ProcedureCall):
        return "annotation" if relation.startswith("args") else None

    return None


def _check_coordinate_real(
    tail: SLExpression,
    scope: Scope,
    records: dict[str, m.DataType],
    type_graph: TypeGraph,
    errors: list[Diagnostic],
) -> None:
    """A coordinate position must be real, never integer (SL-V032)."""
    inferred = infer_expr_type(tail, scope, records, type_graph)
    if inferred is not None and fold_identifier(inferred) != fold_identifier(m.Simple_DataType.REAL.value):
        errors.append(
            Diagnostic(
                code=DiagnosticCode.COORDINATE_NOT_REAL,
                message=(
                    f"Coordinate position is of an invalid type: it is {inferred}, but a coordinate must be a real"
                ),
                span=_expression_span(tail),
            )
        )


def _expression_span(expr: SLExpression) -> SourceSpan | None:
    """Span of a parsed expression node; primitives carry none."""
    span = getattr(expr, "span", None)
    return span if isinstance(span, SourceSpan) else None


def _check_enable_condition(
    tail: SLExpression,
    scope: Scope,
    records: dict[str, m.DataType],
    type_graph: TypeGraph,
    errors: list[Diagnostic],
) -> None:
    """An ``Enable_`` expression tail must be boolean (SL-V030)."""
    inferred = infer_expr_type(tail, scope, records, type_graph)
    if inferred is not None and not is_boolean(inferred):
        errors.append(
            Diagnostic(
                code=DiagnosticCode.CONDITION_NOT_BOOLEAN,
                message=f"Enable_ tail condition is not boolean; expression is of type {inferred}",
                span=_expression_span(tail),
            )
        )


def check_annotation_tails(
    container: m.ModuleHeader | m.ModuleDef | m.GraphObject | m.InteractObject,
    scope: Scope,
    records: dict[str, m.DataType],
    type_graph: TypeGraph,
    sfc_names: Collection[str],
    errors: list[Diagnostic],
) -> None:
    """Check every expression tail attached to ``container`` in ``scope``.

    Bound ``VarTail``/``LitStringTail`` values are deliberately skipped: their
    names are references, not values, and the parser does not evidence how a
    name resolves.
    """
    for event in walk(container):
        context = _tail_context(event)
        if context is None:
            continue
        if not is_expression_tail(event.node):
            continue
        tail = event.node
        walk_expression(tail, scope, records, type_graph, set(sfc_names), errors)
        if context == _ENABLE:
            _check_enable_condition(tail, scope, records, type_graph, errors)
        elif context == _COORDINATE:
            _check_coordinate_real(tail, scope, records, type_graph, errors)
