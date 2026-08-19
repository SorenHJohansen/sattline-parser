"""Shared helpers and type aliases for module transformer mixins."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Literal, cast

from lark import Tree
from lark.visitors import v_args as _lark_v_args  # pyright: ignore[reportUnknownVariableType]

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import FrameModule, ModuleTypeInstance, SingleModule, SourceSpan, VarRef

TransformerTree = Tree[Any]
TransformerItem = object
ModuleInvocation = SingleModule | FrameModule | ModuleTypeInstance
type VArgsDecorator = Callable[[object], object]
_V_ARGS_FACTORY = cast(Callable[..., VArgsDecorator], _lark_v_args)

CoordPair = tuple[float, float]
CoordBox = tuple[CoordPair, CoordPair]


@dataclass(frozen=True)
class InterimCoords:
    """Coordinate payload passed between layout/graphics transformer rules.

    Replaces the previous ``{KEY_COORDS: ..., KEY_TAILS: ...}`` /
    ``{TREE_TAG_INVOKE_COORD: ..., KEY_TAILS: ...}`` dict protocol: a rule that
    produces coordinates (:func:`coordinates`, :func:`origo_size_pair`,
    :func:`invoke_coord`) returns an ``InterimCoords`` that downstream rules
    unpack. ``coords`` is a coordinate pair ``(x, y)``, a coordinate box
    ``((x, y), (w, h))``, or a five-value invocation coordinate.
    """

    coords: CoordPair | CoordBox | tuple[float, float, float, float, float]
    tails: list[object] | None = None


@dataclass(frozen=True)
class GroupConnInfo:
    """``scan_group`` payload: an optional group connection and its global flag."""

    groupconn: VarRef | None
    is_global: bool


@dataclass(frozen=True)
class CodeBlockPayload:
    """One SFC code block (enter/active/exit) with its flattened statements."""

    kind: Literal["enter", "active", "exit"]
    items: tuple[object, ...]


def v_args(*args: Any, **kwargs: Any) -> VArgsDecorator:
    return _V_ARGS_FACTORY(*args, **kwargs)


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
    if not all(isinstance(value, int | float) for value in values):
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
    "CodeBlockPayload",
    "CoordBox",
    "CoordPair",
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
