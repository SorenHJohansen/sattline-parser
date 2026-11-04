"""Typed tail nodes attached to coordinates, headers, and property clauses.

The grammar offers two tail shapes:

* ``":" (InVar_ | OutVar_) (value | litstring_tail)`` carries a literal or a
  quoted symbol, and the direction is part of the meaning.
* the bare ``expression`` alternative carries a computed value.

Both used to arrive as untyped ``str``/``Tree`` items. They are modelled here so
every consumer can tell a bound tail from an expression without sniffing Lark
trees. A tail carries the source span of the rule that produced it, and a bound
tail exposes the written name through :attr:`VarTail.bound_name`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeGuard

from .expressions import BinOp, BoolOp, Compare, FuncCall, NotOp, SLExpression, TernaryOp, UnaryOp, VarRef

if TYPE_CHECKING:
    from .ast_model import SourceSpan

__all__ = [
    "ClipValue",
    "CoordinateClipping",
    "LitStringTail",
    "Tail",
    "VarTail",
    "is_expression_tail",
    "tail_list",
]


@dataclass(frozen=True)
class LitStringTail:
    """A ``LitString "Name"`` tail: the symbol is quoted, not a variable path."""

    keyword: str
    text: str
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})


@dataclass(frozen=True)
class VarTail:
    """A ``: InVar_ ...`` or ``: OutVar_ ...`` tail.

    ``direction`` records which prefix was written, so a consumer no longer has
    to read it back from a Lark tree node name. :attr:`bound_name` is the name
    the tail binds, or ``None`` when the tail holds a non-name literal.
    """

    direction: Literal["in", "out"]
    value: str | bool | int | float | LitStringTail
    span: SourceSpan | None = field(default=None, compare=False, metadata={"layout": True})

    @property
    def bound_name(self) -> str | None:
        """The written name this tail binds, or ``None`` for a literal value.

        A ``str`` value is the quoted name the source wrote. A
        ``LitStringTail`` is a quoted symbol; its ``text`` is the name. A
        boolean or numeric value binds no name.
        """
        value = self.value
        if isinstance(value, LitStringTail):
            return value.text
        if isinstance(value, str):
            return value
        return None


@dataclass(frozen=True)
class ClipValue:
    """One numeric value in a nested ``ClippingBounds = ...`` coordinate tail."""

    value: float
    tail: Tail | None = None


@dataclass(frozen=True)
class CoordinateClipping:
    """A nested ``ClippingBounds = <values>`` annotation on a coordinate.

    The form still belongs to the coordinate position; its per-value tails are
    folded into the coordinate's flat tail list.
    """

    values: tuple[ClipValue, ...]

    @property
    def tails(self) -> tuple[Tail, ...]:
        return tuple(value.tail for value in self.values if value.tail is not None)


#: Every tail shape a coordinate, header, or clause can carry.
type Tail = SLExpression | VarTail | LitStringTail

_LITERAL_TAIL_TYPES = (bool, int, float, str)
_EXPRESSION_NODE_TYPES = (VarRef, BoolOp, NotOp, Compare, BinOp, UnaryOp, FuncCall, TernaryOp)


def tail_list() -> list[Tail]:
    """Empty tail list; the default factory for tail-bearing model fields."""
    return []


def is_expression_tail(value: object) -> TypeGuard[SLExpression]:
    """True for a computed tail: a literal or an expression node.

    False for the bound ``InVar_``/``OutVar_`` wrappers, which carry a symbol or
    literal rather than a computed value.
    """
    if isinstance(value, VarTail | LitStringTail):
        return False
    return isinstance(value, _LITERAL_TAIL_TYPES + _EXPRESSION_NODE_TYPES)
