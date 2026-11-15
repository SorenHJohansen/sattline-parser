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
    "CoordBox",
    "CoordPair",
    "EnableClause",
    "FlagClause",
    "ModuleArguments",
    "ModuleInViewClause",
    "ModuleMarker",
    "PickButton",
    "PolygonPoint",
    "ProcedureCall",
    "ScaleSelector",
    "TailedClause",
    "ZoomLimits",
]

type CoordPair = tuple[float, float]
type CoordBox = tuple[CoordPair, CoordPair]


@dataclass(frozen=True)
class PolygonPoint:
    """One ``(x, y)`` pair of a polygon, with the tails written after each value.

    A coordinate may carry its own ``: InVar_ "X"`` tail or a nested
    ``ClippingBounds`` annotation. Keeping the two positions apart is what lets a
    consumer map a tail back to the coordinate it belongs to; the object's flat
    ``tails`` view still lists every tail once.
    """

    x: float
    y: float
    x_tails: tuple[Tail, ...] = ()
    y_tails: tuple[Tail, ...] = ()
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class Alignment:
    """A ``LeftAligned``, ``CenterAligned``, or ``RightAligned`` body line."""

    value: Literal["left", "center", "right"]
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
    """A bare interactor flag: a name plus an optional tail."""

    name: str
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
class ClippingClause:
    """A resolved ``ClippingBounds`` pair and the tails on its corners."""

    bounds: CoordBox = field(compare=False, metadata={"layout": True})
    tails: tuple[Tail, ...] = ()
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})
    #: The same tails as ``tails``, one group per corner in ``bounds`` order, so
    #: each one can be placed where it was written. Empty for a clause assembled
    #: without position information.
    corner_tails: tuple[tuple[Tail, ...], ...] = ()


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
class ModuleMarker:
    """A marker-only invocation argument, e.g. ``SymbolModule``."""

    kind: str
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


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
