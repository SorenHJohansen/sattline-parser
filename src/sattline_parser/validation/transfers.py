"""Parameter-transfer type validation for module-type instances.

The real parser rejects a module-type instance whose parameter transfer
supplies a variable that is not compatible with the declared parameter
datatype — e.g. mapping an integer counter into a boolean parameter yields
``Submodule Child, parameter EnableFlag: Variable CounterValue is an invalid
type``.  This is the single-file half of the cross-module contract: it is only
resolvable when the module type is declared in the same file (its parameters
are then known). Transfers into module types declared in another file remain
consumer/project-graph territory.
"""

from __future__ import annotations

from sattline_parser.models.ast_model import (
    DataType,
    ModuleTypeDef,
    ModuleTypeInstance,
    Simple_DataType,
    Variable,
)
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.symbols import Scope, resolve_var

_ANYTYPE = "anytype"

_NUMERIC_TYPES: frozenset[Simple_DataType] = frozenset(
    {Simple_DataType.INTEGER, Simple_DataType.REAL}
)


def _source_type_compatible(source: Variable, formal: Variable) -> bool:
    if formal.datatype_text.casefold() == _ANYTYPE:
        return True
    source_builtin = isinstance(source.datatype, Simple_DataType)
    formal_builtin = isinstance(formal.datatype, Simple_DataType)
    if source_builtin and formal_builtin:
        if source.datatype == formal.datatype:
            return True
        return source.datatype in _NUMERIC_TYPES and formal.datatype in _NUMERIC_TYPES
    if source_builtin or formal_builtin:
        return False
    return source.datatype_text.casefold() == formal.datatype_text.casefold()


def check_moduletype_transfers(
    instance: ModuleTypeInstance,
    moduletype: ModuleTypeDef,
    scope: Scope,
    records: dict[str, DataType],
    errors: list[Diagnostic],
) -> None:
    """Flag parameter transfers whose variable type mismatches the declared type."""
    parameters = {parameter.name.casefold(): parameter for parameter in moduletype.moduleparameters}
    for mapping in instance.parametermappings:
        formal = parameters.get(mapping.target.name.casefold())
        if formal is None:
            continue
        if mapping.source is None or mapping.is_source_global:
            continue
        source = resolve_var(mapping.source, scope, records)
        if source is None:
            continue
        if _source_type_compatible(source, formal):
            continue
        errors.append(
            Diagnostic(
                code=DiagnosticCode.PARAM_TRANSFER_TYPE_MISMATCH,
                message=(
                    f"Submodule {instance.header.name}, parameter {formal.name}: "
                    f"Variable {source.name} is an invalid type "
                    f"({source.datatype_text} for {formal.datatype_text})"
                ),
                span=mapping.span,
            )
        )
