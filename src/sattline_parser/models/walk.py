"""Public traversal of the SattLine AST.

``walk`` yields every AST node in pre-order, together with its ancestry and the
field that holds it. ``NodeVisitor`` is the subclassing form: override a
``visit_<ClassName>`` method and call ``generic_visit`` to descend.

The walk is structural. It visits model nodes (declarations, module and code
containers, SFC nodes, statements, and expressions) and their list fields. It
does not descend into ``GraphObject.properties``, ``InteractObject.properties``,
``ModuleDef.properties``, ``ModuleHeader.invocation_arguments``, ``parse_tree``,
or the deprecated ``BasePicture.graphics_*`` and ``library_dependencies``
fields. Those are attached data, debugging state, or another layer's transport,
not AST children. Literal values (``bool``, ``int``, ``float``, ``str``) are
leaves and are not visited as nodes.

The order is deterministic: the declared field order of each node, with list
elements in source order. It is the same tree every caller sees, so a consumer
no longer needs to reimplement the recursion.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import cast

from . import ast_model as m
from .expressions import (
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
from .tails import is_expression_tail

__all__ = ["NodeVisitor", "WalkEvent", "iter_child_nodes", "walk"]

#: Model classes that count as AST nodes. Literals and leaves such as
#: ``SourceSpan`` and ``Simple_DataType`` are deliberately absent.
_NODE_TYPES: tuple[type[object], ...] = (
    m.BasePicture,
    m.CodeComment,
    m.DataType,
    m.Equation,
    m.FrameModule,
    m.GraphObject,
    m.InteractObject,
    m.ModuleCode,
    m.ModuleDef,
    m.ModuleHeader,
    m.ModuleTypeDef,
    m.ModuleTypeInstance,
    m.ParameterMapping,
    m.SFCCodeBlocks,
    m.SFCAlternative,
    m.SFCFork,
    m.SFCParallel,
    m.SFCStep,
    m.SFCSubsequence,
    m.SFCTransition,
    m.SFCTransitionSub,
    m.Sequence,
    m.SingleModule,
    m.Variable,
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


@dataclass(frozen=True, slots=True)
class WalkEvent:
    """One node on a ``walk``.

    ``relation`` names where the node sits inside its parent, for example
    ``"localvariables[2]"`` or ``"branches[0][1]"``. It is the empty string for
    the root. ``parents`` is the ancestor chain, root first and parent last.
    """

    node: object
    relation: str
    parents: tuple[object, ...]


def _listed(prefix: str, values: Iterable[object]) -> Iterator[tuple[str, object]]:
    """Yield ``prefix[i]`` for each item of a list or tuple, in order."""
    for index, value in enumerate(values):
        yield f"{prefix}[{index}]", value


def _expression_tails(prefix: str, values: Iterable[object]) -> Iterator[tuple[str, object]]:
    """Yield only the computed tails; bound tail wrappers are annotation leaves."""
    for index, value in enumerate(values):
        if is_expression_tail(value):
            yield f"{prefix}[{index}]", value


def iter_child_nodes(node: object) -> Iterator[tuple[str, object]]:
    """Yield ``(relation, child)`` pairs for the AST children of ``node``.

    A list or tuple is treated as a sequence of nodes and labelled by index.
    Non-node values are skipped, so callers may pass a field directly.
    """
    if isinstance(node, list | tuple):
        for index, child in enumerate(cast("Sequence[object]", node)):
            if isinstance(child, _NODE_TYPES):
                yield f"[{index}]", child
        return
    yield from _container_children(node)
    yield from _declaration_children(node)
    yield from _code_children(node)
    yield from _expression_children(node)


def _container_children(node: object) -> Iterator[tuple[str, object]]:
    """Children of the picture and module containers."""
    if isinstance(node, m.BasePicture):
        yield "header", node.header
        yield from _listed("datatype_defs", node.datatype_defs)
        yield from _listed("moduletype_defs", node.moduletype_defs)
        yield from _listed("moduleparameters", node.moduleparameters)
        yield from _listed("localvariables", node.localvariables)
        yield from _listed("submodules", node.submodules)
        yield from _listed("moduledefs", node.moduledefs)
        yield from _listed("modulecodes", node.modulecodes)
        yield from _listed("trailing_comments", node.trailing_comments)
        return

    if isinstance(node, m.ModuleTypeDef):
        yield from _listed("moduleparameters", node.moduleparameters)
        yield from _listed("localvariables", node.localvariables)
        yield from _listed("submodules", node.submodules)
        yield from _listed("moduledefs", node.moduledefs)
        yield from _listed("modulecodes", node.modulecodes)
        yield from _listed("parametermappings", node.parametermappings)
        if node.groupconn is not None:
            yield "groupconn", node.groupconn
        yield from _listed("description_comments", node.description_comments)
        yield from _listed("trailing_comments", node.trailing_comments)
        return

    if isinstance(node, m.SingleModule):
        yield "header", node.header
        yield from _listed("moduleparameters", node.moduleparameters)
        yield from _listed("localvariables", node.localvariables)
        yield from _listed("submodules", node.submodules)
        yield from _listed("moduledefs", node.moduledefs)
        yield from _listed("modulecodes", node.modulecodes)
        yield from _listed("parametermappings", node.parametermappings)
        yield from _listed("trailing_comments", node.trailing_comments)
        return

    if isinstance(node, m.FrameModule):
        yield "header", node.header
        yield from _listed("moduleparameters", node.moduleparameters)
        yield from _listed("localvariables", node.localvariables)
        yield from _listed("submodules", node.submodules)
        yield from _listed("moduledefs", node.moduledefs)
        yield from _listed("modulecodes", node.modulecodes)
        yield from _listed("trailing_comments", node.trailing_comments)
        return

    if isinstance(node, m.ModuleTypeInstance):
        yield "header", node.header
        yield from _listed("parametermappings", node.parametermappings)
        return

    if isinstance(node, m.ModuleHeader):
        if node.enable_tail is not None and is_expression_tail(node.enable_tail):
            yield "enable_tail", node.enable_tail
        yield from _expression_tails("invoke_coord_tails", node.invoke_coord_tails)
        if node.groupconn is not None:
            yield "groupconn", node.groupconn
        yield from _listed("description_comments", node.description_comments)


def _declaration_children(node: object) -> Iterator[tuple[str, object]]:
    """Children of declarations and module layout blocks."""
    if isinstance(node, m.DataType):
        yield from _listed("var_list", node.var_list)
        yield from _listed("trailing_comments", node.trailing_comments)
        return

    if isinstance(node, m.ParameterMapping):
        yield "target", node.target
        if node.source is not None:
            yield "source", node.source
        return

    if isinstance(node, m.ModuleDef):
        yield from _expression_tails("clipping_tails", node.clipping_tails or ())
        yield from _listed("graph_objects", node.graph_objects)
        yield from _listed("interact_objects", node.interact_objects)


def _code_children(node: object) -> Iterator[tuple[str, object]]:
    """Children of module code, equations, and SFC structure."""
    if isinstance(node, m.ModuleCode):
        yield from _listed("sequences", node.sequences or ())
        yield from _listed("equations", node.equations or ())
        return

    if isinstance(node, m.Sequence | m.Equation):
        yield from _listed("code", node.code)
        return

    if isinstance(node, m.SFCCodeBlocks):
        yield from _listed("enter", node.enter)
        yield from _listed("active", node.active)
        yield from _listed("exit", node.exit)
        return

    if isinstance(node, m.SFCStep):
        yield "code", node.code
        if node.fork is not None:
            yield "fork", node.fork
        return

    if isinstance(node, m.SFCTransition):
        if node.condition is not None:
            yield "condition", node.condition
        if node.fork is not None:
            yield "fork", node.fork
        return

    if isinstance(node, m.SFCTransitionSub | m.SFCSubsequence):
        yield from _listed("body", node.body)
        return

    if isinstance(node, m.SFCAlternative | m.SFCParallel):
        for branch_index, branch in enumerate(node.branches):
            for item_index, item in enumerate(branch):
                yield f"branches[{branch_index}][{item_index}]", item


def _expression_children(node: object) -> Iterator[tuple[str, object]]:
    """Children of statements and expressions."""
    if isinstance(node, Assignment):
        yield "target", node.target
        yield "value", node.value
        return

    if isinstance(node, FuncCallStmt):
        yield "call", node.call
        return

    if isinstance(node, IfStmt):
        for branch_index, (condition, body) in enumerate(node.branches):
            yield f"branches[{branch_index}][0]", condition
            for item_index, item in enumerate(body):
                yield f"branches[{branch_index}][1][{item_index}]", item
        yield from _listed("else_block", node.else_block or ())
        return

    if isinstance(node, BoolOp):
        yield from _listed("operands", node.operands)
        return

    if isinstance(node, NotOp | UnaryOp):
        yield "operand", node.operand
        return

    if isinstance(node, Compare | BinOp):
        yield "left", node.left
        yield "right", node.right
        return

    if isinstance(node, FuncCall):
        yield from _listed("args", node.args)
        return

    if isinstance(node, TernaryOp):
        for branch_index, (condition, value) in enumerate(node.branches):
            yield f"branches[{branch_index}][0]", condition
            yield f"branches[{branch_index}][1]", value
        if node.else_expr is not None:
            yield "else_expr", node.else_expr


def _walk(
    node: object,
    relation: str,
    parents: tuple[object, ...],
    prune: Callable[[object], bool] | None,
) -> Iterator[WalkEvent]:
    if not isinstance(node, _NODE_TYPES):
        return
    yield WalkEvent(node=node, relation=relation, parents=parents)
    if prune is not None and prune(node):
        return
    for child_relation, child in iter_child_nodes(node):
        yield from _walk(child, child_relation, (*parents, node), prune)


def walk(node: object, *, prune: Callable[[object], bool] | None = None) -> Iterator[WalkEvent]:
    """Yield every AST node under ``node`` in pre-order.

    ``node`` may be a single model node or a list/tuple of them. ``prune`` is
    consulted after a node is yielded; returning true stops descent into that
    node's children.
    """
    if isinstance(node, list | tuple):
        for index, item in enumerate(cast("Sequence[object]", node)):
            yield from _walk(item, f"[{index}]", (), prune)
        return
    yield from _walk(node, "", (), prune)


class NodeVisitor:
    """Dispatch to ``visit_<ClassName>`` methods, falling back to the walker.

    A subclass that overrides a ``visit_*`` method decides whether to descend by
    calling ``self.generic_visit(node)``. The default walk covers every child
    that ``iter_child_nodes`` reports.
    """

    def visit(self, node: object) -> None:
        """Visit one node, dispatching on its concrete class name."""
        method: Callable[[object], None] | None = getattr(self, f"visit_{type(node).__name__}", None)
        if method is None:
            self.generic_visit(node)
        else:
            method(node)

    def generic_visit(self, node: object) -> None:
        """Visit every child of ``node`` in walker order."""
        for _relation, child in iter_child_nodes(node):
            self.visit(child)
