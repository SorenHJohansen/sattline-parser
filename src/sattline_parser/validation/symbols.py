"""Symbol tables and variable resolution for the strict validation pass.

Resolution follows SattLine scoping: an inner module definition may reference
its own locals/parameters, then those of its enclosing definitions, and finally
the original BasePicture locals. Record field access resolves through the
top-level ``DATATYPE`` definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sattline_parser.models.ast_model import DataType, Variable
from sattline_parser.models.expressions import VarRef


@dataclass
class Scope:
    """A single declaration frame: one module definition's variables and parameters."""

    parent: Scope | None
    variables: dict[str, Variable] = field(default_factory=dict[str, Variable])

    def lookup(self, name: str) -> Variable | None:
        key = name.casefold()
        current: Scope | None = self
        while current is not None:
            found = current.variables.get(key)
            if found is not None:
                return found
            current = current.parent
        return None


def build_scope(parent: Scope | None, variables: list[Variable]) -> Scope:
    """Flatten a module definition's parameter + local declarations into a scope."""
    table: dict[str, Variable] = {}
    for variable in variables:
        table.setdefault(variable.name.casefold(), variable)
    return Scope(parent=parent, variables=table)


def _find_field(record: DataType, name: str) -> Variable | None:
    key = name.casefold()
    for variable in record.var_list:
        if variable.name.casefold() == key:
            return variable
    return None


def resolve_var(ref: VarRef, scope: Scope, records: dict[str, DataType]) -> Variable | None:
    """Resolve a (possibly dotted, possibly :Old/:New) reference to its Variable.

    Returns ``None`` when the reference cannot be resolved to a known variable
    or record field — e.g. a submodule instance name or an undeclared symbol —
    in which case no rules apply.
    """
    parts = ref.name.split(".")
    current = scope.lookup(parts[0])
    if current is None:
        return None
    for part in parts[1:]:
        record = records.get(current.datatype_text.casefold())
        if record is None:
            return None
        current = _find_field(record, part)
        if current is None:
            return None
    return current
