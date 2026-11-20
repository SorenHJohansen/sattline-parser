"""Declaration-level validation rules for a parsed BasePicture.

Rules here are intra-file and operate on the transformed AST: sibling submodule
uniqueness, declaration-modifier combinations, built-in datatype name typos and
unknown datatype references.

A rule only lives here if it is enforced. Several plausible rules were
implemented and then removed because the editor's UI refuses to create such a
declaration while the same source loads and parses from disk; see
:data:`sattline_parser.validation.rules.RETIRED_CODES`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sattline_parser.builtins.records import BUILTIN_RECORD_SPECS
from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    FrameModule,
    ModuleCode,
    ModuleTypeDef,
    ModuleTypeInstance,
    ScalarDatatype,
    SFCAlternative,
    SFCBodyItem,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
    SingleModule,
    SourceSpan,
    Variable,
)
from sattline_parser.names import fold_identifier
from sattline_parser.validation.builtins import builtin_datatype_typo
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode

Submodule = SingleModule | FrameModule | ModuleTypeInstance

# Datatype names the SattLine language accepts that are not modelled as
# ScalarDatatype nor declared via TYPEDEFINITIONS. GroupData is the reserved
# scan-group connection type used by module definitions with a GroupConn tail.
#: System datatypes the language accepts without a local definition and without a
#: field table. Every other system datatype resolves through
#: :data:`BUILTIN_RECORD_SPECS`; these three either have no fields at all
#: (``AnyType``) or are plain aliases of a scalar / of ``tObject``.
_VALID_UNRESOLVED_DATATYPES = frozenset(
    fold_identifier(name)
    for name in (
        "anytype",
        "textfile",
        "window",
    )
)

#: Builtin record names are declared datatypes too; a variable may name one
#: without a local DATATYPE definition.
_BUILTIN_RECORD_KEYS = frozenset(fold_identifier(name) for name in BUILTIN_RECORD_SPECS)

_MAX_IDENTIFIER_LENGTH = 20
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _build_reserved_identifier_keywords() -> frozenset[str]:
    reserved: set[str] = set()
    values: list[object] = [getattr(const, name) for name in dir(const) if name.startswith("GRAMMAR_VALUE_")]
    values.extend(const.BOOL_SPELLINGS)
    for value in values:
        if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
            continue
        reserved.add(fold_identifier(value))
    return frozenset(reserved)


_RESERVED_IDENTIFIER_KEYWORDS = _build_reserved_identifier_keywords()


def _identifier_length(name: str) -> int:
    if len(name) >= 2 and name.startswith("'") and name.endswith("'"):
        return len(name[1:-1])
    return len(name)


def check_identifier(
    name: str | None,
    what: str,
    span: SourceSpan | None,
    errors: list[Diagnostic],
    *,
    check_reserved_keywords: bool = True,
) -> None:
    """Flag identifiers that exceed the language limit or reuse a keyword."""
    if not name:
        return
    if _identifier_length(name) > _MAX_IDENTIFIER_LENGTH:
        errors.append(
            Diagnostic(
                code=DiagnosticCode.IDENTIFIER_TOO_LONG,
                message=f"{what} name {name!r} exceeds {_MAX_IDENTIFIER_LENGTH} characters",
                span=span,
            )
        )
    quoted = len(name) >= 2 and name.startswith("'") and name.endswith("'")
    if check_reserved_keywords and not quoted and fold_identifier(name) in _RESERVED_IDENTIFIER_KEYWORDS:
        errors.append(
            Diagnostic(
                code=DiagnosticCode.RESERVED_KEYWORD_NAME,
                message=f"{what} name {name!r} is a reserved SattLine keyword",
                span=span,
            )
        )


def check_identifiers(bp: BasePicture, errors: list[Diagnostic]) -> None:
    """Check every named declaration and SFC element in the picture."""
    check_identifier(bp.header.name, "BasePicture", bp.header.declaration_span, errors, check_reserved_keywords=False)
    for datatype in bp.datatype_defs:
        check_identifier(datatype.name, "Datatype", datatype.declaration_span, errors)
        for variable in datatype.var_list:
            check_identifier(variable.name, "Variable", variable.declaration_span, errors)
    for moduletype in bp.moduletype_defs:
        check_moduletype_identifiers(moduletype, errors)
    _check_variable_names(bp.moduleparameters, errors)
    _check_variable_names(bp.localvariables, errors)
    if bp.modulecode is not None:
        _check_modulecode_identifiers(bp.modulecode, errors)
    for submodule in bp.submodules:
        _check_submodule_identifiers(submodule, errors)


def check_moduletype_identifiers(moduletype: ModuleTypeDef, errors: list[Diagnostic]) -> None:
    """Check identifiers belonging to one module type."""
    check_identifier(moduletype.name, "Moduletype", moduletype.declaration_span, errors)
    _check_variable_names(moduletype.moduleparameters, errors)
    _check_variable_names(moduletype.localvariables, errors)
    if moduletype.modulecode is not None:
        _check_modulecode_identifiers(moduletype.modulecode, errors)
    for submodule in moduletype.submodules:
        _check_submodule_identifiers(submodule, errors)


def _check_variable_names(variables: list[Variable], errors: list[Diagnostic]) -> None:
    for variable in variables:
        check_identifier(variable.name, "Variable", variable.declaration_span, errors)


def _check_submodule_identifiers(submodule: Submodule, errors: list[Diagnostic]) -> None:
    check_identifier(submodule.header.name, "Submodule", submodule.header.declaration_span, errors)
    if isinstance(submodule, ModuleTypeInstance):
        check_identifier(submodule.moduletype_name, "Module type reference", submodule.header.declaration_span, errors)
        return
    # A frame module declares parameters, locals, and module code like a single
    # module, so its identifiers are checked the same way.
    _check_variable_names(submodule.moduleparameters, errors)
    _check_variable_names(submodule.localvariables, errors)
    if submodule.modulecode is not None:
        _check_modulecode_identifiers(submodule.modulecode, errors)
    for nested in submodule.submodules:
        _check_submodule_identifiers(nested, errors)


def _check_modulecode_identifiers(modulecode: ModuleCode, errors: list[Diagnostic]) -> None:
    for equation in modulecode.equationblocks or ():
        check_identifier(equation.name, "Equation", equation.declaration_span, errors)
    for sequence in modulecode.sequences or ():
        check_identifier(sequence.name, "Sequence", sequence.declaration_span, errors)
        _check_sequence_identifiers(sequence.code, errors)


def _check_sequence_identifiers(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    for item in items:
        name: str | None = None
        span: SourceSpan | None = None
        if isinstance(item, (SFCStep, SFCTransition, SFCTransitionSub, SFCSubsequence)):
            name = item.name
            span = item.span
        if name:
            check_identifier(name, "Sequence element", span, errors)
        if isinstance(item, (SFCStep, SFCTransition)) and item.fork is not None:
            for target in item.fork.targets:
                check_identifier(target, "Fork target", span, errors)
        if isinstance(item, (SFCAlternative, SFCParallel)):
            for branch in item.branches:
                _check_sequence_identifiers(branch, errors)
        elif isinstance(item, (SFCSubsequence, SFCTransitionSub)):
            _check_sequence_identifiers(item.body, errors)


def _sibling_scope(child: Submodule) -> str:
    """The declaration scope a sibling label belongs to.

    A module-type instance is scoped by its module type, so two instances of
    different types may share a label. A single module and a frame module are
    each scoped by kind.
    """
    if isinstance(child, ModuleTypeInstance):
        return f"module-type instance {child.moduletype_name!r}"
    if isinstance(child, FrameModule):
        return "frame module"
    return "single module"


def check_sibling_submodules(submodules: list[Submodule], errors: list[Diagnostic]) -> None:
    """Flag duplicate sibling labels in one declaration scope.

    A container may hold a module-type instance, a single module, and a frame
    module with the same label, and two module-type instances may share a label
    when their types differ. Only siblings that share a label and a scope clash.
    """
    seen: set[tuple[str, str]] = set()
    for child in submodules:
        scope = _sibling_scope(child)
        key = (fold_identifier(child.header.name), scope)
        if key in seen:
            description = (
                f"module-type instance {child.header.name!r} of {child.moduletype_name!r}"
                if isinstance(child, ModuleTypeInstance)
                else f"{scope} {child.header.name!r}"
            )
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.DUPLICATE_SIBLING_SUBMODULE,
                    message=f"Sibling {description} is already declared in the same container",
                    span=child.header.declaration_span,
                )
            )
        else:
            seen.add(key)


def check_variable_declarations(
    variables: list[Variable],
    records: dict[str, DataType],
    errors: list[Diagnostic],
    *,
    allow_unresolved_external_datatypes: bool = False,
) -> None:
    """Run per-variable datatype-reference and modifier checks (all scopes and fields)."""
    for variable in variables:
        _check_datatype_reference(
            variable,
            records,
            errors,
            allow_unresolved_external_datatypes=allow_unresolved_external_datatypes,
        )
        _check_attribute_combination(variable, errors)


def check_record_fields(
    records: dict[str, DataType],
    errors: list[Diagnostic],
    *,
    owned_records: Sequence[DataType],
    allow_unresolved_external_datatypes: bool = False,
) -> None:
    """Validate the fields of every record this file owns.

    ``records`` carries every visible record so field datatypes resolve across
    dependencies. ``owned_records`` limits which definitions are validated, so a
    consumer does not repeat findings that belong to a library file. It is a
    sequence, not a folded map, because a file may declare the same datatype name
    twice and each definition is validated on its own.
    """
    for record in owned_records:
        check_variable_declarations(
            record.var_list,
            records,
            errors,
            allow_unresolved_external_datatypes=allow_unresolved_external_datatypes,
        )


def check_type_references(
    bp: BasePicture,
    errors: list[Diagnostic],
    *,
    external_datatypes: Sequence[DataType] = (),
    external_moduletype_defs: Sequence[ModuleTypeDef] = (),
) -> None:
    """Check only declaration type bindings owned by this picture."""
    records = {fold_identifier(record.name): record for record in (*external_datatypes, *bp.datatype_defs)}
    moduletypes = {fold_identifier(item.name) for item in (*external_moduletype_defs, *bp.moduletype_defs)}

    def variables(items: list[Variable]) -> None:
        for variable in items:
            _check_datatype_reference(variable, records, errors)

    for record in bp.datatype_defs:
        variables(record.var_list)
    variables(bp.moduleparameters)
    variables(bp.localvariables)
    for definition in bp.moduletype_defs:
        variables(definition.moduleparameters)
        variables(definition.localvariables)

    pending: list[Submodule] = list(reversed(bp.submodules))
    for definition in reversed(bp.moduletype_defs):
        pending.extend(reversed(definition.submodules))
    while pending:
        child = pending.pop()
        if isinstance(child, ModuleTypeInstance):
            if fold_identifier(child.moduletype_name) not in moduletypes:
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
        else:
            variables(child.moduleparameters)
            variables(child.localvariables)
            pending.extend(reversed(child.submodules))


# The OpSave rule is order-sensitive rather than a symmetric pair:
#   `OpSave State`  -> invalid combination
#   `State OpSave`  -> accepted
#   `OpSave Const`  -> illegal attribute mix
#   `OpSave` alone  -> accepted
# So OpSave must not be followed by State or Const. `OpSave Secure` is not
# covered.
_OPSAVE_TRAILING_MODIFIERS: tuple[str, ...] = ("state", "const")


def _check_attribute_combination(variable: Variable, errors: list[Diagnostic]) -> None:
    """Reject modifier sequences the editor refuses as an invalid combination.

    Only fires when the declared order is known. A ``Variable`` built without
    ``attribute_order`` carries no evidence of sequence, so it stays silent
    rather than guessing - the same "unproven means silent" rule the operand and
    record-field checks use.
    """
    order = variable.attribute_order
    if "opsave" not in order:
        return
    opsave_at = order.index("opsave")
    for modifier in _OPSAVE_TRAILING_MODIFIERS:
        if modifier in order[opsave_at + 1 :]:
            trailing = [order[opsave_at], *order[opsave_at + 1 :]]
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.ATTRIBUTE_COMBINATION_INVALID,
                    message=(
                        f"Variable {variable.name!r} uses the invalid combination of attributes {' '.join(trailing)}"
                    ),
                    span=variable.declaration_span,
                )
            )
            return


def _check_datatype_reference(
    variable: Variable,
    records: dict[str, DataType],
    errors: list[Diagnostic],
    *,
    allow_unresolved_external_datatypes: bool = False,
) -> None:
    if isinstance(variable.datatype, ScalarDatatype):
        return
    name = variable.datatype_text
    folded = fold_identifier(name)
    if folded in records or folded in _BUILTIN_RECORD_KEYS or folded in _VALID_UNRESOLVED_DATATYPES:
        return
    suggestion = builtin_datatype_typo(name)
    if suggestion is not None:
        errors.append(
            Diagnostic(
                code=DiagnosticCode.BUILTIN_DATATYPE_TYPO,
                message=f"Datatype {name!r} looks like a typo for built-in datatype {suggestion!r}",
                span=variable.declaration_span,
            )
        )
        return
    if allow_unresolved_external_datatypes:
        return
    errors.append(
        Diagnostic(
            code=DiagnosticCode.UNKNOWN_DATATYPE_NAME,
            message=f"Datatype {name!r} is neither a built-in datatype nor a declared DATATYPE",
            span=variable.declaration_span,
        )
    )
