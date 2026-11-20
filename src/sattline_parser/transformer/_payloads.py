"""Interim payloads produced by the transformer's rule methods.

These are not AST nodes. A rule method returns one of them while it assembles a
unit, and the consuming rule folds its content into a real node field. A parsed
tree never contains one, which is why they live beside the transformer rather
than on the model surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from sattline_parser.models.ast_model import GraphObject
from sattline_parser.models.clauses import ColourSpec, EnableClause, ZoomLimits
from sattline_parser.models.tails import Tail

__all__ = [
    "ClipValue",
    "CommonProperties",
    "CoordinateClipping",
    "Grid",
    "ModuleOptions",
    "TwoLayers",
    "Zoomable",
]


@dataclass(frozen=True)
class CommonProperties:
    """The ``common_properties`` run shared by graphics objects.

    ``connection_node`` holds the bare ``ConnectionNode`` marker the run allows.
    It has no coordinates, unlike a text object's ``ConnectionNode (x, y)``
    clause, so the formatter writes it back as the bare keyword.
    """

    layer: int | None = None
    enable: EnableClause | None = None
    colours: tuple[ColourSpec, ...] = ()
    connection_node: GraphObject | None = None

    @property
    def tails(self) -> tuple[Tail, ...]:
        """Every tail carried by the enable or colour clauses."""
        tails: list[Tail] = []
        if self.enable is not None and self.enable.tail is not None:
            tails.append(self.enable.tail)
        for colour in self.colours:
            tails.extend(colour.tails)
        return tuple(tails)


@dataclass(frozen=True)
class Zoomable:
    """The ``Zoomable`` marker argument."""


@dataclass(frozen=True)
class TwoLayers:
    """``Two_Layers_ LayerLimit_ = <real>``, the zoom level that switches to layer 2."""

    layer_limit: float


@dataclass(frozen=True)
class Grid:
    """``Grid = <real>``."""

    spacing: float


@dataclass(frozen=True)
class ModuleOptions:
    """Every ``moduledef_option`` merged into one payload."""

    layer_limit: float | None = None
    zoom_limits: ZoomLimits | None = None
    zoomable: bool = False
    grid: float | None = None

    @classmethod
    def from_option(cls, option: object) -> ModuleOptions:
        """Wrap one typed option rule result as a ``ModuleOptions`` delta."""
        if isinstance(option, TwoLayers):
            return cls(layer_limit=option.layer_limit)
        if isinstance(option, ZoomLimits):
            return cls(zoom_limits=option)
        if isinstance(option, Zoomable):
            return cls(zoomable=True)
        if isinstance(option, Grid):
            return cls(grid=option.spacing)
        if isinstance(option, (int, float)):
            return cls(grid=float(option))
        return cls()

    def merge(self, other: ModuleOptions) -> ModuleOptions:
        """Return the combination, letting ``other`` win where it sets a field.

        ``layer_limit``, ``zoom_limits``, and ``grid`` are singular options, so
        two written values for one of them are ambiguous. The merge rejects the
        pair instead of letting the later clause win silently. ``zoomable`` is a
        marker, so a repeat is idempotent.
        """
        if other.layer_limit is not None and self.layer_limit is not None:
            raise ValueError("module definition has more than one Two_Layers_/LayerLimit_ option")
        if other.zoom_limits is not None and self.zoom_limits is not None:
            raise ValueError("module definition has more than one ZoomLimits option")
        if other.grid is not None and self.grid is not None:
            raise ValueError("module definition has more than one Grid option")
        return ModuleOptions(
            layer_limit=other.layer_limit if other.layer_limit is not None else self.layer_limit,
            zoom_limits=other.zoom_limits if other.zoom_limits is not None else self.zoom_limits,
            zoomable=self.zoomable or other.zoomable,
            grid=other.grid if other.grid is not None else self.grid,
        )


@dataclass(frozen=True)
class ClipValue:
    """One numeric value in a nested ``ClippingBounds = ...`` coordinate tail."""

    value: float
    tail: Tail | None = None


@dataclass(frozen=True)
class CoordinateClipping:
    """A nested ``ClippingBounds = <values>`` annotation on a coordinate.

    The form still belongs to the coordinate position: its per-value tails are
    folded into the coordinate's flat tail list, and the values themselves become
    a :class:`~sattline_parser.models.clauses.NestedClipping` on the coordinate
    they follow, so a formatter can write them back.
    """

    values: tuple[ClipValue, ...]

    @property
    def tails(self) -> tuple[Tail, ...]:
        return tuple(value.tail for value in self.values if value.tail is not None)
