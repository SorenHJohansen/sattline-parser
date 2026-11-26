"""Branch paths in module-code validation for optional expression members.

A ternary without an ``else`` and an SFC transition without a guard are both
legal AST shapes with no input line to reach them. These tests build the nodes
directly and assert that the walkers and the type inference accept them.
"""

from __future__ import annotations

from sattline_parser.models.ast_model import SFCTransition
from sattline_parser.models.expressions import TernaryOp
from sattline_parser.validation.code import (
    ValidationContext,
    walk_expression,
    walk_sfc_item,
)
from sattline_parser.validation.symbols import Scope
from sattline_parser.validation.type_graph import TypeGraph
from sattline_parser.validation.typing import infer_expr_type


def _context() -> ValidationContext:
    return ValidationContext(
        scope=Scope(parent=None, variables={}),
        records={},
        type_graph=TypeGraph.from_datatypes([]),
        sfc_names=set(),
        errors=[],
    )


def test_walk_expression_accepts_a_ternary_without_an_else_branch() -> None:
    expression = TernaryOp(branches=((True, 1),), else_expr=None)
    context = _context()

    walk_expression(expression, context)

    assert context.errors == []


def test_infer_expr_type_accepts_a_ternary_without_an_else_branch() -> None:
    expression = TernaryOp(branches=((True, 1),), else_expr=None)
    context = _context()

    inferred = infer_expr_type(expression, context.scope, context.records, context.type_graph)

    assert inferred == "integer"


def test_walk_sfc_item_accepts_a_transition_without_a_condition() -> None:
    transition = SFCTransition(name="Bare", condition=None)
    context = _context()

    walk_sfc_item(transition, context)

    assert context.errors == []
