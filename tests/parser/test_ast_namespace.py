# pyright: reportPrivateUsage=false
"""Tests for the public ``sattline_parser.ast`` namespace."""

from __future__ import annotations

import dataclasses

import sattline_parser.ast as sl_ast
from sattline_parser.models import ast_model, clauses, expressions, tails
from sattline_parser.models.walk import _NODE_TYPES

#: Type aliases are not classes, so the dataclass sweep cannot see them.
_TYPE_ALIASES = (
    "CodeItem",
    "CoordBox",
    "CoordPair",
    "InteractBodyEntry",
    "SFCBodyItem",
    "SLExpression",
    "SLStmt",
    "Tail",
)


def test_every_walker_node_type_is_exported() -> None:
    for node_type in _NODE_TYPES:
        name = node_type.__name__
        assert name in sl_ast.__all__, name
        assert getattr(sl_ast, name) is node_type, name


def test_every_exported_model_dataclass_is_exported() -> None:
    for module in (ast_model, expressions, clauses, tails):
        for name in module.__all__:
            value = getattr(module, name)
            if isinstance(value, type) and dataclasses.is_dataclass(value):
                assert name in sl_ast.__all__, name
                assert getattr(sl_ast, name) is value, name


def test_type_aliases_are_exported() -> None:
    for name in _TYPE_ALIASES:
        assert name in sl_ast.__all__, name
        assert hasattr(sl_ast, name), name


def test_walker_surface_is_exported() -> None:
    for name in ("walk", "iter_child_nodes", "iter_literal_leaves", "NodeVisitor", "WalkEvent", "LiteralLeaf"):
        assert name in sl_ast.__all__, name


def test_shared_scalar_types_are_exported() -> None:
    assert sl_ast.SourceSpan is ast_model.SourceSpan
    assert sl_ast.MappingSource is ast_model.MappingSource
    assert sl_ast.MappingSource.VARIABLE.value == "variable_name"
    assert sl_ast.MappingSource.VALUE.value == "value"


def test_code_comment_has_one_canonical_class() -> None:
    assert ast_model.CodeComment is expressions.CodeComment
    assert sl_ast.CodeComment is expressions.CodeComment


def test_ast_all_names_resolve_and_are_unique() -> None:
    assert len(sl_ast.__all__) == len(set(sl_ast.__all__))
    assert sl_ast.__all__ == sorted(sl_ast.__all__)
    for name in sl_ast.__all__:
        assert hasattr(sl_ast, name), name
