"""Typed clause payloads for module headers, graphics, and interact objects.

Each grammar rule that used to return a ``{key: value}`` dictionary now returns
one of these frozen dataclasses. The rules compose: ``EnableClause`` carries its
own :data:`~sattline_parser.models.tails.Tail`, ``ColourSpec`` carries its width,
assignments, and style, and ``ModuleArguments`` carries everything the invocation
argument list accepted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from .expressions import SLExpression, VarRef
from .tails import Tail

if TYPE_CHECKING:
    from .ast_model import SourceSpan

__all__ = [
    "Alignment",
    "AssignClause",
    "ClippingClause",
    "ColourSpec",
    "CommonProperties",
    "CoordBox",
    "CoordPair",
    "EnableClause",
    "FlagClause",
    "Grid",
    "ModuleArguments",
    "ModuleInViewClause",
    "ModuleMarker",
    "ModuleOptions",
    "PickButton",
    "ProcedureCall",
    "ScaleSelector",
    "SeqLayers",
    "TailedClause",
    "TwoLayers",
    "ZoomLimits",
    "Zoomable",
]

type CoordPair = tuple[float, float]
type CoordBox = tuple[CoordPair, CoordPair]


@dataclass(frozen=True)
class Alignment:
    """A ``LeftAligned`` or ``RightAligned`` interactor body line."""

    value: Literal["left", "right"]
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class EnableClause:
    """``Enable_ = True|False`` with an optional ``InVar_``/expression tail."""

    enabled: bool
    tail: Tail | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class ModuleInViewClause:
    """``Module_In_View = True|False``, stored apart from ``Enable_``."""

    in_view: bool
    tail: Tail | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class AssignClause:
    """``Name = value`` with an optional tail, as used by interactors/headers."""

    name: str
    value: SLExpression
    tail: Tail | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class FlagClause:
    """A bare interactor flag: a name plus an optional literal and tail."""

    name: str
    extra: str | None = None
    tail: Tail | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class TailedClause:
    """A ``Keyword = value`` clause: width, format string, colour, or fraction."""

    key: str
    value: SLExpression
    tail: Tail | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class ColourSpec:
    """One ``OutlineColour`` or ``FillColour`` block."""

    kind: Literal["outline", "fill"]
    width: TailedClause | None = None
    assignments: tuple[TailedClause, ...] = ()
    style: TailedClause | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})

    @property
    def tails(self) -> tuple[Tail, ...]:
        """Every tail carried by the width, assignment, or style clauses."""
        parts = [self.width, self.style, *self.assignments]
        return tuple(part.tail for part in parts if part is not None and part.tail is not None)


@dataclass(frozen=True)
class CommonProperties:
    """The ``common_properties`` run shared by graphics objects."""

    layer: int | None = None
    enable: EnableClause | None = None
    colours: tuple[ColourSpec, ...] = ()

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
class ClippingClause:
    """A resolved ``ClippingBounds`` pair and the tails on its corners."""

    bounds: CoordBox
    tails: tuple[Tail, ...] = ()
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class ScaleSelector:
    """The bare ``Relative_``/``Abs_`` interactor selector."""

    mode: Literal["relative", "abs"]
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class PickButton:
    """``IntObjPickButton = "..."`` with its optional ``VarName`` marker.

    ``value`` is the written string. ``reference`` is the variable it names when
    the ``VarName`` postfix is present, and ``None`` for literal text.
    """

    value: str
    reference: VarRef | None = None
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class ProcedureCall:
    """A ``ComButProc_`` procedure name and its arguments."""

    name: str
    args: tuple[Tail, ...] = ()
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class ZoomLimits:
    """``ZoomLimits = <min> <max>``."""

    minimum: float
    maximum: float
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class Zoomable:
    """The ``Zoomable`` marker argument."""


@dataclass(frozen=True)
class ModuleMarker:
    """A marker-only invocation argument, e.g. ``SymbolModule``."""

    kind: str
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class TwoLayers:
    """``Two_Layers_ LayerLimit_ = <real>``."""

    layer_limit: float


@dataclass(frozen=True)
class Grid:
    """``Grid = <real>``."""

    spacing: float


@dataclass(frozen=True)
class SeqLayers:
    """A ``seq_layers`` payload: one real or a layer mapping."""

    value: float | dict[str, float]


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
        if isinstance(option, int | float):
            return cls(grid=float(option))
        return cls()

    def merge(self, other: ModuleOptions) -> ModuleOptions:
        """Return the combination, letting ``other`` win where it sets a field."""
        return ModuleOptions(
            layer_limit=other.layer_limit if other.layer_limit is not None else self.layer_limit,
            zoom_limits=other.zoom_limits if other.zoom_limits is not None else self.zoom_limits,
            zoomable=self.zoomable or other.zoomable,
            grid=other.grid if other.grid is not None else self.grid,
        )


@dataclass(frozen=True)
class ModuleArguments:
    """The typed content of a module invocation's argument list."""

    layer: int | None = None
    enable: EnableClause | None = None
    module_in_view: ModuleInViewClause | None = None
    zoom_limits: ZoomLimits | None = None
    zoomable: bool = False
    markers: tuple[ModuleMarker, ...] = ()
    assigns: tuple[AssignClause, ...] = ()
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})
