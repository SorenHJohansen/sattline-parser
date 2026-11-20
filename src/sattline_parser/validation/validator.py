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
from sattline_parser.errors import SourceTooDeepError
from sattline_parser.models import walk
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
    collect_program_sfc_facts,
    walk_module_code,
)
from sattline_parser.validation.declarations import (
    check_identifiers,
    check_moduletype_identifiers,
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

#: Deepest AST node nesting :func:`validate_basepicture` accepts.
#:
#: The expression and statement rules of this pass are recursive, and a
#: hand-built tree can be deeper than the Python call stack allows. Parsed input
#: is already capped by ``source_io.MAX_SOURCE_DEPTH`` (256), so the same bound
#: is used here: anything the parser accepts validates, and a manual tree past
#: the bound is rejected with the documented nesting error instead of raising a
#: bare ``RecursionError``. ``tests/parser/test_validation_depth.py`` pins the
#: equality with the parser bound.
MAX_VALIDATED_DEPTH = 256


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
    sfc_accessors: Mapping[str, frozenset[str]]


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
    check_parameter_mappings(
        mappings,
        expected,
        scope,
        context.type_graph,
        errors,
        sfc_names=context.sfc_names,
        sfc_accessors=context.sfc_accessors,
    )


def _check_numeric_literal_ranges(root: object, errors: list[Diagnostic]) -> None:
    """Report a literal the transformer had to clamp to the language range."""
    stack: list[object] = [root]
    seen: set[int] = set()
    while stack:
        value = stack.pop()
        if isinstance(value, (IntLiteral, FloatLiteral)) and value.clamped:
            # ``value`` holds the clamped number, so the sentence quotes the text
            # the source wrote instead. A hand-built literal may carry no written
            # text; then the stored value is the only spelling there is.
            written = value.written if value.written is not None else str(value)
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.NUMERIC_LITERAL_OUT_OF_RANGE,
                    message=(
                        f"The numeric literal {written} is outside the supported "
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


def _reject_over_deep_tree(bp: BasePicture) -> None:
    """Refuse a tree the recursive expression rules cannot visit.

    ``walk`` is iterative and exposes the ancestor chain length, so the check
    itself cannot exhaust the call stack and costs one linear pass.
    """
    depth = max((len(event.parents) + 1 for event in walk(bp)), default=0)
    if depth > MAX_VALIDATED_DEPTH:
        raise SourceTooDeepError(MAX_VALIDATED_DEPTH)


def _validation_context(
    bp: BasePicture,
    external_datatypes: Sequence[DataType],
    external_moduletype_defs: Sequence[ModuleTypeDef],
    allow_unresolved_external_datatypes: bool,
    *,
    sfc_names: frozenset[str],
    sfc_accessors: Mapping[str, frozenset[str]],
) -> _ValidationContext:
    available_datatypes = [*external_datatypes, *bp.datatype_defs]
    available_moduletypes = [*external_moduletype_defs, *bp.moduletype_defs]
    # A transcription cannot state a State, Const, or OpSave modifier, so a
    # declared record of the same name replaces it. The local file wins over a
    # dependency definition, and both win over the builtin fallback.
    records = {fold_identifier(datatype.name): datatype for datatype in _builtin_record_datatypes()}
    for datatype in available_datatypes:
        records[fold_identifier(datatype.name)] = datatype
    return _ValidationContext(
        records=records,
        moduletypes={fold_identifier(moduletype.name): moduletype for moduletype in available_moduletypes},
        type_graph=TypeGraph.from_datatypes(bp.datatype_defs, fallback=external_datatypes),
        allow_unresolved_external_datatypes=allow_unresolved_external_datatypes,
        sfc_names=sfc_names,
        sfc_accessors=sfc_accessors,
    )


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

    A declared record wins over a builtin transcription of the same name, and a
    file definition wins over a same-named dependency definition.

    Raises :class:`~sattline_parser.errors.SourceTooDeepError` when the node
    nesting is deeper than :data:`MAX_VALIDATED_DEPTH`. Parsed input never
    reaches that bound, because the parser rejects it first; a hand-built tree
    does, and the recursive expression rules cannot visit it safely.
    """
    _reject_over_deep_tree(bp)
    errors: list[Diagnostic] = []
    sfc_names, sfc_accessors = collect_program_sfc_facts(bp)
    context = _validation_context(
        bp,
        external_datatypes,
        external_moduletype_defs,
        allow_unresolved_external_datatypes,
        sfc_names=sfc_names,
        sfc_accessors=sfc_accessors,
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
            program_sfc_accessors=context.sfc_accessors,
        )
    for child in bp.submodules:
        _walk_submodule(child, base_scope, context, errors)
    for moduletype in bp.moduletype_defs:
        _walk_moduletype_def(moduletype, context, errors)

    return tuple(errors)


def validate_moduletype_definitions(
    bp: BasePicture,
    selected: BasePicture,
    *,
    external_datatypes: Sequence[DataType] = (),
    external_moduletype_defs: Sequence[ModuleTypeDef] = (),
) -> tuple[Diagnostic, ...]:
    """Validate selected module types using the containing picture's type shapes."""
    _reject_over_deep_tree(bp)
    sfc_names, sfc_accessors = collect_program_sfc_facts(selected)
    context = _validation_context(
        bp,
        external_datatypes,
        external_moduletype_defs,
        False,
        sfc_names=sfc_names,
        sfc_accessors=sfc_accessors,
    )
    errors: list[Diagnostic] = []
    for moduletype in selected.moduletype_defs:
        check_moduletype_identifiers(moduletype, errors)
    _check_numeric_literal_ranges(selected.moduletype_defs, errors)
    for moduletype in selected.moduletype_defs:
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
            # The formals are unknown, so the target side needs the formal
            # list and stays silent; a live source is still checked.
            check_parameter_mappings(
                child.parametermappings,
                None,
                parent,
                context.type_graph,
                errors,
                sfc_names=context.sfc_names,
                sfc_accessors=context.sfc_accessors,
            )
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
    # A single module and a frame module both declare formals and carry a
    # mapping tail, so both get the transfer and mapping contract.
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
            program_sfc_accessors=context.sfc_accessors,
        )
    for child in moduletype.submodules:
        _walk_submodule(child, scope, context, errors)


def _child_scope(child: SingleModule | FrameModule, parent: Scope) -> Scope:
    if isinstance(child, FrameModule):
        return parent
    return build_scope(None, [*_module_parameters(child), *_local_variables(child)])


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
            program_sfc_accessors=context.sfc_accessors,
        )
    for sub in child.submodules:
        _walk_submodule(sub, scope, context, errors)
