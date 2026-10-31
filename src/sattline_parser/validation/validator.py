"""Strict single-source validation of a parsed SattLine BasePicture.

Walks the transformed AST and reports intra-file, well-formedness diagnostics
that a SattLine compiler would reject at its "validation" stage. Project-graph
and cross-module concerns (contract mismatches, graphics correlation) are
deliberately out of scope and remain with the consumer.

Use :func:`validate_basepicture` directly, or the ``parse_and_validate`` entry
point in :mod:`sattline_parser.api`.
"""

from __future__ import annotations

from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    FrameModule,
    ModuleTypeDef,
    ModuleTypeInstance,
    SingleModule,
    Variable,
)
from sattline_parser.validation.code import check_coordinate_tail_types, walk_module_code
from sattline_parser.validation.declarations import (
    check_identifiers,
    check_record_fields,
    check_reserved_name_declarations,
    check_sibling_submodules,
    check_variable_declarations,
)
from sattline_parser.validation.diagnostics import Diagnostic
from sattline_parser.validation.names import fold_identifier
from sattline_parser.validation.parameter_mappings import check_parameter_mappings
from sattline_parser.validation.symbols import Scope, build_scope
from sattline_parser.validation.transfers import check_moduletype_transfers
from sattline_parser.validation.type_graph import TypeGraph

Submodule = SingleModule | FrameModule | ModuleTypeInstance


def validate_basepicture(bp: BasePicture) -> tuple[Diagnostic, ...]:
    """Validate a transformed BasePicture; returns all findings (empty when valid)."""
    errors: list[Diagnostic] = []
    records = {fold_identifier(datatype.name): datatype for datatype in bp.datatype_defs}
    moduletypes = {fold_identifier(moduletype.name): moduletype for moduletype in bp.moduletype_defs}
    type_graph = TypeGraph.from_datatypes(bp.datatype_defs)

    check_reserved_name_declarations(bp, errors)
    check_identifiers(bp, errors)
    base_scope = build_scope(None, bp.localvariables)
    check_variable_declarations(bp.localvariables, records, errors)
    check_record_fields(records, errors)
    check_sibling_submodules(bp.submodules, errors)
    for module_def in bp.moduledefs:
        check_coordinate_tail_types(module_def, base_scope, records, errors)

    for code in bp.modulecodes:
        walk_module_code(code, base_scope, records, errors)
    for child in bp.submodules:
        _walk_submodule(child, base_scope, records, moduletypes, type_graph, errors)
    for moduletype in bp.moduletype_defs:
        _walk_moduletype_def(moduletype, records, moduletypes, type_graph, errors)

    return tuple(errors)


def _walk_submodule(
    child: Submodule,
    parent: Scope,
    records: dict[str, DataType],
    moduletypes: dict[str, ModuleTypeDef],
    type_graph: TypeGraph,
    errors: list[Diagnostic],
) -> None:
    if isinstance(child, ModuleTypeInstance):
        moduletype = moduletypes.get(fold_identifier(child.moduletype_name))
        if moduletype is not None:
            check_moduletype_transfers(child, moduletype, parent, records, errors)
            expected = {fold_identifier(parameter.name): parameter for parameter in moduletype.moduleparameters}
            check_parameter_mappings(child.parametermappings, expected, parent, type_graph, errors)
        return
    scope = _child_scope(child, parent)
    _walk_definition(child, scope, records, moduletypes, type_graph, errors)


def _walk_moduletype_def(
    moduletype: ModuleTypeDef,
    records: dict[str, DataType],
    moduletypes: dict[str, ModuleTypeDef],
    type_graph: TypeGraph,
    errors: list[Diagnostic],
) -> None:
    scope = build_scope(None, [*moduletype.moduleparameters, *moduletype.localvariables])
    check_variable_declarations([*moduletype.moduleparameters, *moduletype.localvariables], records, errors)
    check_sibling_submodules(moduletype.submodules, errors)
    for code in moduletype.modulecodes:
        walk_module_code(code, scope, records, errors)
    for child in moduletype.submodules:
        _walk_submodule(child, scope, records, moduletypes, type_graph, errors)


def _child_scope(child: SingleModule | FrameModule, parent: Scope) -> Scope:
    return build_scope(parent, [*_module_parameters(child), *_local_variables(child)])


def _module_parameters(child: SingleModule | FrameModule) -> list[Variable]:
    if isinstance(child, SingleModule):
        return child.moduleparameters
    return []


def _local_variables(child: SingleModule | FrameModule) -> list[Variable]:
    if isinstance(child, SingleModule):
        return child.localvariables
    return []


def _walk_definition(
    child: SingleModule | FrameModule,
    scope: Scope,
    records: dict[str, DataType],
    moduletypes: dict[str, ModuleTypeDef],
    type_graph: TypeGraph,
    errors: list[Diagnostic],
) -> None:
    parameters = _module_parameters(child)
    notes = _local_variables(child)
    check_variable_declarations([*parameters, *notes], records, errors)
    check_sibling_submodules(child.submodules, errors)
    for module_def in child.moduledefs:
        check_coordinate_tail_types(module_def, scope, records, errors)
    for code in child.modulecodes:
        walk_module_code(code, scope, records, errors)
    for sub in child.submodules:
        _walk_submodule(sub, scope, records, moduletypes, type_graph, errors)
