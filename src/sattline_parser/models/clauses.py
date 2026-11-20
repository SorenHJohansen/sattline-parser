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
    "NestedClipping",
    "NestedClippingValue",
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
class NestedClippingValue:
    """One numeric value of a nested ``ClippingBounds = ...`` annotation.

    ``value`` is the written real and ``tail`` the binding written after it, so
    the pair is read together. The tail is the same object the owning
    coordinate's flat tail view holds.
    """

    value: float
    tail: Tail | None = None


@dataclass(frozen=True)
class NestedClipping:
    """A nested ``ClippingBounds = <values>`` annotation on one coordinate.

    The grammar attaches the annotation to a single coordinate value, so the
    values it carries sit beside the tails written after that value rather than
    replacing them. A parsed tree keeps the annotation here and the same tail
    objects in the coordinate's flat tail view; the walker emits each tail once
    from that view, which is also why this positional payload is not a walked
    node.
    """

    values: tuple[NestedClippingValue, ...] = ()

    @property
    def tails(self) -> tuple[Tail, ...]:
        """Every tail carried by the annotated values, in order."""
        return tuple(value.tail for value in self.values if value.tail is not None)


@dataclass(frozen=True)
class PolygonPoint:
    """One ``(x, y)`` pair of a polygon, with the tails written after each value.

    A coordinate may carry its own ``: InVar_ "X"`` tail or a nested
    ``ClippingBounds`` annotation. Keeping the two positions apart is what lets a
    consumer map a tail back to the coordinate it belongs to; the object's flat
    ``tails`` view still lists every tail once. ``x_clippings`` and
    ``y_clippings`` hold the nested annotations written after each value, in
    order, so the values they carry are not lost.
    """

    x: float
    y: float
    x_tails: tuple[Tail, ...] = ()
    y_tails: tuple[Tail, ...] = ()
    x_clippings: tuple[NestedClipping, ...] = ()
    y_clippings: tuple[NestedClipping, ...] = ()
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
    #: Nested ``ClippingBounds`` annotations on the corners, one group per corner
    #: in ``bounds`` order, matching ``corner_tails``.
    corner_clippings: tuple[tuple[NestedClipping, ...], ...] = ()


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
