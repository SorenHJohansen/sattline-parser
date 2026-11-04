"""AST walking for ``sattline query``: declarations, uses and SFC/object inventories.

The traversal itself is the public :class:`sattline_parser.models.NodeVisitor`.
This module only decides which AST facts become query rows and in what order.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from sattline_parser.models import NodeVisitor
from sattline_parser.models import ast_model as m
from sattline_parser.models.clauses import PickButton
from sattline_parser.models.expressions import Assignment, FuncCall, FuncCallStmt, IfStmt, VarRef
from sattline_parser.models.tails import LitStringTail, VarTail

__all__ = ["QUERY_KINDS", "QueryRow", "iter_rows"]

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
    visitor = _QueryVisitor()
    visitor.visit(picture)
    wanted = {kind.casefold() for kind in kinds}
    wanted_name = name.casefold() if name is not None else None
    wanted_module = module.casefold() if module is not None else None
    for row in visitor.rows:
        if row.kind.casefold() not in wanted:
            continue
        if wanted_name is not None and row.name.casefold() != wanted_name:
            continue
        if wanted_module is not None and (row.module or "").casefold() != wanted_module:
            continue
        yield row


class _QueryVisitor(NodeVisitor):
    """Turn AST nodes into query rows while tracking the enclosing module path."""

    def __init__(self) -> None:
        self.rows: list[QueryRow] = []
        self._path: list[str] = []

    def visit_BasePicture(self, picture: m.BasePicture) -> None:
        self.visit(picture.header)
        for module_type in picture.moduletype_defs:
            self.rows.append(
                _symbol("module_type", module_type.name, self._module_path(), module_type.declaration_span)
            )
            self._path.append(module_type.name)
            self._visit_module_body(module_type, declarations=True)
            self._path.pop()
        self._visit_module_body(picture, declarations=True)

    def visit_ModuleDef(self, module_def: m.ModuleDef) -> None:
        for graph_object in module_def.graph_objects or ():
            self.rows.append(
                QueryRow.at(
                    "graph-objects",
                    graph_object.type,
                    span=graph_object.span,
                    detail=_graph_object_detail(graph_object),
                    module=self._module_path(),
                )
            )
        for interact_object in module_def.interact_objects or ():
            self.rows.append(QueryRow(kind="interact-objects", name=interact_object.type, module=self._module_path()))
        self.generic_visit(module_def)

    def visit_ModuleHeader(self, header: m.ModuleHeader) -> None:
        """Visit header tails; ``groupconn`` names a scan group, not a variable."""
        if header.enable_tail is not None:
            self.visit(header.enable_tail)
        for tail in header.invoke_coord_tails:
            self.visit(tail)

    def visit_ModuleCode(self, module_code: m.ModuleCode) -> None:
        for sequence in module_code.sequences or ():
            self.rows.append(
                QueryRow(
                    kind="sequences",
                    name=sequence.name or "",
                    detail=f"{sequence.type}, {len(sequence.code)} element(s)",
                    module=self._module_path(),
                )
            )
            self.visit(sequence)
        for equation in module_code.equations or ():
            self.visit(equation)

    def visit_Sequence(self, sequence: m.Sequence) -> None:
        for item in sequence.code:
            self.visit(item)

    def visit_Equation(self, equation: m.Equation) -> None:
        for item in equation.code:
            self.visit(item)

    def visit_SFCStep(self, step: m.SFCStep) -> None:
        self.rows.append(_symbol("step", step.name or "", self._module_path(), step.span))
        for block in (step.code.enter, step.code.active, step.code.exit):
            for item in block:
                self.visit(item)

    def visit_SFCTransition(self, transition: m.SFCTransition) -> None:
        self.rows.append(_symbol("transition", transition.name or "", self._module_path(), transition.span))
        if transition.condition is not None:
            self.visit(transition.condition)

    def visit_SFCTransitionSub(self, transition: m.SFCTransitionSub) -> None:
        self.rows.append(_symbol("transition", transition.name or "", self._module_path(), transition.span))
        for item in transition.body:
            self.visit(item)

    def visit_SFCAlternative(self, alternative: m.SFCAlternative) -> None:
        for branch in alternative.branches:
            for item in branch:
                self.visit(item)

    def visit_SFCParallel(self, parallel: m.SFCParallel) -> None:
        for branch in parallel.branches:
            for item in branch:
                self.visit(item)

    def visit_SFCSubsequence(self, subsequence: m.SFCSubsequence) -> None:
        kind = "substep" if subsequence.kind == "substep" else "subsequence"
        self.rows.append(_symbol(kind, subsequence.name or "", self._module_path(), subsequence.span))
        for item in subsequence.body:
            self.visit(item)

    def visit_Assignment(self, assignment: Assignment) -> None:
        self.rows.append(
            QueryRow.at("writers", assignment.target.name, span=assignment.target.span, module=self._module_path())
        )
        self.visit(assignment.value)

    def visit_FuncCallStmt(self, statement: FuncCallStmt) -> None:
        self._visit_call(statement.call)
        for argument in statement.call.args:
            self.visit(argument)

    def visit_IfStmt(self, statement: IfStmt) -> None:
        for condition, body in statement.branches:
            self.visit(condition)
            for item in body:
                self.visit(item)
        for item in statement.else_block or ():
            self.visit(item)

    def visit_VarRef(self, reference: VarRef) -> None:
        self.rows.append(QueryRow.at("references", reference.name, span=reference.span, module=self._module_path()))

    def visit_VarTail(self, tail: VarTail) -> None:
        """Report a bound ``InVar_``/``OutVar_`` name as an unresolved use.

        The parser records the written symbol but does not evidence how it
        resolves, so the row is deliberately labelled unresolved rather than
        claiming a declaration. Bound tails carry no source span.
        """
        name = _bound_tail_name(tail)
        if name is not None:
            self.rows.append(QueryRow(kind="references", name=name, detail="unresolved", module=self._module_path()))

    def visit_LitStringTail(self, _tail: LitStringTail) -> None:
        """The owning ``VarTail`` already reported the name."""

    def visit_GraphObject(self, graph_object: m.GraphObject) -> None:
        """Report text-object variable names, then walk the property payloads."""
        for name in graph_object.properties.get("text_vars") or ():
            self.rows.append(QueryRow(kind="references", name=name, detail="text variable", module=self._module_path()))
        self.generic_visit(graph_object)

    def visit_PickButton(self, button: PickButton) -> None:
        if button.is_reference:
            self.rows.append(
                QueryRow(
                    kind="references", name=button.value, detail="pick-button reference", module=self._module_path()
                )
            )

    def visit_FuncCall(self, call: FuncCall) -> None:
        self._visit_call(call)
        for argument in call.args:
            self.visit(argument)

    def _visit_call(self, call: FuncCall) -> None:
        self.rows.append(QueryRow.at("callers", call.name, span=call.span, module=self._module_path()))

    def _visit_module_body(
        self, module: m.BasePicture | m.ModuleTypeDef | m.SingleModule | m.FrameModule, *, declarations: bool
    ) -> None:
        if declarations:
            for variable in module.localvariables:
                self.rows.append(_symbol("variable", variable.name, self._module_path()))
            for variable in module.moduleparameters:
                self.rows.append(_symbol("parameter", variable.name, self._module_path()))
        for module_def in module.moduledefs:
            self.visit(module_def)
        for module_code in module.modulecodes:
            self.visit(module_code)
        for submodule in module.submodules:
            self._visit_submodule(submodule)

    def _visit_submodule(self, submodule: m.SingleModule | m.FrameModule | m.ModuleTypeInstance) -> None:
        if isinstance(submodule, m.ModuleTypeInstance):
            # A reference to a named module type: no body is parsed here.
            self.rows.append(
                _symbol(
                    "module_instance", submodule.header.name, self._module_path(), submodule.header.declaration_span
                )
            )
            self.visit(submodule.header)
            return
        header = submodule.header
        self.rows.append(_symbol("submodule", header.name, self._module_path(), header.declaration_span))
        self.visit(header)
        self._path.append(header.name)
        self._visit_module_body(submodule, declarations=isinstance(submodule, m.SingleModule))
        self._path.pop()

    def _module_path(self) -> str | None:
        """``A/B`` for a nested module, ``None`` at the unit level."""
        return "/".join(self._path) or None


def _symbol(kind: str, name: str, module: str | None, span: m.SourceSpan | None = None) -> QueryRow:
    return QueryRow.at("symbols", name, span=span, detail=kind, module=module)


def _graph_object_detail(graph_object: m.GraphObject) -> str:
    layer = graph_object.properties.get("layer")
    return f"layer {layer}" if layer is not None else "graph object"


def _bound_tail_name(tail: VarTail) -> str | None:
    """The symbol a bare bound tail names, or ``None`` for a literal value.

    A ``LitStringTail`` is a quoted symbol, not a variable path, so it is not
    reported as a variable use.
    """
    value = tail.value
    return value if isinstance(value, str) else None
