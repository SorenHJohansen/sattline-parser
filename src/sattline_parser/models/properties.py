"""Typed property maps carried by graphics, interact, and module-definition nodes.

The parser writes a small, fixed set of keys; these ``TypedDict`` definitions
name them so a reader no longer has to guess whether ``properties["coords"]`` is
one pair or a list of them.
"""

from __future__ import annotations

from typing import TypedDict

from .clauses import (
    AssignClause,
    ColourSpec,
    CoordBox,
    CoordPair,
    EnableClause,
    FlagClause,
    ProcedureCall,
)
from .tails import Tail

__all__ = [
    "GraphProperties",
    "InteractProperties",
    "ModuleDefProperties",
    "graph_properties",
    "interact_properties",
    "module_def_properties",
]


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


class InteractProperties(TypedDict, total=False):
    """Properties of one ``InteractObject``."""

    #: ``KEY_COORDS``
    coords: list[CoordPair | CoordBox] | None
    #: ``KEY_TAILS``
    tails: list[Tail]
    #: ``KEY_BODY``
    body: list[object] | None
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
