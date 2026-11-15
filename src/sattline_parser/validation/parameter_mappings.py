"""Parameter mapping rules for submodule declarations and module-type instances.

A mapping connects an actual source (a variable, a literal, or a global) to a
formal module parameter. This module checks the target side (duplicates, field
access, unknown targets) and the value side (literal and variable datatypes).
The same checks run for a module-type instance, a plain submodule declaration,
and a module-type definition.

An absent mapping target is reported when the formal parameter list is known.
``None`` means the formals come from a definition that is not loaded, so the
target stays unproven and silent. Module types and datatypes visible from loaded
dependencies are passed in by the project layer, so a mapping that targets an
external typedef resolves the same way as a local one. An instance may omit
mappings entirely; only the mappings that are present are checked.
"""

from __future__ import annotations

from sattline_parser.models.ast_model import ParameterMapping, Simple_DataType, Variable
from sattline_parser.names import fold_identifier
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.symbols import Scope
from sattline_parser.validation.type_graph import TypeGraph
from sattline_parser.validation.typing import (
    extract_time_literal,
    format_datatype,
    has_time_literal_marker,
    infer_literal_datatype,
    is_valid_duration_literal,
    is_valid_time_literal,
    literal_matches_expected_datatype,
    resolve_ref_datatype,
    resolve_variable_field_datatype,
    split_dotted_name,
    unresolved_reference_is_a_defect,
)


def check_parameter_mappings(
    mappings: list[ParameterMapping],
    expected_parameters: dict[str, Variable] | None,
    scope: Scope,
    type_graph: TypeGraph,
    errors: list[Diagnostic],
) -> None:
    """Check duplicate targets, field access, and value datatypes."""
    seen: dict[str, str] = {}
    for mapping in mappings:
        target_name = mapping.target.name
        target_key = fold_identifier(target_name)
        if target_key in seen:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.PARAMETER_MAPPING_DUPLICATE_TARGET,
                    message=(f"Duplicate parameter mapping target {seen[target_key]!r} and {target_name!r}"),
                    span=mapping.span,
                )
            )
            continue
        seen[target_key] = target_name

        if expected_parameters is None:
            continue

        # The formals are known, so the source must resolve even when the target
        # field itself is opaque. The check runs before the target rules so a
        # typo is not hidden behind an unproven target shape.
        source_datatype: Simple_DataType | str | None = None
        if mapping.source is not None and not mapping.is_source_global:
            source_datatype = resolve_ref_datatype(mapping.source, scope, type_graph)
            if source_datatype is None and unresolved_reference_is_a_defect(mapping.source, scope, type_graph):
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.UNDEFINED_VARIABLE,
                        message=f"Parameter mapping source {mapping.source.name!r} is not a defined variable",
                        span=mapping.span,
                    )
                )
                continue

        base_name, field_path = split_dotted_name(target_name)
        target_variable = expected_parameters.get(fold_identifier(base_name))
        if target_variable is None:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.PARAMETER_MAPPING_TARGET_UNKNOWN,
                    message=f"Parameter mapping target {target_name!r} is not a parameter of the target module",
                    span=mapping.span,
                )
            )
            continue

        target_datatype = resolve_variable_field_datatype(target_variable, field_path, type_graph)
        if field_path and target_datatype is None:
            if isinstance(target_variable.datatype, Simple_DataType):
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.PARAMETER_MAPPING_TARGET_UNKNOWN,
                        message=(
                            f"Parameter mapping target {target_name!r} uses field access on "
                            f"non-record parameter {target_variable.name!r}"
                        ),
                        span=mapping.span,
                    )
                )
            elif type_graph.has_known_fields(str(target_variable.datatype)):
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.PARAMETER_MAPPING_TARGET_UNKNOWN,
                        message=f"Parameter mapping target {target_name!r} does not exist",
                        span=mapping.span,
                    )
                )
            continue

        actual_datatype, source_description = _mapping_source_datatype(mapping, source_datatype, errors)
        if actual_datatype is None:
            continue
        if mapping.source_literal is None:
            # Variable sources are covered by the module-type transfer rule,
            # which reports the same mismatch under its own code.
            continue
        if literal_matches_expected_datatype(mapping.source_literal, target_datatype, is_duration=mapping.is_duration):
            continue
        errors.append(
            Diagnostic(
                code=DiagnosticCode.PARAMETER_MAPPING_TYPE_MISMATCH,
                message=(
                    f"Maps {source_description or 'value'} with datatype "
                    f"{format_datatype(actual_datatype)!r} to parameter target {target_name!r} "
                    f"with datatype {format_datatype(target_datatype)!r}"
                ),
                span=mapping.span,
            )
        )


def _mapping_source_datatype(
    mapping: ParameterMapping,
    source_datatype: Simple_DataType | str | None,
    errors: list[Diagnostic],
) -> tuple[Simple_DataType | str | None, str | None]:
    if mapping.source_literal is not None:
        literal = mapping.source_literal
        if mapping.is_duration and not is_valid_duration_literal(literal):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.PARAMETER_MAPPING_TYPE_MISMATCH,
                    message=f"Maps invalid duration literal {literal!r} to parameter target {mapping.target.name!r}",
                    span=mapping.span,
                )
            )
            return None, None
        if has_time_literal_marker(literal) and not is_valid_time_literal(extract_time_literal(literal)):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.PARAMETER_MAPPING_TYPE_MISMATCH,
                    message=(
                        f"Maps invalid time literal {extract_time_literal(literal)!r} "
                        f"to parameter target {mapping.target.name!r}"
                    ),
                    span=mapping.span,
                )
            )
            return None, None
        return infer_literal_datatype(literal, is_duration=mapping.is_duration), repr(literal)
    if mapping.source is not None and not mapping.is_source_global:
        return source_datatype, mapping.source.name
    return None, None


__all__ = ["check_parameter_mappings"]
