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
no longer needs to reimplement the recursion. The walk uses an explicit stack
and keeps ancestors as a persistent chain, so a deep tree is walked in linear
time without growing the Python call stack.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import cast, overload

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


class _AncestorChain:
    """A persistent root-to-parent chain.

    Extending the chain costs O(1), so a walk does not build one tuple per
    yielded node. :meth:`to_tuple` expands it only when a caller reads
    :attr:`WalkEvent.parents`.
    """

    __slots__ = ("length", "node", "parent")

    def __init__(self, node: object, parent: _AncestorChain | None) -> None:
        self.node = node
        self.parent = parent
        self.length = 1 if parent is None else parent.length + 1

    def to_tuple(self) -> tuple[object, ...]:
        nodes: list[object] = []
        current: _AncestorChain | None = self
        while current is not None:
            nodes.append(current.node)
            current = current.parent
        nodes.reverse()
        return tuple(nodes)

    @classmethod
    def from_tuple(cls, parents: tuple[object, ...]) -> _AncestorChain | None:
        chain: _AncestorChain | None = None
        for parent in parents:
            chain = cls(parent, chain)
        return chain


class _Ancestors(Sequence[object]):
    """A sequence view over a persistent ancestor chain.

    The chain is built in O(1) per step. Iteration, indexing, equality, and
    repr expand it on demand, so a caller pays O(depth) only when it reads the
    ancestry.
    """

    __slots__ = ("_chain",)

    def __init__(self, chain: _AncestorChain | None) -> None:
        self._chain = chain

    @classmethod
    def from_tuple(cls, parents: Sequence[object]) -> _Ancestors:
        return cls(_AncestorChain.from_tuple(tuple(parents)))

    def _as_tuple(self) -> tuple[object, ...]:
        chain = self._chain
        return () if chain is None else chain.to_tuple()

    def __len__(self) -> int:
        chain = self._chain
        return 0 if chain is None else chain.length

    def __iter__(self) -> Iterator[object]:
        return iter(self._as_tuple())

    @overload
    def __getitem__(self, index: int) -> object: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[object]: ...

    def __getitem__(self, index: int | slice) -> object | Sequence[object]:
        return self._as_tuple()[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Ancestors):
            return self._as_tuple() == other._as_tuple()
        if isinstance(other, tuple | list):
            return self._as_tuple() == tuple(cast("Sequence[object]", other))
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._as_tuple())

    def __repr__(self) -> str:
        return repr(self._as_tuple())


@dataclass(frozen=True, slots=True)
class WalkEvent:
    """One node on a ``walk``.

    ``relation`` names where the node sits inside its parent, for example
    ``"localvariables[2]"`` or ``"branches[0][1]"``. It is the empty string for
    the root. ``parents`` is the ancestor chain, root first and parent last.
    It behaves like a tuple and expands from a persistent chain on access, so
    the walk itself stays linear on a deep tree.
    """

    node: object
    relation: str
    parents: Sequence[object] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.parents, _Ancestors):
            object.__setattr__(self, "parents", _Ancestors.from_tuple(self.parents))


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


def walk(node: object, *, prune: Callable[[object], bool] | None = None) -> Iterator[WalkEvent]:
    """Yield every AST node under ``node`` in pre-order.

    ``node`` may be a single model node or a list/tuple of them. ``prune`` is
    consulted after a node is yielded; returning true stops descent into that
    node's children. The traversal uses an explicit stack, so a manually built
    deep AST cannot exhaust the Python call stack.
    """
    if isinstance(node, list | tuple):
        items = cast("Sequence[object]", node)
        stack: list[tuple[object, str, _AncestorChain | None]] = [
            (item, f"[{index}]", None) for index, item in reversed(list(enumerate(items)))
        ]
    else:
        stack = [(node, "", None)]

    while stack:
        current, relation, ancestors = stack.pop()
        if not isinstance(current, _NODE_TYPES):
            continue
        yield WalkEvent(current, relation, _Ancestors(ancestors))
        if prune is not None and prune(current):
            continue
        children = list(iter_child_nodes(current))
        if not children:
            continue
        child_ancestors = _AncestorChain(current, ancestors)
        for child_relation, child in reversed(children):
            stack.append((child, child_relation, child_ancestors))


class NodeVisitor:
    """Dispatch to ``visit_<ClassName>`` methods, falling back to the walker.

    A subclass that overrides a ``visit_*`` method decides whether to descend by
    calling ``self.generic_visit(node)``. The default walk covers every child
    that ``iter_child_nodes`` reports. Dispatch is recursive by design, because
    an override controls its own descent; :func:`walk` is the fully iterative
    API. Parsed ASTs are bounded by ``source_io.MAX_SOURCE_DEPTH``, so the
    dispatch stays inside the default recursion limit.
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
