"""Formatting helpers for AST models."""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol, TypeGuard

if TYPE_CHECKING:
    from ..models._ast_model_support import InitValue
    from ..models.ast_model import CodeItem
from ..models.ast_model import Variable
from ..models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    NotOp,
    TernaryOp,
    UnaryOp,
    VarRef,
)

_DEFAULT_INDENT = "    "

#: Source spelling of the ``:Old`` / ``:New`` reference suffixes. ``VarRef``
#: stores the folded form, so the formatter maps it back to the written form.
_STATE_SPELLINGS = {"old": "Old", "new": "New"}

__all__ = ["format_expr", "format_list", "format_optional", "format_seq_nodes"]


class _VariableLike(Protocol):
    name: str
    datatype: str
    global_var: bool | None
    const: bool | None
    state: bool | None
    init_value: InitValue | None
    description: str | None


def _is_variable_like(value: object) -> TypeGuard[_VariableLike]:
    return isinstance(value, Variable)


def _quote_string(value: str) -> str:
    """Render a string literal the way the source spells it.

    SattLine quotes strings with ``"`` and escapes an inner quote by doubling
    it, so the rendered text parses back to the same value.
    """
    return '"' + value.replace('"', '""') + '"'


def format_list(
    items: Sequence[object],
    indent: str = _DEFAULT_INDENT,
    align_variables: bool = True,
    inline_if_singleline: bool = False,
) -> str:
    if not items:
        return "[]"

    if align_variables:
        variable_items = [item for item in items if _is_variable_like(item)]
        if len(variable_items) == len(items):
            name_w = max(len(repr(item.name)) for item in variable_items)
            dtype_w = max(len(repr(item.datatype)) for item in variable_items)
            global_w = max(len(str(item.global_var)) for item in variable_items)
            const_w = max(len(str(item.const)) for item in variable_items)
            state_w = max(len(str(item.state)) for item in variable_items)
            init_w = max(len(repr(item.init_value)) for item in variable_items)
            desc_w = max(len(repr(item.description)) for item in variable_items)

            lines: list[str] = []
            for item in variable_items:
                lines.append(
                    indent + f"Name: {item.name!r:<{name_w}} , "
                    f"Datatype: {item.datatype!r:<{dtype_w}}, "
                    f"Global: {item.global_var!s:<{global_w}}, "
                    f"Const: {item.const!s:<{const_w}}, "
                    f"State: {item.state!s:<{state_w}}, "
                    f"Init_value : {item.init_value!r:<{init_w}}, "
                    f"Description: {item.description!r:<{desc_w}}"
                )
            return "[\n" + "\n".join(lines) + "]"

    rendered_items = [str(item) for item in items]
    if inline_if_singleline and all("\n" not in item for item in rendered_items):
        return "[" + ", ".join(rendered_items) + "]"
    indented = [textwrap.indent(item, indent) for item in rendered_items]
    return "[\n" + "\n".join(indented) + "]"


def format_optional(obj: object) -> str:
    return "None" if obj is None else str(obj)


def _branch_block(
    branches: Sequence[tuple[object, Sequence[object]]],
    *,
    indent: str,
    else_block: Sequence[object] | None,
) -> str:
    """Render one IF/ELSIF/THEN/ELSE/ENDIF chain.

    Shared by ``IfStmt`` (statement bodies) and ``TernaryOp`` (expression
    bodies), which only differ in what each branch contains.
    """
    lines: list[str] = []
    for index, (cond, body) in enumerate(branches):
        lines.append(f"{'IF' if index == 0 else 'ELSIF'} {format_expr(cond, indent)}")
        lines.append("THEN")
        lines.extend(textwrap.indent(format_expr(stmt, indent), indent) for stmt in body)
    if else_block is not None:
        lines.append("ELSE")
        lines.extend(textwrap.indent(format_expr(stmt, indent), indent) for stmt in else_block)
    lines.append("ENDIF")
    return "\n".join(lines)


def _precedence(expr: object) -> int:
    """Binding strength of an expression node, matching the grammar.

    Higher binds tighter. The order is the one documented in
    ``docs/grammar.md``: ternary, OR, AND, NOT, comparison, additive,
    multiplicative, unary, term.
    """
    if isinstance(expr, TernaryOp):
        return 1
    if isinstance(expr, BoolOp):
        return 2 if expr.op.upper() == "OR" else 3
    if isinstance(expr, NotOp):
        return 4
    if isinstance(expr, Compare):
        return 5
    if isinstance(expr, BinOp):
        return 7 if expr.op in {"*", "/"} else 6
    if isinstance(expr, UnaryOp):
        return 8
    return 9


def _needs_parentheses(expr: object, parent_precedence: int, parent_op: str | None) -> bool:
    """Whether *expr* must be wrapped to keep its tree under its parent."""
    if isinstance(expr, BinOp):
        # ``BinOp`` always renders itself parenthesised, so it is already a
        # complete parenthesised expression at every parent.
        return False
    precedence = _precedence(expr)
    if precedence < parent_precedence:
        return True
    if precedence > parent_precedence:
        return False
    if isinstance(expr, BoolOp) and parent_op is not None and expr.op.upper() == parent_op.upper():
        # A chain of one operator is n-ary in the AST. Parentheses are what
        # preserve a deliberately nested same-operator node.
        return True
    # Comparison is non-associative and the grammar admits only one operator.
    return isinstance(expr, Compare)


def _format_child(expr: object, indent: str, parent_precedence: int, parent_op: str | None) -> str:
    text = _format_expr(expr, indent, parent_precedence=parent_precedence, parent_op=parent_op)
    return f"({text})" if _needs_parentheses(expr, parent_precedence, parent_op) else text


def format_expr(expr: object, indent: str = _DEFAULT_INDENT) -> str:
    """Pretty-print nested expressions and statements in a SattLine-like format.

    Expression children are parenthesised by precedence, so the output parses
    back to the same tree rather than to the precedence the source happened to
    write.
    """
    return _format_expr(expr, indent, parent_precedence=0, parent_op=None)


def _format_expr(expr: object, indent: str, *, parent_precedence: int, parent_op: str | None) -> str:
    # Typed nodes are rendered by their own type; anything unhandled falls back
    # to ``str`` at the end.
    if isinstance(expr, VarRef):
        state = None if expr.state is None else _STATE_SPELLINGS.get(expr.state, expr.state)
        return expr.name if state is None else f"{expr.name}:{state}"

    if isinstance(expr, Assignment):
        return (
            f"{_format_expr(expr.target, indent, parent_precedence=0, parent_op=None)} = "
            f"{_format_expr(expr.value, indent, parent_precedence=0, parent_op=None)}"
        )

    if isinstance(expr, FuncCallStmt):
        return _format_expr(expr.call, indent, parent_precedence=0, parent_op=None)

    if isinstance(expr, IfStmt):
        return _branch_block(expr.branches, indent=indent, else_block=expr.else_block)

    if isinstance(expr, BoolOp):
        precedence = _precedence(expr)
        parts = [_format_child(op, indent, precedence, expr.op) for op in expr.operands]
        sep = f" {expr.op} \n"
        return sep.join(parts)

    if isinstance(expr, NotOp):
        return f"NOT({_format_expr(expr.operand, indent, parent_precedence=0, parent_op=None)})"

    if isinstance(expr, Compare):
        left = _format_child(expr.left, indent, 5, None)
        right = _format_child(expr.right, indent, 5, None)
        return f"{left} {expr.op} {right}"

    if isinstance(expr, BinOp):
        precedence = _precedence(expr)
        left = _format_child(expr.left, indent, precedence, None)
        right = _format_child(expr.right, indent, precedence, None)
        return f"({left} {expr.op} {right})"

    if isinstance(expr, UnaryOp):
        operand = _format_child(expr.operand, indent, 8, None)
        # A sign written directly against a numeric literal lexes as one signed
        # literal, so ``-5`` would reparse as a literal and the ``UnaryOp``
        # would disappear. A separating space is accepted by the grammar and
        # keeps the node, so the written form decides the shape.
        separator = " " if operand[:1].isdigit() or operand[:1] in {".", "+", "-"} else ""
        return f"{expr.op}{separator}{operand}"

    if isinstance(expr, FuncCall):
        args = ", ".join(_format_expr(argument, indent, parent_precedence=0, parent_op=None) for argument in expr.args)
        return f"{expr.name}({args})"

    if isinstance(expr, TernaryOp):
        branches = [(cond, [then_expr]) for cond, then_expr in expr.branches]
        return _branch_block(
            branches,
            indent=indent,
            else_block=None if expr.else_expr is None else [expr.else_expr],
        )

    if isinstance(expr, (int, float, bool, str)):
        return _quote_string(expr) if isinstance(expr, str) else str(expr)

    # An unhandled object is rendered with ``str`` rather than rejected, which
    # keeps debug output available for a node the formatter does not model yet
    # (a whole ``BasePicture`` or ``ModuleDef``, for example). Only the typed
    # node output above is round-trip parseable.
    return str(expr)


def format_seq_nodes(nodes: list[Any], indent: str = _DEFAULT_INDENT) -> str:
    """Pretty-print a list of SFC nodes recursively."""
    lines: list[str] = []

    from ..models import ast_model  # noqa: PLC0415

    def _fmt_stmt_list(statements: list[CodeItem], level: int = 2) -> None:
        for statement in statements:
            lines.append(indent * level + format_expr(statement, indent))

    def _fmt_fork(fork: ast_model.SFCFork | None) -> None:
        if fork is None:
            return
        suffix = " Break" if fork.has_break else ""
        lines.append(f"{indent}Fork to {', '.join(fork.targets)}{suffix}")

    def _fmt_step(step: ast_model.SFCStep) -> None:
        header = "InitStep" if step.kind == "init" else "Step"
        lines.append(f"{header} {step.name}")
        for label, block in (("Enter", step.code.enter), ("Active", step.code.active), ("Exit", step.code.exit)):
            if block:
                lines.append(indent + label + ":")
                _fmt_stmt_list(block)

    def _fmt_branches(header: str, footer: str, branches: list[list[Any]]) -> None:
        lines.append(header + ":")
        for index, branch in enumerate(branches, start=1):
            lines.append(indent + f"Branch {index}:")
            for line in format_seq_nodes(list(branch), indent).splitlines():
                lines.append(indent * 2 + line)
        lines.append(footer)

    def _fmt_body(header: str, footer: str, body: list[Any]) -> None:
        lines.append(header)
        for line in format_seq_nodes(list(body), indent).splitlines():
            lines.append(indent + line)
        lines.append(footer)

    for node in nodes:
        if isinstance(node, ast_model.SFCStep):
            _fmt_step(node)
            _fmt_fork(node.fork)

        elif isinstance(node, ast_model.SFCTransition):
            name_suffix = f" {node.name}" if node.name else ""
            if node.condition is None:
                lines.append(f"Transition{name_suffix}")
            else:
                lines.append(f"Transition{name_suffix} WAIT_FOR {format_expr(node.condition, indent)}")
            _fmt_fork(node.fork)

        elif isinstance(node, ast_model.SFCAlternative):
            _fmt_branches("Alternative", "EndAlternative", node.branches)

        elif isinstance(node, ast_model.SFCParallel):
            _fmt_branches("Parallel", "EndParallel", node.branches)

        elif isinstance(node, ast_model.SFCSubsequence):
            is_substep = node.kind == "substep"
            label = "Substep" if is_substep else "Subsequence"
            footer = "EndSubstep" if is_substep else "EndSubsequence"
            name_suffix = f" {node.name}" if node.name else ""
            _fmt_body(f"{label}{name_suffix}:", footer, node.body)

        elif isinstance(node, ast_model.SFCTransitionSub):
            name_suffix = f" {node.name}" if node.name else ""
            _fmt_body(f"TransitionSub{name_suffix}:", "EndTransitionSub", node.body)

        else:
            lines.append(str(node))

    return "\n".join(lines)
