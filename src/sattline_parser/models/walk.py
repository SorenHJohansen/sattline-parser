"""Public traversal of the SattLine AST.

``walk`` yields every AST node in pre-order, together with its ancestry, the
model field that holds it, and its subscript path. ``NodeVisitor`` is the
subclassing form: override a ``visit_<ClassName>`` method to decide how to
descend, and a ``leave_<ClassName>`` method to run after the subtree.

The walk is structural and driven by ``_FIELD_SPECS``. Every field of every node
class is declared as one of:

* ``node``: a node or a nested sequence of nodes;
* ``value``: a node or a literal value (``SLExpression``/``Tail`` fields);
* ``properties``: a typed property map with a fixed visit order;
* ``leaf``: no child nodes.

The field-coverage test asserts that the declaration matches
``dataclasses.fields`` exactly, so a new field forces a walker decision.

The walk descends into ``GraphObject.properties`` and
``InteractObject.properties`` in the documented order, and into
``ModuleHeader.arguments`` and ``ModuleDef.clipping`` as ordinary nodes. It
does not descend into ``parse_tree``. Literal values are leaves and are not
emitted as nodes; use :func:`iter_literal_leaves` to read the literal values a
node holds directly.

Property order:

* ``GraphObject``: ``colours``, ``enable_tail``, ``tails``, ``text_vars``,
  then the non-node keys (``coords``, ``segment_point``, ``polygon_type``,
  ``layer``, ``enable``).
* ``InteractObject``: ``procedure``, ``assigns``, ``enables``, ``flags``,
  ``colours``, ``body``, ``tails``, then the non-node keys (``coords``,
  ``layers``).

The flat ``properties["tails"]`` list is a derived view: a tail owned by a
clause is emitted through that clause, and only the unowned (coordinate) tails
are emitted from the flat list. Every tail node therefore appears once. The
order is load-bearing: ``tails`` is visited last among the node-bearing keys, so
the clauses have already recorded their tails before the flat list is filtered.

The order is deterministic: the declared field order of each node, with list
elements in source order, except for the property maps, which use the order
above. The walk uses an explicit stack and keeps ancestors as a persistent
chain, so a deep tree is walked in linear time without growing the Python call
stack.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, is_dataclass
from dataclasses import fields as dataclass_fields
from typing import Literal, cast, overload

from . import ast_model as m
from .clauses import (
    Alignment,
    AssignClause,
    ClippingClause,
    ColourSpec,
    EnableClause,
    FlagClause,
    ModuleArguments,
    ModuleInViewClause,
    ModuleMarker,
    PickButton,
    ProcedureCall,
    ScaleSelector,
    TailedClause,
    ZoomLimits,
)
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
from .tails import LitStringTail, VarTail

__all__ = ["LiteralLeaf", "NodeVisitor", "WalkEvent", "iter_child_nodes", "iter_literal_leaves", "walk"]

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
    Alignment,
    AssignClause,
    Assignment,
    BinOp,
    BoolOp,
    ClippingClause,
    ColourSpec,
    Compare,
    EnableClause,
    FlagClause,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    LitStringTail,
    ModuleArguments,
    ModuleInViewClause,
    ModuleMarker,
    NotOp,
    PickButton,
    ProcedureCall,
    ScaleSelector,
    TailedClause,
    TernaryOp,
    UnaryOp,
    VarRef,
    VarTail,
    ZoomLimits,
)

type _FieldKind = Literal["leaf", "node", "value", "properties"]
type _FieldSpecs = dict[type[object], dict[str, _FieldKind]]

#: How the walker treats every field of every node class. ``node`` and
#: ``properties`` yield child nodes, ``value`` yields a child node or a literal,
#: and ``leaf`` yields nothing. The coverage test compares this table with the
#: dataclass fields, so a new field cannot be left unclassified.
_FIELD_SPECS: _FieldSpecs = {
    m.BasePicture: {
        "header": "node",
        "name": "leaf",
        "program_name": "leaf",
        "position": "leaf",
        "datatype_defs": "node",
        "moduletype_defs": "node",
        "moduleparameters": "node",
        "localvariables": "node",
        "submodules": "node",
        "moduledefs": "node",
        "modulecodes": "node",
        "origin_file": "leaf",
        "origin_lib": "leaf",
        "graphics_file": "leaf",
        "trailing_comments": "node",
        "datecode": "leaf",
        "parse_tree": "leaf",
    },
    m.CodeComment: {"text": "leaf", "span": "leaf"},
    m.DataType: {
        "name": "leaf",
        "description": "leaf",
        "datecode": "leaf",
        "var_list": "node",
        "origin_file": "leaf",
        "origin_lib": "leaf",
        "declaration_span": "leaf",
        "trailing_comments": "node",
    },
    m.Equation: {
        "kind": "leaf",
        "name": "leaf",
        "position": "leaf",
        "size": "leaf",
        "code": "node",
        "layer_info": "leaf",
    },
    m.FrameModule: {
        "header": "node",
        "datecode": "leaf",
        "moduleparameters": "node",
        "localvariables": "node",
        "submodules": "node",
        "moduledefs": "node",
        "modulecodes": "node",
        "trailing_comments": "node",
    },
    m.GraphObject: {"type": "leaf", "properties": "properties", "span": "leaf"},
    m.InteractObject: {"type": "leaf", "properties": "properties", "span": "leaf"},
    m.ModuleCode: {"sequences": "node", "equations": "node"},
    m.ModuleDef: {
        "clipping": "node",
        "zoom_limits": "leaf",
        "seq_layers": "leaf",
        "grid": "leaf",
        "zoomable": "leaf",
        "graph_objects": "node",
        "interact_objects": "node",
        "span": "leaf",
    },
    m.ModuleHeader: {
        "name": "leaf",
        "invoke_coord": "leaf",
        "declaration_span": "leaf",
        "arguments": "node",
        "invoke_coord_tails": "value",
        "groupconn": "node",
        "groupconn_global": "leaf",
        "description_comments": "node",
    },
    m.ModuleTypeDef: {
        "name": "leaf",
        "datecode": "leaf",
        "is_private": "leaf",
        "moduleparameters": "node",
        "localvariables": "node",
        "submodules": "node",
        "moduledefs": "node",
        "modulecodes": "node",
        "parametermappings": "node",
        "groupconn": "node",
        "groupconn_global": "leaf",
        "origin_file": "leaf",
        "origin_lib": "leaf",
        "declaration_span": "leaf",
        "description_comments": "node",
        "trailing_comments": "node",
    },
    m.ModuleTypeInstance: {
        "header": "node",
        "moduletype_name": "leaf",
        "parametermappings": "node",
    },
    m.ParameterMapping: {
        "target": "node",
        "source_type": "leaf",
        "is_duration": "leaf",
        "is_source_global": "leaf",
        "source": "node",
        "source_literal": "value",
        "span": "leaf",
    },
    m.SFCCodeBlocks: {"enter": "node", "active": "node", "exit": "node"},
    m.SFCAlternative: {"branches": "node", "span": "leaf"},
    m.SFCFork: {"targets": "leaf", "has_break": "leaf"},
    m.SFCParallel: {"branches": "node", "span": "leaf"},
    m.SFCStep: {
        "kind": "leaf",
        "name": "leaf",
        "code": "node",
        "fork": "node",
        "span": "leaf",
    },
    m.SFCSubsequence: {"name": "leaf", "body": "node", "kind": "leaf", "span": "leaf"},
    m.SFCTransition: {"name": "leaf", "condition": "value", "fork": "node", "span": "leaf"},
    m.SFCTransitionSub: {"name": "leaf", "body": "node", "span": "leaf"},
    m.Sequence: {
        "name": "leaf",
        "type": "leaf",
        "position": "leaf",
        "size": "leaf",
        "seqcontrol": "leaf",
        "seqtimer": "leaf",
        "code": "node",
    },
    m.SingleModule: {
        "header": "node",
        "datecode": "leaf",
        "moduleparameters": "node",
        "localvariables": "node",
        "submodules": "node",
        "moduledefs": "node",
        "modulecodes": "node",
        "parametermappings": "node",
        "trailing_comments": "node",
    },
    m.Variable: {
        "name": "leaf",
        "datatype": "leaf",
        "global_var": "leaf",
        "const": "leaf",
        "state": "leaf",
        "opsave": "leaf",
        "secure": "leaf",
        "init_value": "value",
        "has_explicit_default": "leaf",
        "description": "leaf",
        "declaration_span": "leaf",
        "init_is_duration": "leaf",
        "attribute_order": "leaf",
    },
    Alignment: {"value": "leaf", "span": "leaf"},
    AssignClause: {"name": "leaf", "value": "value", "tail": "value", "span": "leaf"},
    Assignment: {"target": "node", "value": "value", "span": "leaf"},
    BinOp: {"left": "value", "op": "leaf", "right": "value", "span": "leaf"},
    BoolOp: {"op": "leaf", "operands": "value", "span": "leaf"},
    ClippingClause: {"bounds": "leaf", "tails": "value", "span": "leaf"},
    ColourSpec: {
        "kind": "leaf",
        "width": "node",
        "assignments": "node",
        "style": "node",
        "span": "leaf",
    },
    Compare: {"left": "value", "op": "leaf", "right": "value", "span": "leaf"},
    EnableClause: {"enabled": "leaf", "tail": "value", "span": "leaf"},
    FlagClause: {"name": "leaf", "extra": "leaf", "tail": "value", "span": "leaf"},
    FuncCall: {"name": "leaf", "args": "value", "span": "leaf"},
    FuncCallStmt: {"call": "node", "span": "leaf"},
    IfStmt: {"branches": "node", "else_block": "node", "span": "leaf"},
    LitStringTail: {"keyword": "leaf", "text": "leaf", "span": "leaf"},
    ModuleArguments: {
        "layer": "leaf",
        "enable": "node",
        "module_in_view": "node",
        "zoom_limits": "node",
        "zoomable": "leaf",
        "markers": "node",
        "assigns": "node",
        "span": "leaf",
    },
    ModuleInViewClause: {"in_view": "leaf", "tail": "value", "span": "leaf"},
    ModuleMarker: {"kind": "leaf", "span": "leaf"},
    NotOp: {"operand": "value", "span": "leaf"},
    PickButton: {"value": "leaf", "reference": "node", "span": "leaf"},
    ProcedureCall: {"name": "leaf", "args": "value", "span": "leaf"},
    ScaleSelector: {"mode": "leaf", "span": "leaf"},
    TailedClause: {"key": "leaf", "value": "value", "tail": "value", "span": "leaf"},
    TernaryOp: {"branches": "node", "else_expr": "value", "span": "leaf"},
    UnaryOp: {"op": "leaf", "operand": "value", "span": "leaf"},
    VarRef: {"name": "leaf", "state": "leaf", "span": "leaf"},
    VarTail: {"direction": "leaf", "value": "value", "span": "leaf"},
    ZoomLimits: {"minimum": "leaf", "maximum": "leaf", "span": "leaf"},
}

#: Node-bearing keys of ``GraphProperties`` in the order the walker visits them.
#: The non-node keys stay in the tuple so a property added to the TypedDict
#: forces a decision here; a test compares the tuple with the annotation keys.
_GRAPH_PROPERTY_ORDER: tuple[str, ...] = (
    "colours",
    "enable_tail",
    "tails",
    "coords",
    "segment_point",
    "polygon_type",
    "layer",
    "text_vars",
    "enable",
)

#: Node-bearing keys of ``InteractProperties`` in walk order.
_INTERACT_PROPERTY_ORDER: tuple[str, ...] = (
    "procedure",
    "assigns",
    "enables",
    "flags",
    "colours",
    "body",
    "tails",
    "coords",
    "layers",
)

#: Expression node classes that can stand as a tail or a clause value.
_EXPRESSION_NODE_TYPES: tuple[type[object], ...] = (
    VarRef,
    BoolOp,
    NotOp,
    Compare,
    BinOp,
    UnaryOp,
    FuncCall,
    TernaryOp,
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
    """One event on a :func:`walk`.

    ``relation`` is the display path relative to the parent, for example
    ``"localvariables[2]"`` or ``"branches[0][1]"``. ``field`` is the model
    field that holds the node, or the property key for a property-map child.
    ``indices`` is the subscript path inside that field. ``phase`` is
    ``"enter"`` before the subtree and ``"leave"`` after it, when the walk is
    asked to emit leave events.

    ``parents`` is the ancestor chain, root first and parent last. It behaves
    like a tuple and expands from a persistent chain on access, so the walk
    itself stays linear on a deep tree.
    """

    node: object
    relation: str
    parents: Sequence[object] = ()
    field: str | None = None
    indices: tuple[int, ...] = ()
    phase: Literal["enter", "leave"] = "enter"

    def __post_init__(self) -> None:
        if not isinstance(self.parents, _Ancestors):
            object.__setattr__(self, "parents", _Ancestors.from_tuple(self.parents))


@dataclass(frozen=True, slots=True)
class LiteralLeaf:
    """One literal value directly under a node.

    ``relation``, ``field``, and ``indices`` describe where the value sits, in
    the same shape as :class:`WalkEvent`. ``value`` is a boolean, number, or
    string; ``None`` and containers are not literal leaves.
    """

    relation: str
    field: str | None
    indices: tuple[int, ...]
    value: bool | int | float | str


@dataclass(frozen=True, slots=True)
class _Child:
    """One node child, with the metadata the walk exposes on its event."""

    relation: str
    field: str | None
    indices: tuple[int, ...]
    node: object


def _is_tail_value(value: object) -> bool:
    return isinstance(value, (VarTail, LitStringTail, *_EXPRESSION_NODE_TYPES))


def _collect_tail_ids(value: object, into: set[int]) -> None:
    """Collect the ids of every tail reachable through ``value``.

    Used to keep the flat ``properties["tails"]`` view from emitting a tail a
    second time when the same object is owned by a typed clause.
    """
    if _is_tail_value(value):
        into.add(id(value))
        return
    if isinstance(value, list | tuple):
        for item in cast("Sequence[object]", value):
            _collect_tail_ids(item, into)
        return
    if is_dataclass(value):
        for field in dataclass_fields(value):
            _collect_tail_ids(getattr(value, field.name), into)


def _descend(field: str, value: object, relation: str, indices: tuple[int, ...]) -> Iterator[_Child]:
    """Yield ``value`` and its nested sequence items that are nodes."""
    if isinstance(value, _NODE_TYPES):
        yield _Child(relation, field, indices, value)
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(cast("Sequence[object]", value)):
            yield from _descend(field, item, f"{relation}[{index}]", (*indices, index))


def _literal_leaves(field: str, value: object, relation: str, indices: tuple[int, ...]) -> Iterator[LiteralLeaf]:
    """Yield the literal values reachable through one ``value`` field."""
    if isinstance(value, _NODE_TYPES):
        return
    if isinstance(value, bool | int | float | str):
        yield LiteralLeaf(relation, field, indices, value)
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(cast("Sequence[object]", value)):
            yield from _literal_leaves(field, item, f"{relation}[{index}]", (*indices, index))


def _unowned_tail_entries(values: object, owned: set[int]) -> Iterator[_Child]:
    """Yield the flat tail entries whose owner did not already emit them."""
    if not isinstance(values, list | tuple):
        return
    for index, value in enumerate(cast("Sequence[object]", values)):
        if id(value) in owned or not isinstance(value, _NODE_TYPES):
            continue
        yield _Child(f"properties.tails[{index}]", "tails", (index,), value)


def _property_entries(node: m.GraphObject | m.InteractObject) -> Iterator[_Child]:
    """Yield the node-valued properties of a graphics or interact object."""
    properties = node.properties
    order = _GRAPH_PROPERTY_ORDER if isinstance(node, m.GraphObject) else _INTERACT_PROPERTY_ORDER
    owned: set[int] = set()
    for key in order:
        value = properties.get(key)
        if value is None:
            continue
        if key == "tails":
            yield from _unowned_tail_entries(value, owned)
            continue
        _collect_tail_ids(value, owned)
        if isinstance(value, _NODE_TYPES):
            yield _Child(f"properties.{key}", key, (), value)
            continue
        if isinstance(value, list | tuple):
            for index, item in enumerate(cast("Sequence[object]", value)):
                if isinstance(item, _NODE_TYPES):
                    yield _Child(f"properties.{key}[{index}]", key, (index,), item)


def _iter_child_entries(node: object) -> Iterator[_Child]:
    """Yield the node children of ``node``, with field and index metadata."""
    if isinstance(node, list | tuple):
        for index, item in enumerate(cast("Sequence[object]", node)):
            if isinstance(item, _NODE_TYPES):
                yield _Child(f"[{index}]", None, (index,), item)
        return

    specs = _FIELD_SPECS.get(type(node))
    if specs is None:
        return
    for name, kind in specs.items():
        if kind == "leaf":
            continue
        value = getattr(node, name)
        if kind == "properties":
            yield from _property_entries(cast("m.GraphObject | m.InteractObject", node))
            continue
        yield from _descend(name, value, name, ())


def iter_child_nodes(node: object) -> Iterator[tuple[str, object]]:
    """Yield ``(relation, child)`` pairs for the AST children of ``node``.

    A list or tuple is treated as a sequence of nodes and labelled by index.
    Non-node values are filtered here, so callers may pass a field directly.
    """
    for child in _iter_child_entries(node):
        if isinstance(child.node, _NODE_TYPES):
            yield child.relation, child.node


def iter_literal_leaves(node: object) -> Iterator[LiteralLeaf]:
    """Yield the literal values directly under ``node``.

    Only fields declared as ``value`` can hold a literal. Use :func:`walk` to
    reach the nodes, and this helper to read the literal values a node holds
    without boxing them.
    """
    if isinstance(node, list | tuple):
        for item in cast("Sequence[object]", node):
            if isinstance(item, _NODE_TYPES):
                yield from iter_literal_leaves(item)
        return

    specs = _FIELD_SPECS.get(type(node))
    if specs is None:
        return
    for name, kind in specs.items():
        if kind != "value":
            continue
        yield from _literal_leaves(name, getattr(node, name), name, ())


def walk(
    node: object,
    *,
    prune: Callable[[object], bool] | None = None,
    emit_leave: bool = False,
) -> Iterator[WalkEvent]:
    """Yield every AST node under ``node`` in pre-order.

    ``node`` may be a single model node or a list/tuple of them. ``prune`` is
    consulted after a node is yielded; returning true stops descent into that
    node's children. With ``emit_leave``, each enter event is followed by a
    matching ``phase="leave"`` event after the subtree (or immediately, when
    the node is pruned). The traversal uses an explicit stack, so a manually
    built deep AST cannot exhaust the Python call stack.
    """
    initial: list[_Child] = []
    if isinstance(node, list | tuple):
        for index, item in enumerate(cast("Sequence[object]", node)):
            initial.append(_Child(f"[{index}]", None, (index,), item))
    else:
        initial.append(_Child("", None, (), node))

    stack: list[tuple[_Child, _AncestorChain | None, bool]] = [(child, None, False) for child in reversed(initial)]
    while stack:
        child, ancestors, is_leave = stack.pop()
        if is_leave:
            yield WalkEvent(child.node, child.relation, _Ancestors(ancestors), child.field, child.indices, "leave")
            continue
        if not isinstance(child.node, _NODE_TYPES):
            continue
        yield WalkEvent(child.node, child.relation, _Ancestors(ancestors), child.field, child.indices, "enter")
        child_ancestors = _AncestorChain(child.node, ancestors)
        if emit_leave:
            stack.append((child, ancestors, True))
        if prune is not None and prune(child.node):
            continue
        entries = list(_iter_child_entries(child.node))
        for entry in reversed(entries):
            stack.append((entry, child_ancestors, False))


class NodeVisitor:
    """Dispatch to ``visit_<ClassName>`` and ``leave_<ClassName>`` methods.

    A subclass that overrides a ``visit_*`` method decides whether to descend
    by calling ``self.generic_visit(node)``. After the enter method returns,
    ``leave(node)`` dispatches to ``leave_<ClassName>`` when one exists, so a
    subclass can maintain a scope stack without writing its own recursion.

    Dispatch is recursive by design, because an override controls its own
    descent; :func:`walk` is the fully iterative API. Parsed ASTs are bounded by
    ``source_io.MAX_SOURCE_DEPTH``, so the dispatch stays inside the default
    recursion limit.
    """

    def visit(self, node: object) -> None:
        """Visit one node, dispatching on its concrete class name."""
        method: Callable[[object], None] | None = getattr(self, f"visit_{type(node).__name__}", None)
        if method is None:
            self.generic_visit(node)
        else:
            method(node)
        self.leave(node)

    def leave(self, node: object) -> None:
        """Run the ``leave_<ClassName>`` hook for ``node``, when defined."""
        method: Callable[[object], None] | None = getattr(self, f"leave_{type(node).__name__}", None)
        if method is not None:
            method(node)

    def generic_visit(self, node: object) -> None:
        """Visit every child of ``node`` in walker order."""
        for _relation, child in iter_child_nodes(node):
            self.visit(child)
