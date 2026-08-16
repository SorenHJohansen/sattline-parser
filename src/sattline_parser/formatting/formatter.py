"""Formatting helpers for AST models."""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
from typing import Any, Protocol, TypeGuard, cast

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

__all__ = ["format_expr", "format_list", "format_optional", "format_seq_nodes"]


class _VariableLike(Protocol):
    name: object
    datatype: object
    global_var: object
    const: object
    state: object
    init_value: object
    description: object


def _is_variable_like(value: object) -> TypeGuard[_VariableLike]:
    required_attrs = (
        "name",
        "datatype",
        "global_var",
        "const",
        "state",
        "init_value",
        "description",
    )
    return type(value).__name__ == "Variable" and all(hasattr(value, attr) for attr in required_attrs)


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


def format_expr(expr: object, indent: str = _DEFAULT_INDENT) -> str:
    """Pretty-print nested expressions and statements in a SattLine-like format."""

    # New typed nodes take priority over legacy tuple/dict forms
    if isinstance(expr, VarRef):
        return expr.name if not expr.state else f"{expr.name}:{expr.state}"

    if isinstance(expr, Assignment):
        return f"{format_expr(expr.target, indent)} = {format_expr(expr.value, indent)}"

    if isinstance(expr, FuncCallStmt):
        return format_expr(expr.call, indent)

    if isinstance(expr, IfStmt):
        out_lines: list[str] = []
        for index, (cond, body) in enumerate(expr.branches):
            out_lines.append(f"{'IF' if index == 0 else 'ELSIF'} {format_expr(cond, indent)}")
            out_lines.append("THEN")
            for stmt in body:
                out_lines.append(textwrap.indent(format_expr(stmt, indent), indent))
        if expr.else_block is not None:
            out_lines.append("ELSE")
            for stmt in expr.else_block:
                out_lines.append(textwrap.indent(format_expr(stmt, indent), indent))
        out_lines.append("ENDIF")
        return "\n".join(out_lines)

    if isinstance(expr, BoolOp):
        parts = [format_expr(op, indent) for op in expr.operands]
        sep = f" {expr.op} \n"
        return sep.join(parts)

    if isinstance(expr, NotOp):
        return f"NOT({format_expr(expr.operand, indent)})"

    if isinstance(expr, Compare):
        return f"{format_expr(expr.left, indent)} {expr.op} {format_expr(expr.right, indent)}"

    if isinstance(expr, BinOp):
        return f"({format_expr(expr.left, indent)} {expr.op} {format_expr(expr.right, indent)})"

    if isinstance(expr, UnaryOp):
        return f"{expr.op}{format_expr(expr.operand, indent)}"

    if isinstance(expr, FuncCall):
        args = ", ".join(format_expr(a, indent) for a in expr.args)
        return f"{expr.name}({args})"

    if isinstance(expr, TernaryOp):
        out_lines2: list[str] = []
        for index, (cond, then_expr) in enumerate(expr.branches):
            out_lines2.append(f"{'IF' if index == 0 else 'ELSIF'} {format_expr(cond, indent)}")
            out_lines2.append("THEN")
            out_lines2.append(textwrap.indent(format_expr(then_expr, indent), indent))
        if expr.else_expr is not None:
            out_lines2.append("ELSE")
            out_lines2.append(textwrap.indent(format_expr(expr.else_expr, indent), indent))
        out_lines2.append("ENDIF")
        return "\n".join(out_lines2)

    if isinstance(expr, int | float | bool | str):
        return repr(expr) if isinstance(expr, str) else str(expr)

    return str(expr)


def format_seq_nodes(nodes: list[Any], indent: str = _DEFAULT_INDENT) -> str:
    """Pretty-print a list of SFC nodes recursively."""
    lines: list[str] = []

    from ..models import ast_model  # noqa: PLC0415

    def _fmt_stmt_list(statements: list[object], level: int = 2) -> None:
        for statement in statements:
            lines.append(indent * level + format_expr(statement, indent))

    for node in nodes:
        if isinstance(node, ast_model.SFCStep):
            header = "InitStep" if node.kind == "init" else "Step"
            lines.append(f"{header} {node.name}")
            if node.code.enter:
                lines.append(indent + "Enter:")
                _fmt_stmt_list(cast(list[object], node.code.enter))
            if node.code.active:
                lines.append(indent + "Active:")
                _fmt_stmt_list(cast(list[object], node.code.active))
            if node.code.exit:
                lines.append(indent + "Exit:")
                _fmt_stmt_list(cast(list[object], node.code.exit))

        elif isinstance(node, ast_model.SFCTransition):
            name_suffix = f" {node.name}" if node.name else ""
            condition = format_expr(node.condition, indent)
            lines.append(f"Transition{name_suffix} WAIT_FOR {condition}")

        elif isinstance(node, ast_model.SFCAlternative):
            lines.append("Alternative:")
            for index, branch in enumerate(node.branches, start=1):
                lines.append(indent + f"Branch {index}:")
                branch_str = format_seq_nodes(cast(list[object], branch), indent)
                for line in branch_str.splitlines():
                    lines.append(indent * 2 + line)
            lines.append("EndAlternative")

        elif isinstance(node, ast_model.SFCParallel):
            lines.append("Parallel:")
            for index, branch in enumerate(node.branches, start=1):
                lines.append(indent + f"Branch {index}:")
                branch_str = format_seq_nodes(cast(list[object], branch), indent)
                for line in branch_str.splitlines():
                    lines.append(indent * 2 + line)
            lines.append("EndParallel")

        elif isinstance(node, ast_model.SFCSubsequence):
            lines.append(f"Subsequence {node.name}:")
            sub_str = format_seq_nodes(cast(list[object], node.body), indent)
            for line in sub_str.splitlines():
                lines.append(indent + line)
            lines.append("EndSubsequence")

        elif isinstance(node, ast_model.SFCTransitionSub):
            lines.append(f"TransitionSub {node.name}:")
            sub_str = format_seq_nodes(cast(list[object], node.body), indent)
            for line in sub_str.splitlines():
                lines.append(indent + line)
            lines.append("EndTransitionSub")

        elif isinstance(node, ast_model.SFCFork):
            lines.append(f"Fork to {', '.join(node.targets)}")

        elif isinstance(node, ast_model.SFCBreak):
            lines.append("Break")

        else:
            lines.append(str(node))

    return "\n".join(lines)
