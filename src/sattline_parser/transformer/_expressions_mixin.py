"""Expression and statement mixin for SLTransformer.

Handles expression parsing, operator handling, statements, and value unwrapping.
"""

from __future__ import annotations

from typing import Any, cast

from lark import Token, Tree

from sattline_parser.grammar import constants as const
from sattline_parser.models.expressions import (
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

__all__ = ["ExpressionsMixin", "_ExpressionsMixin"]


class _ExpressionsMixin:
    """Mixin providing expression and statement transformation methods."""

    def value(self, items: list[Any]) -> Any:
        """Grammar value rule -> the base value (BOOL | REAL | STRING | SIGNED_INT)."""
        if not items:
            raise ValueError("value expected one item (BOOL|REAL|STRING|SIGNED_INT); got empty list")
        if len(items) != 1:
            raise ValueError(f"value expected exactly one item; got {len(items)}: {items!r}")
        v = items[0]
        if v is None:
            raise ValueError("value item is None")
        return v

    def connected_variable(self, items: list[Any]) -> Any:
        """Grammar connected_variable rule -> variable or variable reference."""
        for it in items:
            if not isinstance(it, Token):
                return it
        raise ValueError(f"connected_variable expected a non-Token child; got: {items}")

    def invar_tail(self, items: list[Any]) -> Any:
        """Grammar invar_tail rule -> tail specification or variable reference."""
        saw_outvar = False
        for it in items:
            if isinstance(it, Token) and it.type == "OUTVAR_PREFIX":
                saw_outvar = True
            if not isinstance(it, Token):
                if saw_outvar:
                    return Tree(const.GRAMMAR_VALUE_OUTVAR_PREFIX, [it])
                return it
        raise ValueError(f"invar_tail expected a non-Token child; got: {items}")

    def or_expression(self, items: list[Any]) -> Any:
        """Grammar or_expression -> BoolOp("OR", ...) | single expression."""
        exprs = [it for it in items if not isinstance(it, Token)]
        if len(exprs) == 1:
            return exprs[0]
        return BoolOp(op="OR", operands=tuple(exprs))

    def and_expression(self, items: list[Any]) -> Any:
        """Grammar and_expression -> BoolOp("AND", ...) | single expression."""
        exprs = [it for it in items if not isinstance(it, Token)]
        if len(exprs) == 1:
            return exprs[0]
        return BoolOp(op="AND", operands=tuple(exprs))

    def not_expression(self, items: list[Any]) -> Any:
        """Grammar not_expression -> NotOp(...) | single expression."""
        if len(items) == 1:
            return items[0]
        expr: Any | None = None
        for it in items:
            if not isinstance(it, Token):
                expr = it
        if expr is not None:
            return NotOp(operand=expr)
        return items[-1]

    def compare(self, items: list[Any]) -> Any:
        """Grammar compare -> Compare(left, op, right) | single expression."""
        values = [it for it in items if it is not None and not isinstance(it, Token)]
        operators = [str(it) for it in items if isinstance(it, Token)]
        if len(values) <= 1:
            return values[0] if values else None
        # Left-fold: build chained comparisons as nested Compare nodes
        result = values[0]
        for op, rhs in zip(operators, values[1:], strict=False):
            result = Compare(left=result, op=op, right=rhs)
        return result

    def additive_expression(self, items: list[Any]) -> Any:
        """Grammar additive_expression -> BinOp (left-associative) | single expression."""
        values = [it for it in items if it is not None and not isinstance(it, Token)]
        operators = [str(it) for it in items if isinstance(it, Token)]
        if len(values) <= 1:
            return values[0] if values else None
        result = values[0]
        for op, rhs in zip(operators, values[1:], strict=False):
            result = BinOp(left=result, op=op, right=rhs)
        return result

    def multiplicative_expression(self, items: list[Any]) -> Any:
        """Grammar multiplicative_expression -> BinOp (left-associative) | single expression."""
        values = [it for it in items if it is not None and not isinstance(it, Token)]
        operators = [str(it) for it in items if isinstance(it, Token)]
        if len(values) <= 1:
            return values[0] if values else None
        result = values[0]
        for op, rhs in zip(operators, values[1:], strict=False):
            result = BinOp(left=result, op=op, right=rhs)
        return result

    def unary_expression(self, items: list[Any]) -> Any:
        """Grammar unary_expression -> UnaryOp | single expression."""
        if len(items) == 1:
            return items[0]
        op: Token | None = None
        expr: Any | None = None
        for it in items:
            if isinstance(it, Token):
                op = it
            else:
                expr = it
        if op is None or expr is None:
            raise ValueError(f"unary_expression expected operator and expression; got: {items}")
        op_str = "-" if op.type == const.KEY_MINUS else "+"
        return UnaryOp(op=op_str, operand=expr)  # type: ignore[arg-type]

    def function_call(self, items: list[Any]) -> FuncCall:
        """Grammar function_call -> FuncCall(name, args)."""
        fn_name: str | None = None
        args: list[Any] = []
        for it in items:
            if isinstance(it, str) and not isinstance(it, Token) and fn_name is None:
                fn_name = it
            elif not isinstance(it, Token):
                args = cast(list[Any], it) if isinstance(it, list) else [it]
        if fn_name is None:
            raise ValueError(f"function_call missing name; got: {items}")
        return FuncCall(name=fn_name, args=tuple(args))

    def argument_list(self, items: list[Any]) -> list[Any]:
        """Grammar argument_list -> expression (COMMA expression)*."""
        return [it for it in items if not isinstance(it, Token)]

    def ternary_if(self, items: list[Any]) -> TernaryOp:
        """Grammar ternary_if -> TernaryOp(branches, else_expr)."""
        branches: list[tuple[Any, Any]] = []
        else_expr: Any | None = None
        i = 0
        while i < len(items):
            tok = items[i]
            if isinstance(tok, Token) and tok.type == const.GRAMMAR_VALUE_IF:
                cond = items[i + 1]
                then_expr = items[i + 3]  # skip THEN at i+2
                branches.append((cond, then_expr))
                i += 4
            elif isinstance(tok, Token) and tok.type == const.GRAMMAR_VALUE_ELSIF:
                cond = items[i + 1]
                then_expr = items[i + 3]  # skip THEN
                branches.append((cond, then_expr))
                i += 4
            elif isinstance(tok, Token) and tok.type == const.GRAMMAR_VALUE_ELSE:
                else_expr = items[i + 1]
                i += 2
            else:
                i += 1
        return TernaryOp(branches=tuple(branches), else_expr=else_expr)

    def assignment_statement(self, items: list[Any]) -> Assignment:
        """Grammar assignment_statement -> Assignment(target, value)."""
        target_raw, expr = (items[0], items[-1]) if len(items) != 2 else items
        target = target_raw if isinstance(target_raw, VarRef) else VarRef(str(target_raw))
        return Assignment(target=target, value=expr)

    def if_statement(self, items: list[Any]) -> IfStmt:
        """Grammar if_statement -> IfStmt(branches, else_block)."""
        branches: list[tuple[Any, tuple[Any, ...]]] = []
        else_block: tuple[Any, ...] | None = None
        i = 0
        while i < len(items):
            tok = items[i]
            if isinstance(tok, Token) and tok.type in (
                const.GRAMMAR_VALUE_IF,
                const.GRAMMAR_VALUE_ELSIF,
            ):
                cond = items[i + 1]
                i += 3  # skip cond + THEN
                stmts: list[Any] = []
                while i < len(items):
                    t = items[i]
                    if isinstance(t, Token) and t.type in (
                        const.GRAMMAR_VALUE_ELSIF,
                        const.GRAMMAR_VALUE_ELSE,
                        const.GRAMMAR_VALUE_ENDIF,
                    ):
                        break
                    if isinstance(t, list):
                        stmts.extend(cast(list[Any], t))
                    else:
                        stmts.append(t)
                    i += 1
                branches.append((cond, tuple(stmts)))
            elif isinstance(tok, Token) and tok.type == const.GRAMMAR_VALUE_ELSE:
                i += 1
                elst: list[Any] = []
                while i < len(items):
                    t = items[i]
                    if isinstance(t, Token) and t.type == const.GRAMMAR_VALUE_ENDIF:
                        i += 1
                        break
                    if isinstance(t, list):
                        elst.extend(cast(list[Any], t))
                    else:
                        elst.append(t)
                    i += 1
                else_block = tuple(elst)
            else:
                i += 1
        return IfStmt(branches=tuple(branches), else_block=else_block)

    def statement(self, items: list[Any]) -> Any:
        """Grammar statement -> unwrapped Assignment | FuncCallStmt | IfStmt | CodeComment."""
        for it in items:
            if not isinstance(it, Token):
                # Wrap bare FuncCall in FuncCallStmt
                if isinstance(it, FuncCall):
                    return FuncCallStmt(call=it)
                return it
        types = ", ".join(type(x).__name__ for x in items)
        raise ValueError(
            f"statement expected a non-Token child "
            f"(assignment_statement | function_call | if_statement); got only tokens: {types}"
        )


ExpressionsMixin = _ExpressionsMixin
