"""Strict single-source validation of a parsed SattLine BasePicture.

Walks the transformed AST and reports intra-file, well-formedness diagnostics
that a SattLine compiler would reject at its "validation" stage. Project-graph
concerns (contract mismatches, graphics correlation, datecode conflicts) are
deliberately out of scope and are added by the project loader.

Use :func:`validate_basepicture` directly, or the ``parse_and_validate`` entry
point in :mod:`sattline_parser.api`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import cast

from sattline_parser.builtins.records import BUILTIN_RECORD_SPECS
from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    FloatLiteral,
    FrameModule,
    IntLiteral,
    ModuleDef,
    ModuleHeader,
    ModuleTypeDef,
    ModuleTypeInstance,
    ParameterMapping,
    SingleModule,
    Variable,
)
from sattline_parser.names import fold_identifier
from sattline_parser.validation.annotations import check_annotation_tails
from sattline_parser.validation.code import (
    ValidationContext,
    collect_program_sfc_names,
    walk_module_code,
)
from sattline_parser.validation.declarations import (
    check_identifiers,
    check_record_fields,
    check_sibling_submodules,
    check_variable_declarations,
)
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.parameter_mappings import check_parameter_mappings
from sattline_parser.validation.symbols import Scope, build_scope
from sattline_parser.validation.transfers import check_parameter_transfers
from sattline_parser.validation.type_graph import TypeGraph

Submodule = SingleModule | FrameModule | ModuleTypeInstance


@lru_cache(maxsize=1)
def _builtin_record_datatypes() -> tuple[DataType, ...]:
    """Builtin records as AST datatypes, so dotted references resolve."""
    return tuple(
        DataType(
            name=name,
            description=None,
            datecode=None,
            var_list=[Variable(name=field_name, datatype=datatype) for field_name, datatype in specs],
        )
        for name, specs in BUILTIN_RECORD_SPECS.items()
    )


@dataclass(frozen=True)
class _ValidationContext:
    records: dict[str, DataType]
    moduletypes: dict[str, ModuleTypeDef]
    type_graph: TypeGraph
    allow_unresolved_external_datatypes: bool
    sfc_names: frozenset[str]


def _code_context(scope: Scope, context: _ValidationContext, errors: list[Diagnostic]) -> ValidationContext:
    return ValidationContext(
        scope=scope,
        records=context.records,
        type_graph=context.type_graph,
        sfc_names=set(),
        errors=errors,
    )


def _check_annotation_tails(
    container: ModuleHeader | ModuleDef,
    scope: Scope,
    context: _ValidationContext,
    errors: list[Diagnostic],
) -> None:
    """Check annotation tails for a header or module definition in ``scope``."""
    check_annotation_tails(
        container,
        scope,
        context.records,
        context.type_graph,
        context.sfc_names,
        errors,
    )


def _check_parameter_contract(
    mappings: list[ParameterMapping],
    parameters: list[Variable],
    subject: str,
    scope: Scope,
    context: _ValidationContext,
    errors: list[Diagnostic],
) -> None:
    """Run the transfer and mapping rules for one declaration's formals.

    ``scope`` is the scope the mapping sources resolve in: the invoking scope for
    a submodule, the file scope for a module-type definition.
    """
    check_parameter_transfers(mappings, parameters, subject, scope, context.records, context.type_graph, errors)
    expected = {fold_identifier(parameter.name): parameter for parameter in parameters}
    check_parameter_mappings(mappings, expected, scope, context.type_graph, errors)


def _check_numeric_literal_ranges(root: object, errors: list[Diagnostic]) -> None:
    """Report a literal the transformer had to clamp to the language range."""
    stack: list[object] = [root]
    seen: set[int] = set()
    while stack:
        value = stack.pop()
        if isinstance(value, (IntLiteral, FloatLiteral)) and value.clamped:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.NUMERIC_LITERAL_OUT_OF_RANGE,
                    message=(
                        f"Numeric literal {value!r} is outside the supported "
                        "32-bit integer or real range and was clamped"
                    ),
                    span=value.span,
                )
            )
            continue
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            stack.extend(getattr(value, field.name) for field in dataclasses.fields(value))
        elif isinstance(value, Mapping):
            mapping = cast("Mapping[object, object]", value)
            stack.extend(mapping.values())
        elif isinstance(value, (list, tuple)):
            sequence = cast("Sequence[object]", value)
            stack.extend(sequence)


def validate_basepicture(
    bp: BasePicture,
    *,
    external_datatypes: Sequence[DataType] = (),
    external_moduletype_defs: Sequence[ModuleTypeDef] = (),
    allow_unresolved_external_datatypes: bool = False,
) -> tuple[Diagnostic, ...]:
    """Validate a transformed BasePicture; returns all findings (empty when valid).

    ``external_datatypes`` and ``external_moduletype_defs`` are the definitions
    visible from already-loaded dependencies. The project loader passes them and
    leaves ``allow_unresolved_external_datatypes`` off. The flag exists for the
    standalone single-file path, where an unknown name may genuinely be external;
    it suppresses only the unknown-name findings, not typo suggestions or local
    rules.

    The tables are built external-first, so a definition in this file wins over a
    same-named definition from a dependency, and a builtin name is only a
    fallback. Resolution order is therefore file, dependency, builtin.
    """
    errors: list[Diagnostic] = []
    available_datatypes = [*external_datatypes, *bp.datatype_defs]
    available_moduletypes = [*external_moduletype_defs, *bp.moduletype_defs]
    records = {fold_identifier(datatype.name): datatype for datatype in available_datatypes}
    for builtin in _builtin_record_datatypes():
        records.setdefault(fold_identifier(builtin.name), builtin)
    context = _ValidationContext(
        records=records,
        moduletypes={fold_identifier(moduletype.name): moduletype for moduletype in available_moduletypes},
        type_graph=TypeGraph.from_datatypes(available_datatypes),
        allow_unresolved_external_datatypes=allow_unresolved_external_datatypes,
        sfc_names=collect_program_sfc_names(bp),
    )

    check_identifiers(bp, errors)
    _check_numeric_literal_ranges(bp, errors)
    base_scope = build_scope(None, [*bp.moduleparameters, *bp.localvariables])
    check_variable_declarations(
        [*bp.moduleparameters, *bp.localvariables],
        context.records,
        errors,
        allow_unresolved_external_datatypes=allow_unresolved_external_datatypes,
    )
    check_record_fields(
        context.records,
        errors,
        owned_records=bp.datatype_defs,
        allow_unresolved_external_datatypes=allow_unresolved_external_datatypes,
    )
    check_sibling_submodules(bp.submodules, errors)
    _check_annotation_tails(bp.header, base_scope, context, errors)
    if bp.moduledef is not None:
        _check_annotation_tails(bp.moduledef, base_scope, context, errors)

    if bp.modulecode is not None:
        walk_module_code(
            bp.modulecode,
            _code_context(base_scope, context, errors),
            program_sfc_names=context.sfc_names,
        )
    for child in bp.submodules:
        _walk_submodule(child, base_scope, context, errors)
    for moduletype in bp.moduletype_defs:
        _walk_moduletype_def(moduletype, context, errors)

    return tuple(errors)


def _walk_submodule(
    child: Submodule,
    parent: Scope,
    context: _ValidationContext,
    errors: list[Diagnostic],
) -> None:
    _check_annotation_tails(child.header, parent, context, errors)
    if isinstance(child, ModuleTypeInstance):
        moduletype = context.moduletypes.get(fold_identifier(child.moduletype_name))
        if moduletype is None:
            if not context.allow_unresolved_external_datatypes:
                errors.append(
                    Diagnostic(
                        code=DiagnosticCode.UNKNOWN_MODULETYPE_NAME,
                        message=(
                            f"Module type {child.moduletype_name!r} is neither declared in this file "
                            "nor visible from a loaded dependency"
                        ),
                        span=child.header.declaration_span,
                    )
                )
            # The formals are unknown, so only the local mapping rules apply:
            # a duplicate target is a defect regardless of where the type lives.
            check_parameter_mappings(child.parametermappings, None, parent, context.type_graph, errors)
            return
        _check_parameter_contract(
            child.parametermappings,
            moduletype.moduleparameters,
            f"Submodule {child.header.name}",
            parent,
            context,
            errors,
        )
        return
    scope = _child_scope(child, parent)
    if isinstance(child, SingleModule):
        _check_parameter_contract(
            child.parametermappings,
            child.moduleparameters,
            f"Submodule {child.header.name}",
            parent,
            context,
            errors,
        )
    _walk_definition(child, scope, context, errors)


def _walk_moduletype_def(
    moduletype: ModuleTypeDef,
    context: _ValidationContext,
    errors: list[Diagnostic],
) -> None:
    # A module type definition carries no parameter mapping: the grammar has no
    # ``moduletype_par_list`` on ``moduletype_definition``, and a mapping belongs
    # to the submodule or module-type instance that invokes it.
    scope = build_scope(None, [*moduletype.moduleparameters, *moduletype.localvariables])
    check_variable_declarations(
        [*moduletype.moduleparameters, *moduletype.localvariables],
        context.records,
        errors,
        allow_unresolved_external_datatypes=context.allow_unresolved_external_datatypes,
    )
    check_sibling_submodules(moduletype.submodules, errors)
    if moduletype.moduledef is not None:
        _check_annotation_tails(moduletype.moduledef, scope, context, errors)
    if moduletype.modulecode is not None:
        walk_module_code(
            moduletype.modulecode,
            _code_context(scope, context, errors),
            program_sfc_names=context.sfc_names,
        )
    for child in moduletype.submodules:
        _walk_submodule(child, scope, context, errors)


def _child_scope(child: SingleModule | FrameModule, parent: Scope) -> Scope:
    return build_scope(parent, [*_module_parameters(child), *_local_variables(child)])


def _module_parameters(child: SingleModule | FrameModule) -> list[Variable]:
    return child.moduleparameters


def _local_variables(child: SingleModule | FrameModule) -> list[Variable]:
    return child.localvariables


def _walk_definition(
    child: SingleModule | FrameModule,
    scope: Scope,
    context: _ValidationContext,
    errors: list[Diagnostic],
) -> None:
    parameters = _module_parameters(child)
    notes = _local_variables(child)
    check_variable_declarations(
        [*parameters, *notes],
        context.records,
        errors,
        allow_unresolved_external_datatypes=context.allow_unresolved_external_datatypes,
    )
    check_sibling_submodules(child.submodules, errors)
    if child.moduledef is not None:
        _check_annotation_tails(child.moduledef, scope, context, errors)
    if child.modulecode is not None:
        walk_module_code(
            child.modulecode,
            _code_context(scope, context, errors),
            program_sfc_names=context.sfc_names,
        )
    for sub in child.submodules:
        _walk_submodule(sub, scope, context, errors)
