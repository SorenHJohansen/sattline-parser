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
from sattline_parser.validation.type_graph import TypeGraph
from sattline_parser.validation.typing import (
    builtin_type_matches,
    format_datatype,
    resolve_variable_field_datatype,
    split_dotted_name,
)


def check_parameter_transfers(
    mappings: list[ParameterMapping],
    parameters: list[Variable],
    subject: str,
    scope: Scope,
    records: dict[str, DataType],
    type_graph: TypeGraph,
    errors: list[Diagnostic],
) -> None:
    """Flag parameter transfers whose variable type mismatches the declared type.

    ``parameters`` are the formals the mappings target, ``subject`` names the
    declaration in the sentence (``Submodule Child`` or ``Module type T``), and
    ``scope`` is the scope the mapping sources resolve in. A dotted target
    resolves through the type graph, so ``Settings.Flag => Counter`` is compared
    against the field's datatype rather than the record's.
    """
    formals = {fold_identifier(parameter.name): parameter for parameter in parameters}
    for mapping in mappings:
        base_name, field_path = split_dotted_name(mapping.target.name)
        formal = formals.get(fold_identifier(base_name))
        if formal is None:
            continue
        target_datatype = resolve_variable_field_datatype(formal, field_path, type_graph)
        if target_datatype is None:
            # An unresolved field is the mapping-target rule's finding.
            continue
        if mapping.source is None or mapping.is_source_global:
            continue
        source = resolve_var(mapping.source, scope, records)
        if source is None:
            continue
        if builtin_type_matches(source.datatype, target_datatype, direction="in"):
            continue
        errors.append(
            Diagnostic(
                code=DiagnosticCode.PARAM_TRANSFER_TYPE_MISMATCH,
                message=(
                    f"{subject}, parameter {formal.name}: "
                    f"Variable {source.name} is an invalid type "
                    f"({source.datatype_text} for {format_datatype(target_datatype)})"
                ),
                span=mapping.span,
            )
        )


__all__ = ["check_parameter_transfers"]
