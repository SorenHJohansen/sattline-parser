"""Module-type instance parameter mapping rules.

A mapping connects an actual source (a variable, a literal, or a global) to a
formal module parameter. This module checks the target side (duplicates, field
access, unknown fields) and the value side (literal and variable datatypes).
Module types and datatypes visible from loaded dependencies are passed in by
the project layer, so a mapping that targets an external typedef resolves the
same way as a local one. An instance may omit mappings entirely; only the
mappings that are present are checked.
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

        base_name, field_path = split_dotted_name(target_name)
        target_variable = expected_parameters.get(fold_identifier(base_name))
        if target_variable is None:
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
            elif type_graph.has_record(str(target_variable.datatype)):
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.PARAMETER_MAPPING_TARGET_UNKNOWN,
                        message=f"Parameter mapping target {target_name!r} does not exist",
                        span=mapping.span,
                    )
                )
            continue

        actual_datatype, source_description = _mapping_source_datatype(mapping, scope, type_graph, errors)
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
    scope: Scope,
    type_graph: TypeGraph,
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
        return resolve_ref_datatype(mapping.source, scope, type_graph), mapping.source.name
    return None, None


__all__ = ["check_parameter_mappings"]
