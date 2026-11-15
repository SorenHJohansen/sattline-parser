"""Shared helpers and type aliases for module transformer mixins."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Final, Literal, ParamSpec, TypeVar, cast

from lark import Tree
from lark.visitors import v_args as _lark_v_args  # pyright: ignore[reportUnknownVariableType]

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import CodeItem, FrameModule, ModuleTypeInstance, SingleModule, SourceSpan, VarRef
from sattline_parser.models.clauses import CoordBox, CoordPair
from sattline_parser.models.tails import Tail

TransformerTree = Tree[Any]
TransformerItem = object
ModuleInvocation = SingleModule | FrameModule | ModuleTypeInstance

#: Terminal types the shared transformer helpers inspect by name.
OUTVAR_TOKEN: Final = "OUTVAR_PREFIX"  # nosec B105 - grammar token literal, not a credential
INVAR_TOKEN: Final = "INVAR_PREFIX"
PREFIX_TOKENS: Final = (INVAR_TOKEN, OUTVAR_TOKEN)

_P = ParamSpec("_P")
_R = TypeVar("_R")


@dataclass(frozen=True)
class CoordTail:
    """One ``coord_invar_tail`` payload: a tail after a coordinate REAL.

    Lark drops the anonymous commas, so a rule that reads several coordinates
    cannot tell a coordinate REAL from a numeric literal tail by position alone.
    Wrapping every ``coord_invar_tail`` result makes the split structural: the
    remaining bare numbers are exactly the coordinate values.
    """

    value: Tail


@dataclass(frozen=True)
class InterimCoords:
    """Coordinate payload passed between layout/graphics transformer rules.

    A rule that produces coordinates (:func:`coordinates`,
    :func:`origo_size_pair`, :func:`invoke_coord`) returns an ``InterimCoords``
    that downstream rules unpack. ``coords`` is a coordinate pair ``(x, y)``, a
    coordinate box ``((x, y), (w, h))``, or a five-value invocation coordinate.
    """

    coords: CoordPair | CoordBox | tuple[float, float, float, float, float]
    #: Every tail the coordinate run carried, flattened. This is the flat view
    #: the graph object keeps under ``tails``.
    tails: list[Tail] | None = None
    #: Per-coordinate tails, index-aligned with the numbers in ``coords`` when the
    #: run spells one coordinate pair. ``None`` means the rule did not record the
    #: split, as for a five-value invocation coordinate.
    coord_tails: tuple[tuple[Tail, ...], ...] | None = None


@dataclass(frozen=True)
class PrivateMarker:
    """The ``PRIVATE_`` keyword on a module type definition."""


@dataclass(frozen=True)
class GlobalKeyword:
    """The written ``GLOBAL`` keyword.

    A dedicated payload, not the boolean ``True``: a literal source value is also
    a bool, so a shared representation would let ``Name => True`` be read as the
    keyword and lose the value. Identity comparison keeps the two apart.
    """


#: The one ``GLOBAL`` payload every keyword occurrence produces.
GLOBAL_KEYWORD = GlobalKeyword()


@dataclass(frozen=True)
class GroupConnInfo:
    """``scan_group`` payload: an optional group connection and its global flag."""

    groupconn: VarRef | None
    is_global: bool


@dataclass(frozen=True)
class CodeBlockPayload:
    """One SFC code block (enter/active/exit) with its flattened statements."""

    kind: Literal["enter", "active", "exit"]
    items: tuple[CodeItem, ...]


@dataclass(frozen=True)
class TextContent:
    """One ``text_content`` payload and the source span of its STRING token.

    The text is not stored on the graph object; it only spells the following
    ``VarName`` reference. Keeping the span here lets that reference carry a
    real position.
    """

    text: str
    span: SourceSpan | None = None


def v_args(*args: object, **kwargs: object) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Typed passthrough for Lark's ``v_args`` decorator factory.

    Lark annotates the decorated value as ``Callable[[object], object]``, which
    erases the decorated method's signature, so a wrong ``(meta, children)``
    order or a wrong return type would pass strict mode. ``ParamSpec`` keeps the
    declared signature, which is exactly how the ``meta=True`` rule methods are
    written.
    """
    factory = cast(Callable[..., Callable[[Callable[_P, _R]], Callable[_P, _R]]], _lark_v_args)
    return factory(*args, **kwargs)


def tree_children(tree: TransformerTree) -> list[TransformerItem]:
    return cast(list[TransformerItem], tree.children)


def submodule_children(children: Iterable[TransformerItem]) -> list[ModuleInvocation]:
    submodules: list[ModuleInvocation] = []
    for child in children:
        if isinstance(child, list):
            nested = cast(list[TransformerItem], child)
            submodules.extend(
                [item for item in nested if isinstance(item, (SingleModule, FrameModule, ModuleTypeInstance))]
            )
        elif isinstance(child, (SingleModule, FrameModule, ModuleTypeInstance)):
            submodules.append(child)
    return submodules


def float_tuple(raw: object, size: Literal[2, 5]) -> tuple[float, ...] | None:
    if not isinstance(raw, tuple):
        return None
    raw_values = cast(tuple[object, ...], raw)
    if len(raw_values) < size:
        return None
    values = raw_values[:size]
    if not all(isinstance(value, (int, float)) for value in values):
        return None
    return tuple(float(cast(int | float, value)) for value in values)


def groupconn_value(info: GroupConnInfo | None) -> VarRef | None:
    if info is None:
        return None
    return info.groupconn


def coord_pair(raw: object) -> tuple[float, float] | None:
    values = float_tuple(raw, 2)
    if values is None:
        return None
    return cast(tuple[float, float], values)


def meta_span(meta: Any) -> SourceSpan | None:
    """Extract source span from Lark meta.

    Returns a span carrying character offsets (``start``/``end``) plus the
    one-based line/column of the span start. Requires ``start_pos``/``end_pos``,
    which Lark populates when ``propagate_positions`` is enabled; returns
    ``None`` when the meta lacks them.
    """
    line = getattr(meta, "line", None)
    column = getattr(meta, "column", None)
    start_pos = getattr(meta, "start_pos", None)
    end_pos = getattr(meta, "end_pos", None)
    if not isinstance(line, int) or not isinstance(column, int):
        return None
    if not isinstance(start_pos, int) or not isinstance(end_pos, int):
        return None
    return SourceSpan(start=start_pos, end=end_pos, line=line, column=column)


def flatten_items(items: Iterable[TransformerItem]) -> Iterator[TransformerItem]:
    """Yield flat stream of items from possibly nested lists and Trees."""
    for it in items:
        if isinstance(it, list):
            yield from flatten_items(cast(list[TransformerItem], it))
        elif isinstance(it, Tree) and it.data in (
            const.TREE_TAG_BASE_MODULE_BODY,
            const.TREE_TAG_MODULE_BODY,
            const.TREE_TAG_MODULEDEF_BLOCK,
        ):
            tree = cast(TransformerTree, it)
            yield from flatten_items(cast(list[TransformerItem], tree.children))
        else:
            yield it


__all__ = [
    "GLOBAL_KEYWORD",
    "CodeBlockPayload",
    "CoordBox",
    "CoordPair",
    "CoordTail",
    "GlobalKeyword",
    "GroupConnInfo",
    "InterimCoords",
    "ModuleInvocation",
    "TransformerItem",
    "TransformerTree",
    "coord_pair",
    "flatten_items",
    "float_tuple",
    "groupconn_value",
    "meta_span",
    "submodule_children",
    "tree_children",
    "v_args",
]
