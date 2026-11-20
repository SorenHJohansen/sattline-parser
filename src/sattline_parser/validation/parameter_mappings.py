"""Parameter mapping rules for submodule declarations and module-type instances.

A mapping connects an actual source (a variable, a literal, or a global) to a
formal module parameter. This module checks the target side (field access and
unknown targets) and the value side (literal and variable datatypes). The same
checks run for a module-type instance, a plain submodule declaration, and a
module-type definition.

An absent mapping target is silent: SattLine keeps a mapping after its formal
parameter is deleted from the definition, so the clause is inert and its source
is not checked either. A target that does exist is live, and its source must
then resolve in the invoking scope: SattLine rejects a live mapping whose source
variable is undeclared. An ``:Old``/``:New`` suffix on a resolved non-State
source is reported as well.

A repeated target is accepted by the language and is not reported. The first
entry for a target is the one the instance uses, so a later entry with the same
target is discarded and neither its source nor its datatype is checked. Module
types and datatypes visible from loaded dependencies are passed in by the
project layer, so a mapping that targets an external typedef resolves the same
way as a local one. An instance may omit mappings entirely; only the mappings
that are present are checked.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from sattline_parser.models.ast_model import ParameterMapping, ScalarDatatype, Variable
from sattline_parser.names import fold_identifier
from sattline_parser.validation.code import check_old_new
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.symbols import Scope
from sattline_parser.validation.type_graph import TypeGraph
from sattline_parser.validation.typing import (
    extract_time_literal,
    format_datatype,
    has_time_literal_marker,
    infer_literal_datatype,
    is_sfc_runtime_accessor,
    is_valid_duration_literal,
    is_valid_time_literal,
    literal_matches_expected_datatype,
    resolve_ref_datatype,
    resolve_ref_state,
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
    *,
    sfc_names: Collection[str] = frozenset(),
    sfc_accessors: Mapping[str, frozenset[str]] | None = None,
) -> None:
    """Check field access, unknown targets, and value datatypes.

    A mapping whose target the known formal list does not declare is a deleted
    formal, not a typo. SattLine keeps the mapping after the parameter is
    removed, so the whole clause is inert and its source is not checked either.
    ``expected_parameters=None`` means the formals come from a definition that
    is not loaded, so the target stays unproven while a source is still checked.

    A live mapping source must resolve in the invoking scope. ``sfc_names`` and
    ``sfc_accessors`` carry the program-wide SFC facts, because a source may name
    a sequence declared in another module of the same program
    (``StateReset => StateSequence.Reset``), which the module variable scope
    alone cannot see.

    A repeated target is accepted by the language. The first entry is the one
    the instance uses, so a later entry with the same target is discarded and
    neither its source nor its datatype is checked.
    """
    accessors: Mapping[str, frozenset[str]] = sfc_accessors or {}
    seen: set[str] = set()
    for mapping in mappings:
        target_name = mapping.target.name
        target_key = fold_identifier(target_name)
        base_name, field_path = split_dotted_name(target_name)
        target_variable: Variable | None = None
        if expected_parameters is not None:
            target_variable = expected_parameters.get(fold_identifier(base_name))
            if target_variable is None:
                # A formal removed from the definition leaves the mapping in
                # place; the language keeps it and the clause has no effect, so
                # neither its target nor its source is a finding.
                continue
        if target_key in seen:
            # A repeated target keeps its first entry; this one is discarded.
            continue
        seen.add(target_key)

        # The source resolves in the invoking scope, so an undeclared live
        # source is a defect. A sequence control accessor is not a variable and
        # resolves through the program-wide SFC facts instead.
        source_datatype: ScalarDatatype | str | None = None
        if mapping.source is not None and not mapping.is_source_global:
            source_datatype = resolve_ref_datatype(mapping.source, scope, type_graph)
            if (
                source_datatype is None
                and unresolved_reference_is_a_defect(mapping.source, scope, type_graph)
                and not is_sfc_runtime_accessor(mapping.source, sfc_names, accessors)
            ):
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.UNDEFINED_VARIABLE,
                        message=f"Parameter mapping source {mapping.source.name!r} is not a defined variable",
                        span=mapping.span,
                    )
                )
            check_old_new(mapping.source, resolve_ref_state(mapping.source, scope, type_graph), errors)

        if target_variable is None:
            continue

        target_datatype = resolve_variable_field_datatype(target_variable, field_path, type_graph)
        if field_path and target_datatype is None:
            if isinstance(target_variable.datatype, ScalarDatatype):
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
                        message=(
                            f"Parameter mapping target {target_name!r} is not a field in the resolved "
                            f"definition of parameter {target_variable.name!r}"
                        ),
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
    source_datatype: ScalarDatatype | str | None,
    errors: list[Diagnostic],
) -> tuple[ScalarDatatype | str | None, str | None]:
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
