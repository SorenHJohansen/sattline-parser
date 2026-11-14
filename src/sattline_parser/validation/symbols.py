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
from sattline_parser.names import fold_identifier


@dataclass
class Scope:
    """A single declaration frame: one module definition's variables and parameters."""

    parent: Scope | None
    variables: dict[str, Variable] = field(default_factory=dict[str, Variable])

    def lookup(self, name: str) -> Variable | None:
        key = fold_identifier(name)
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
        table.setdefault(fold_identifier(variable.name), variable)
    return Scope(parent=parent, variables=table)


def lookup_datatype(records: dict[str, DataType], datatype_text: str) -> DataType | None:
    """Look a record up in a table keyed by :func:`fold_identifier`.

    Identifier identity is the CP1252 byte fold, never full Unicode case
    folding, so the table key is the only lookup that can match.
    """
    return records.get(fold_identifier(datatype_text))


def _find_field(record: DataType, name: str) -> Variable | None:
    key = fold_identifier(name)
    for variable in record.var_list:
        if fold_identifier(variable.name) == key:
            return variable
    return None


def resolve_var_chain(ref: VarRef, scope: Scope, records: dict[str, DataType]) -> tuple[Variable, ...]:
    """Every variable a dotted reference resolves through, root first.

    An empty tuple means the reference does not resolve. The chain exists so a
    write rule can see a ``Const`` root: the leaf field of ``Rec.Field`` carries
    its own modifiers, not the root's.
    """
    parts = ref.name.split(".")
    current = scope.lookup(parts[0])
    if current is None:
        return ()
    chain = [current]
    for part in parts[1:]:
        record = lookup_datatype(records, current.datatype_text)
        if record is None:
            return ()
        current = _find_field(record, part)
        if current is None:
            return ()
        chain.append(current)
    return tuple(chain)


def resolve_var(ref: VarRef, scope: Scope, records: dict[str, DataType]) -> Variable | None:
    """Resolve a (possibly dotted, possibly :Old/:New) reference to its Variable.

    Returns ``None`` when the reference cannot be resolved to a known variable
    or record field, for example a submodule instance name or an undeclared
    symbol. In that case no rules apply.
    """
    chain = resolve_var_chain(ref, scope, records)
    return chain[-1] if chain else None


def is_const_reference(ref: VarRef, scope: Scope, records: dict[str, DataType]) -> bool:
    """True when any segment of a resolved reference is declared ``Const``."""
    return any(variable.const for variable in resolve_var_chain(ref, scope, records))
