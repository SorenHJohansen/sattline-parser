"""AST walking for ``sattline query``: declarations, uses and SFC/object inventories."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal

from sattline_parser.models import ast_model as m
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

__all__ = ["QUERY_KINDS", "QueryRow", "iter_rows"]

QueryKind = Literal[
    "symbols",
    "references",
    "writers",
    "callers",
    "graph-objects",
    "interact-objects",
    "sequences",
]

#: ``--what`` values, in the order the help lists them.
QUERY_KINDS: tuple[str, ...] = (
    "symbols",
    "references",
    "writers",
    "callers",
    "graph-objects",
    "interact-objects",
    "sequences",
)


@dataclass(frozen=True, slots=True)
class QueryRow:
    """One query hit: what it is, where it is, and which module holds it."""

    kind: str
    name: str
    detail: str | None = None
    module: str | None = None
    line: int | None = None
    column: int | None = None
    start: int | None = None
    end: int | None = None

    @classmethod
    def at(
        cls,
        kind: str,
        name: str,
        *,
        span: m.SourceSpan | None,
        detail: str | None = None,
        module: str | None = None,
    ) -> QueryRow:
        """A row located at ``span``, or without a position when ``span`` is ``None``."""
        return cls(
            kind=kind,
            name=name,
            detail=detail,
            module=module,
            line=span.line if span is not None else None,
            column=span.column if span is not None else None,
            start=span.start if span is not None else None,
            end=span.end if span is not None else None,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "name": self.name,
            "detail": self.detail,
            "module": self.module,
            "line": self.line,
            "column": self.column,
            "start": self.start,
            "end": self.end,
        }


def iter_rows(
    picture: m.BasePicture, *, kinds: Iterable[str], name: str | None, module: str | None
) -> Iterator[QueryRow]:
    """Yield rows for the requested kinds, filtered by name and module path."""
    wanted = {kind.casefold() for kind in kinds}
    wanted_name = name.casefold() if name is not None else None
    wanted_module = module.casefold() if module is not None else None
    for row in _walk_unit(picture, ()):
        if row.kind.casefold() not in wanted:
            continue
        if wanted_name is not None and row.name.casefold() != wanted_name:
            continue
        if wanted_module is not None and (row.module or "").casefold() != wanted_module:
            continue
        yield row


def _walk_unit(picture: m.BasePicture, path: tuple[str, ...]) -> Iterator[QueryRow]:
    for module_type in picture.moduletype_defs:
        yield _symbol("module_type", module_type.name, path, module_type.declaration_span)
        yield from _walk_module(
            (*path, module_type.name),
            module_type.localvariables,
            module_type.moduleparameters,
            module_type.moduledefs or [module_type.moduledef],
            module_type.modulecodes or [module_type.modulecode],
            module_type.submodules,
        )
    yield from _walk_module(
        path, picture.localvariables, (), picture.moduledefs, picture.modulecodes, picture.submodules
    )


def _walk_module(
    path: tuple[str, ...],
    localvariables: Iterable[m.Variable],
    parameters: Iterable[m.Variable],
    moduledefs: Iterable[m.ModuleDef | None],
    modulecodes: Iterable[m.ModuleCode | None],
    submodules: Iterable[m.SingleModule | m.FrameModule | m.ModuleTypeInstance],
) -> Iterator[QueryRow]:
    for variable in localvariables:
        yield _symbol("variable", variable.name, path)
    for variable in parameters:
        yield _symbol("parameter", variable.name, path)
    for moduledef in moduledefs:
        if moduledef is None:  # pragma: no cover - every module body requires a moduledef
            continue
        for graph_object in moduledef.graph_objects or ():
            yield QueryRow.at(
                "graph-objects",
                graph_object.type,
                span=graph_object.span,
                detail=_graph_object_detail(graph_object),
                module=_module_path(path),
            )
        for interact_object in moduledef.interact_objects or ():
            yield QueryRow(kind="interact-objects", name=interact_object.type, module=_module_path(path))
    for modulecode in modulecodes:
        if modulecode is None:
            continue
        for sequence in modulecode.sequences or ():
            yield QueryRow(
                kind="sequences",
                name=sequence.name or "",
                detail=f"{sequence.type}, {len(sequence.code)} element(s)",
                module=_module_path(path),
            )
            yield from _walk_sfc(sequence.code, path)
        for equation in modulecode.equations or ():
            for code_item in equation.code:
                yield from _walk_code_item(code_item, path)
    for submodule in submodules:
        yield from _walk_submodule(submodule, path)


def _walk_submodule(
    submodule: m.SingleModule | m.FrameModule | m.ModuleTypeInstance, path: tuple[str, ...]
) -> Iterator[QueryRow]:
    if isinstance(submodule, m.ModuleTypeInstance):
        # A reference to a named module type: no body is parsed here.
        yield _symbol("module_instance", submodule.header.name, path, submodule.header.declaration_span)
        return
    header = submodule.header
    child_path = (*path, header.name)
    yield _symbol("submodule", header.name, path, header.declaration_span)
    # A FrameModule is a pure container: it only nests further submodules.
    variables = submodule.localvariables if isinstance(submodule, m.SingleModule) else []
    parameters = submodule.moduleparameters if isinstance(submodule, m.SingleModule) else []
    yield from _walk_module(
        child_path,
        variables,
        parameters,
        submodule.moduledefs or [submodule.moduledef],
        submodule.modulecodes or [submodule.modulecode],
        submodule.submodules,
    )


def _walk_sfc(items: Iterable[m.SFCBodyItem], path: tuple[str, ...]) -> Iterator[QueryRow]:
    for item in items:
        if isinstance(item, m.SFCStep):
            yield _symbol("step", item.name or "", path, item.span)
            for block in (item.code.enter, item.code.active, item.code.exit):
                for code_item in block:
                    yield from _walk_code_item(code_item, path)
        elif isinstance(item, m.SFCTransition):
            yield _symbol("transition", item.name or "", path, item.span)
            if item.condition is not None:
                yield from _walk_expression(item.condition, path)
        elif isinstance(item, m.SFCTransitionSub):
            yield _symbol("transition", item.name or "", path, item.span)
            yield from _walk_sfc(item.body, path)
        elif isinstance(item, (m.SFCAlternative, m.SFCParallel)):
            for branch in item.branches:
                yield from _walk_sfc(branch, path)
        elif isinstance(item, m.SFCSubsequence):
            kind = "substep" if item.kind == "substep" else "subsequence"
            yield _symbol(kind, item.name or "", path, item.span)
            yield from _walk_sfc(item.body, path)
        elif isinstance(item, m.SFCLoop):
            yield QueryRow.at("symbols", item.name or "", span=item.span, detail="loop", module=_module_path(path))
            if item.condition is not None:
                yield from _walk_expression(item.condition, path)
            yield from _walk_sfc(item.body, path)
            if item.else_body is not None:
                yield from _walk_sfc(item.else_body, path)


def _walk_code_item(item: object, path: tuple[str, ...]) -> Iterator[QueryRow]:
    if isinstance(item, Assignment):
        yield QueryRow.at("writers", item.target.name, span=item.target.span, module=_module_path(path))
        yield from _walk_expression(item.value, path)
    elif isinstance(item, FuncCallStmt):
        yield _call_row(item.call, path)
        for argument in item.call.args:
            yield from _walk_expression(argument, path)
    elif isinstance(item, IfStmt):
        for condition, body in item.branches:
            yield from _walk_expression(condition, path)
            for nested in body:
                yield from _walk_code_item(nested, path)
        for nested in item.else_block or ():
            yield from _walk_code_item(nested, path)


def _walk_expression(expression: object, path: tuple[str, ...]) -> Iterator[QueryRow]:
    """Yield ``references`` and ``callers`` inside an expression tree."""
    if isinstance(expression, VarRef):
        yield QueryRow.at("references", expression.name, span=expression.span, module=_module_path(path))
    elif isinstance(expression, FuncCall):
        yield _call_row(expression, path)
        for argument in expression.args:
            yield from _walk_expression(argument, path)
    elif isinstance(expression, BoolOp):
        for operand in expression.operands:
            yield from _walk_expression(operand, path)
    elif isinstance(expression, NotOp):
        yield from _walk_expression(expression.operand, path)
    elif isinstance(expression, (Compare, BinOp)):
        yield from _walk_expression(expression.left, path)
        yield from _walk_expression(expression.right, path)
    elif isinstance(expression, UnaryOp):
        yield from _walk_expression(expression.operand, path)
    elif isinstance(expression, TernaryOp):
        for condition, then_expression in expression.branches:
            yield from _walk_expression(condition, path)
            yield from _walk_expression(then_expression, path)
        if expression.else_expr is not None:
            yield from _walk_expression(expression.else_expr, path)


def _call_row(call: FuncCall, path: tuple[str, ...]) -> QueryRow:
    return QueryRow.at("callers", call.name, span=call.span, module=_module_path(path))


def _symbol(kind: str, name: str, path: tuple[str, ...], span: m.SourceSpan | None = None) -> QueryRow:
    return QueryRow.at("symbols", name, span=span, detail=kind, module=_module_path(path))


def _module_path(path: tuple[str, ...]) -> str | None:
    """``A/B`` for a nested module, ``None`` at the unit level."""
    return "/".join(path) or None


def _graph_object_detail(graph_object: m.GraphObject) -> str:
    layer = graph_object.properties.get("layer")
    return f"layer {layer}" if layer is not None else "graph object"
