"""Parameter-transfer type validation for submodules and module types.

A submodule declaration or module-type instance is rejected when its parameter
transfer supplies a variable that is not compatible with the declared parameter
datatype, for example mapping an integer counter into a boolean parameter yields
``Submodule Child, parameter EnableFlag: Variable CounterValue is an invalid
type``. This is the single-file half of the cross-module contract: it is only
resolvable when the formals are known, because they are declared in this file or
in a loaded dependency. Transfers into a definition that is not loaded remain
consumer/project-graph territory.
"""

from __future__ import annotations

from sattline_parser.models.ast_model import (
    DataType,
    ParameterMapping,
    Variable,
)
from sattline_parser.names import fold_identifier
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.symbols import Scope, resolve_var
from sattline_parser.validation.typing import builtin_type_matches


def _source_type_compatible(source: Variable, formal: Variable) -> bool:
    return builtin_type_matches(source.datatype, formal.datatype, direction="in")


def check_parameter_transfers(
    mappings: list[ParameterMapping],
    parameters: list[Variable],
    subject: str,
    scope: Scope,
    records: dict[str, DataType],
    errors: list[Diagnostic],
) -> None:
    """Flag parameter transfers whose variable type mismatches the declared type.

    ``parameters`` are the formals the mappings target, ``subject`` names the
    declaration in the sentence (``Submodule Child`` or ``Module type T``), and
    ``scope`` is the scope the mapping sources resolve in.
    """
    formals = {fold_identifier(parameter.name): parameter for parameter in parameters}
    for mapping in mappings:
        formal = formals.get(fold_identifier(mapping.target.name))
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
                    f"{subject}, parameter {formal.name}: "
                    f"Variable {source.name} is an invalid type "
                    f"({source.datatype_text} for {formal.datatype_text})"
                ),
                span=mapping.span,
            )
        )


__all__ = ["check_parameter_transfers"]
