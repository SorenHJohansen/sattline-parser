"""Graphics binding and expression parsing helpers.

The ``Var`` / ``Expr`` / ``Lit`` binding scanner, literal coercion, and the
graphics-expression parser: the package's own ``expression`` grammar and
transformer, with source spans in companion-file coordinates.
"""

from __future__ import annotations

import dataclasses
import re
from functools import lru_cache
from typing import Any, cast

from lark import Tree
from lark.exceptions import LarkError

from sattline_parser.models.ast_model import FloatLiteral, GraphicsBinding, IntLiteral, SourceSpan
from sattline_parser.source_io import build_lark_parser
from sattline_parser.transformer.sl_transformer import SLTransformer

from .models import GraphicsMessage

BINDING_LINE_RE = re.compile(r"(?<!\S)(Var|Expr|Lit)\s+(\S+)\s+(-?\d+)\s+")
#: Failures a graphics expression may raise. They are the same shape the source
#: parser treats as a failed parse: a grammar error, a runaway recursion, or a
#: transformer value/type/index error. All of them become a ``GraphicsMessage``
#: on the binding, so scanning a companion never raises for its content.
_EXPRESSION_FAILURES = (LarkError, RecursionError, ValueError, TypeError, IndexError)
_GRAPHICS_EXPR_KEYWORDS = {
    "and": "AND",
    "or": "OR",
    "not": "NOT",
    "if": "IF",
    "then": "THEN",
    "else": "ELSE",
    "elsif": "ELSIF",
    "endif": "ENDIF",
    "true": "True",
    "false": "False",
}
_GRAPHICS_EXPR_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(sorted(_GRAPHICS_EXPR_KEYWORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _graphics_expression_parser() -> Any:
    return build_lark_parser(start="expression")


def _unwrap_expression_root(node: object) -> object:
    if isinstance(node, Tree):
        tree = cast(Tree[object], node)
        children = cast(list[object], tree.children)
        if tree.data == "expression" and len(children) == 1:
            return children[0]
        return cast(object, tree)
    return node


def _rebase_expression_spans(node: object, *, line: int, column: int, start: int) -> object:
    """Rewrite expression spans from expression-local to companion coordinates.

    The expression text is parsed on its own, so its spans start at line 1,
    column 1, offset 0. ``line``, ``column``, and ``start`` are the companion
    position of the expression's first character. Parsing without a padding
    prefix keeps the work linear in the expression length rather than in the
    file offset.
    """

    def rebase(value: SourceSpan) -> SourceSpan:
        return SourceSpan(
            start=start + value.start,
            end=start + value.end,
            line=line + value.line - 1,
            column=(column + value.column - 1) if value.line == 1 else value.column,
        )

    def convert(value: object) -> object:
        if isinstance(value, SourceSpan):
            return rebase(value)
        if isinstance(value, (IntLiteral, FloatLiteral)):
            # The literal classes are ``int``/``float`` subclasses, so they fall
            # through every structural branch below and would keep their
            # expression-local span.
            literal_span = value.span
            if literal_span is not None:
                rebased = rebase(literal_span)
                if isinstance(value, IntLiteral):
                    return IntLiteral(int(value), rebased)
                return FloatLiteral(float(value), rebased)
        if isinstance(value, dict):
            mapping = cast(dict[str, object], value)
            for key, item in mapping.items():
                mapping[key] = convert(item)
            return mapping
        if isinstance(value, list):
            items = cast(list[object], value)
            for index, item in enumerate(items):
                items[index] = convert(item)
            return items
        if isinstance(value, tuple):
            items = cast(tuple[object, ...], value)
            return tuple(convert(item) for item in items)
        if isinstance(value, Tree):
            tree = cast(Tree[object], value)
            for index, item in enumerate(tree.children):
                tree.children[index] = convert(item)
            return tree
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            changes = {
                structure_field.name: convert(getattr(value, structure_field.name))
                for structure_field in dataclasses.fields(value)
            }
            return dataclasses.replace(value, **changes)
        return value

    return convert(node)


def _coerce_graphics_literal(payload: str) -> object:
    lowered = payload.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"[+-]?\d+", payload):
        return int(payload)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[Ee][+-]?\d+)?", payload):
        return float(payload)
    return payload


def _normalize_graphics_expression(payload: str) -> str:
    return _GRAPHICS_EXPR_KEYWORD_RE.sub(
        lambda match: _GRAPHICS_EXPR_KEYWORDS[match.group(0).casefold()],
        payload,
    )


def parse_graphics_binding_match(
    row_text: str,
    *,
    line: int,
    match: re.Match[str],
    line_start_offset: int | None = None,
) -> tuple[GraphicsBinding | None, tuple[GraphicsMessage, ...]]:
    if line_start_offset is None:
        # No file context: assume each preceding line is one character long.
        line_start_offset = line - 1
    kind = match.group(1).casefold()
    raw_length = int(match.group(3))
    tail = row_text[match.end() :]
    if raw_length < 0:
        return None, ()

    raw_payload = tail[:raw_length] if raw_length <= len(tail) else tail
    payload = raw_payload.rstrip()
    if not payload:
        return None, ()

    payload_column = match.end() + 1
    payload_start = line_start_offset + match.end()
    span = SourceSpan(
        start=payload_start,
        end=payload_start + len(payload),
        line=line,
        column=payload_column,
    )
    if kind == "lit":
        return GraphicsBinding(kind=kind, raw_text=payload, value=_coerce_graphics_literal(payload), span=span), ()
    if kind == "var":
        return (
            GraphicsBinding(
                kind=kind,
                raw_text=payload,
                value={"var_name": payload, "span": span},
                span=span,
            ),
            (),
        )

    try:
        normalized_payload = _normalize_graphics_expression(payload)
        parsed = _unwrap_expression_root(
            SLTransformer().transform(_graphics_expression_parser().parse(normalized_payload))
        )
        parsed = _rebase_expression_spans(parsed, line=line, column=payload_column, start=payload_start)
    except _EXPRESSION_FAILURES as exc:
        return (
            GraphicsBinding(kind=kind, raw_text=payload, value=payload, span=span),
            (
                GraphicsMessage(
                    severity="warning",
                    message=f"Could not parse graphics expression {payload!r}: {exc}",
                    line=line,
                    column=payload_column,
                    length=len(payload),
                ),
            ),
        )

    return GraphicsBinding(kind=kind, raw_text=payload, value=parsed, span=span), ()


def parse_graphics_binding_line(
    row_text: str,
    *,
    line: int,
    line_start_offset: int | None = None,
) -> tuple[tuple[GraphicsBinding, ...], tuple[GraphicsMessage, ...]]:
    bindings: list[GraphicsBinding] = []
    messages: list[GraphicsMessage] = []

    for match in BINDING_LINE_RE.finditer(row_text):
        binding, binding_messages = parse_graphics_binding_match(
            row_text,
            line=line,
            match=match,
            line_start_offset=line_start_offset,
        )
        if binding is not None:
            bindings.append(binding)
        messages.extend(binding_messages)

    return tuple(bindings), tuple(messages)


__all__: tuple[str, ...] = (
    "BINDING_LINE_RE",
    "_coerce_graphics_literal",
    "_graphics_expression_parser",
    "_normalize_graphics_expression",
    "_rebase_expression_spans",
    "_unwrap_expression_root",
    "parse_graphics_binding_line",
    "parse_graphics_binding_match",
)
