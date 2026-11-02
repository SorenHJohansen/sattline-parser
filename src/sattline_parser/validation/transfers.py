"""Parameter-transfer type validation for module-type instances.

A module-type instance is rejected when its parameter transfer supplies a
variable that is not compatible with the declared parameter datatype — e.g. mapping an integer counter into a boolean parameter yields
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
    Variable,
)
from sattline_parser.names import fold_identifier
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.symbols import Scope, resolve_var
from sattline_parser.validation.typing import builtin_type_matches


def _source_type_compatible(source: Variable, formal: Variable) -> bool:
    return builtin_type_matches(source.datatype, formal.datatype, direction="in")


def check_moduletype_transfers(
    instance: ModuleTypeInstance,
    moduletype: ModuleTypeDef,
    scope: Scope,
    records: dict[str, DataType],
    errors: list[Diagnostic],
) -> None:
    """Flag parameter transfers whose variable type mismatches the declared type."""
    parameters = {fold_identifier(parameter.name): parameter for parameter in moduletype.moduleparameters}
    for mapping in instance.parametermappings:
        formal = parameters.get(fold_identifier(mapping.target.name))
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
