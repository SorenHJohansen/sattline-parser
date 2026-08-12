"""Typed AST nodes for SattLine expressions and statements.

All nodes are frozen dataclasses — safe to hash, compare, and serialise.

Expression type hierarchy
--------------------------
SLExpression = VarRef | bool | IntLiteral | FloatLiteral | str
             | BoolOp | NotOp | Compare | BinOp | UnaryOp | FuncCall | TernaryOp

  Primitive leaves (already typed):
    bool, IntLiteral, FloatLiteral, str (string literal)

  VarRef        — variable or dotted field reference, e.g. "Pump.State"
  BoolOp        — n-ary OR / AND: BoolOp("OR", (a, b, c))
  NotOp         — logical NOT
  Compare       — single binary comparison: a < b
  BinOp         — single binary arithmetic: a + b  (left-associative fold)
  UnaryOp       — unary + or -
  FuncCall      — built-in or user call: GetTime(Arg1, Arg2)
  TernaryOp     — IF cond THEN e (ELSIF cond THEN e)* ELSE e ENDIF

Statement type hierarchy
-------------------------
SLStmt = Assignment | FuncCallStmt | IfStmt
       (+ CodeComment from ast_model, kept as CodeItem alias there)

  Assignment    — variable = expression
  FuncCallStmt  — call as standalone statement (no assignment target)
  IfStmt        — IF / ELSIF / ELSE / ENDIF control flow
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "Assignment",
    "BinOp",
    "BoolOp",
    "Compare",
    "FuncCall",
    "FuncCallStmt",
    "IfStmt",
    "NotOp",
    "SLExpression",
    "SLStmt",
    "TernaryOp",
    "UnaryOp",
    "VarRef",
]


# ---------------------------------------------------------------------------
# Variable reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VarRef:
    """A variable or dotted field reference, optionally with :Old / :New suffix.

    ``name`` is the full dotted path, e.g. ``"Sensor.Calibrated"`` or
    ``"Counter"``; ``state`` is ``"old"``, ``"new"``, or ``None``.
    """

    name: str
    state: str | None = None


# ---------------------------------------------------------------------------
# Expression nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoolOp:
    """N-ary logical OR or AND.  ``operands`` always contains ≥ 2 items."""

    op: Literal["OR", "AND"]
    operands: tuple[SLExpression, ...]


@dataclass(frozen=True)
class NotOp:
    """Logical NOT."""

    operand: SLExpression


@dataclass(frozen=True)
class Compare:
    """Binary comparison: left op right."""

    left: SLExpression
    op: str  # one of "<", ">", "==", "<>", "<=", ">="
    right: SLExpression


@dataclass(frozen=True)
class BinOp:
    """Binary arithmetic or bitwise operator (left-associative fold).

    ``a + b - c`` becomes ``BinOp(BinOp(a, "+", b), "-", c)``.
    """

    left: SLExpression
    op: str  # one of "+", "-", "*", "/"
    right: SLExpression


@dataclass(frozen=True)
class UnaryOp:
    """Unary plus or minus."""

    op: Literal["+", "-"]
    operand: SLExpression


@dataclass(frozen=True)
class FuncCall:
    """Function or built-in call.  ``args`` may be empty."""

    name: str
    args: tuple[SLExpression, ...]


@dataclass(frozen=True)
class TernaryOp:
    """Expression-context IF / ELSIF / ELSE / ENDIF.

    ``branches`` is a tuple of (condition, then_expression) pairs; the first
    branch covers the ``IF`` clause, subsequent branches cover ``ELSIF``
    clauses.  ``else_expr`` is the ``ELSE`` expression (always present for a
    valid SattLine program).
    """

    branches: tuple[tuple[SLExpression, SLExpression], ...]
    else_expr: SLExpression | None


# Convenience type alias covering every possible expression value.
type SLExpression = (
    VarRef
    | bool
    | int
    | float
    | str
    | BoolOp
    | NotOp
    | Compare
    | BinOp
    | UnaryOp
    | FuncCall
    | TernaryOp
)


# ---------------------------------------------------------------------------
# Statement nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Assignment:
    """Variable assignment: ``target = value``."""

    target: VarRef
    value: SLExpression


@dataclass(frozen=True)
class FuncCallStmt:
    """A function call used as a statement (no assignment target)."""

    call: FuncCall


@dataclass(frozen=True)
class IfStmt:
    """Imperative IF / ELSIF / ELSE / ENDIF.

    ``branches`` — tuple of (condition, body) pairs.  First pair = ``IF``
    clause; subsequent = ``ELSIF`` clauses.  Body items are
    ``Assignment | FuncCallStmt | IfStmt | CodeComment``.
    ``else_block`` — the ``ELSE`` body, or ``None`` if absent.
    """

    branches: tuple[tuple[SLExpression, tuple[Any, ...]], ...]
    else_block: tuple[Any, ...] | None


# Convenience type alias for statement nodes (CodeComment excluded here
# to avoid circular import; use CodeItem from ast_model for the full set).
type SLStmt = Assignment | FuncCallStmt | IfStmt
