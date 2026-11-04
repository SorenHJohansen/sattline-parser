"""Typed property maps carried by graphics, interact, and module-definition nodes.

The parser writes a small, fixed set of keys; these ``TypedDict`` definitions
name them so a reader no longer has to guess whether ``properties["coords"]`` is
one pair or a list of them.

``InteractProperties.body`` is a typed union. Each entry is a clause payload, a
tail, a literal (the ``layer_info`` value), an ``Alignment``, or a
``CodeComment``. No grammar tree reaches a caller.
"""

from __future__ import annotations

from typing import TypedDict

from .clauses import (
    Alignment,
    AssignClause,
    ColourSpec,
    CoordBox,
    CoordPair,
    EnableClause,
    FlagClause,
    PickButton,
    ProcedureCall,
    ScaleSelector,
    TailedClause,
)
from .expressions import CodeComment
from .tails import Tail

__all__ = [
    "GraphProperties",
    "InteractBodyEntry",
    "InteractProperties",
    "ModuleDefProperties",
    "graph_properties",
    "interact_properties",
    "module_def_properties",
]

#: One entry of :attr:`InteractProperties.body`, in source order.
#:
#: ``int`` is the ``layer_info`` payload. ``Tail`` covers a literal, a bound
#: ``VarTail``/``LitStringTail``, or a computed expression. ``Alignment`` is the
#: ``LeftAligned``/``RightAligned`` marker, and ``CodeComment`` is a preserved
#: comment. The union is closed: a raw Lark tree is never a body entry.
type InteractBodyEntry = (
    int
    | Tail
    | Alignment
    | AssignClause
    | ColourSpec
    | EnableClause
    | FlagClause
    | PickButton
    | ScaleSelector
    | TailedClause
    | CodeComment
)


class GraphProperties(TypedDict, total=False):
    """Properties of one ``GraphObject``."""

    #: ``KEY_COORDS``
    coords: CoordPair | CoordBox
    #: ``KEY_SEGMENT_POINT``
    segment_point: CoordPair
    #: ``KEY_POLYGON_TYPE``
    polygon_type: list[str]
    #: ``KEY_TAILS``
    tails: list[Tail]
    #: ``KEY_LAYER``
    layer: int
    #: ``KEY_COLOURS``
    colours: list[ColourSpec]
    #: ``KEY_TEXT_VARS``
    text_vars: list[str]
    #: ``KEY_ENABLE``
    enable: bool
    #: ``KEY_ENABLE_TAIL``
    enable_tail: Tail


class InteractProperties(TypedDict, total=False):
    """Properties of one ``InteractObject``."""

    #: ``KEY_COORDS``
    coords: list[CoordPair | CoordBox] | None
    #: ``KEY_TAILS``
    tails: list[Tail]
    #: ``KEY_BODY``
    body: list[InteractBodyEntry] | None
    #: ``KEY_PROCEDURE``
    procedure: ProcedureCall
    #: ``KEY_LAYERS``
    layers: list[int]
    #: ``KEY_ASSIGNS``
    assigns: list[AssignClause]
    #: ``KEY_ENABLES``
    enables: list[EnableClause]
    #: ``KEY_FLAGS``
    flags: list[FlagClause]
    #: ``KEY_COLOURS``
    colours: list[ColourSpec]


class ModuleDefProperties(TypedDict, total=False):
    """Properties of one ``ModuleDef`` block."""

    #: ``KEY_TAILS``
    tails: list[Tail]


def graph_properties() -> GraphProperties:
    return {}


def interact_properties() -> InteractProperties:
    return {}


def module_def_properties() -> ModuleDefProperties:
    return {}
