"""Declaration-level validation rules for a parsed BasePicture.

Rules here are intra-file and operate on the transformed AST: sibling submodule
uniqueness, declaration-modifier combinations, built-in datatype name typos and
unknown datatype references.

A rule only lives here if it is enforced. Several plausible rules were
implemented and then removed because the editor's UI refuses to create such a
declaration while the same source loads and parses from disk; see
:data:`sattline_parser.validation.diagnostics.RETIRED_CODES`.
"""

from __future__ import annotations

from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    FrameModule,
    ModuleHeader,
    ModuleTypeDef,
    ModuleTypeInstance,
    Simple_DataType,
    SingleModule,
    SourceSpan,
    Variable,
)
from sattline_parser.validation.builtins import builtin_datatype_typo
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.names import fold_identifier
from sattline_parser.validation.symbols import is_sfc_runtime_constant

Submodule = SingleModule | FrameModule | ModuleTypeInstance

# Datatype names the SattLine language accepts that are not modelled as
# Simple_DataType nor declared via TYPEDEFINITIONS. GroupData is the reserved
# scan-group connection type used by module definitions with a GroupConn tail.
_VALID_UNRESOLVED_DATATYPES = frozenset({fold_identifier("groupdata")})


def check_sibling_submodules(submodules: list[Submodule], errors: list[Diagnostic]) -> None:
    """Flag duplicate sibling submodule instance/definition names."""
    seen: dict[str, ModuleHeader] = {}
    for child in submodules:
        key = fold_identifier(child.header.name)
        if key in seen:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.DUPLICATE_SIBLING_SUBMODULE,
                    message=f"Submodule instance {child.header.name!r} is already declared as {seen[key].name!r}",
                    span=child.header.declaration_span,
                )
            )
        else:
            seen[key] = child.header


def check_variable_declarations(
    variables: list[Variable], records: dict[str, DataType], errors: list[Diagnostic]
) -> None:
    """Run per-variable datatype-reference and modifier checks (all scopes and fields)."""
    for variable in variables:
        _check_datatype_reference(variable, records, errors)
        _check_attribute_combination(variable, errors)


def check_record_fields(records: dict[str, DataType], errors: list[Diagnostic]) -> None:
    """Validate each record field's declaration."""
    for record in records.values():
        check_variable_declarations(record.var_list, records, errors)


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


def _check_datatype_reference(variable: Variable, records: dict[str, DataType], errors: list[Diagnostic]) -> None:
    if isinstance(variable.datatype, Simple_DataType):
        return
    name = variable.datatype_text
    folded = fold_identifier(name)
    if folded in records or folded in _VALID_UNRESOLVED_DATATYPES:
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
    errors.append(
        Diagnostic(
            code=DiagnosticCode.UNKNOWN_DATATYPE_NAME,
            message=f"Datatype {name!r} is neither a built-in datatype nor a declared DATATYPE",
            span=variable.declaration_span,
        )
    )


def _declaration_span(item: ModuleTypeDef | DataType | Variable) -> SourceSpan | None:
    return item.declaration_span


def check_reserved_name_declarations(bp: BasePicture, errors: list[Diagnostic]) -> None:
    """Flag declarations that reuse a name reserved for SFC runtime access (SL-V034).

    ``On`` and ``Off`` are readable wherever a boolean is expected, which is why
    reads stay exempt from SL-V019 - but they are reserved words and may not be
    declared. A declaration such as ``On: boolean := False;`` in
    ``LOCALVARIABLES`` is rejected with ``>>>On<<< AliasSym Expected``: at the
    declaration position an alias is expected and the reserved word is found.

    Scope is the *variable* declaration family, meaning locals, module
    parameters and record fields, plus ``DATATYPE`` names. ``MODULETYPE`` names
    are left alone: a moduletype lives in a different namespace. ``GroupData`` is deliberately untouched; it
    is a reserved *datatype* that we intentionally accept as a type name.
    """
    for datatype in bp.datatype_defs:
        _flag_if_reserved(datatype.name, datatype, "Datatype", errors)
        for variable in datatype.var_list:
            _flag_if_reserved(variable.name, variable, "Variable", errors)
    for variable in bp.localvariables:
        _flag_if_reserved(variable.name, variable, "Variable", errors)
    for module in _walk_modules(bp.submodules):
        for variable in (*module.localvariables, *module.moduleparameters):
            _flag_if_reserved(variable.name, variable, "Variable", errors)


def _walk_modules(
    modules: list[SingleModule | FrameModule | ModuleTypeInstance],
) -> list[SingleModule]:
    """Every ``SingleModule`` reachable through nested submodules, in source order."""
    found: list[SingleModule] = []
    for module in modules:
        if isinstance(module, SingleModule):
            found.append(module)
        if isinstance(module, SingleModule | FrameModule):
            found.extend(_walk_modules(module.submodules))
    return found


def _flag_if_reserved(name: str, item: Variable | DataType, what: str, errors: list[Diagnostic]) -> None:
    if is_sfc_runtime_constant(name):
        errors.append(
            Diagnostic(
                code=DiagnosticCode.RESERVED_NAME_DECLARED,
                message=(f"{what} {name!r} uses a name reserved for SFC runtime access (On/Off)"),
                span=_declaration_span(item),
            )
        )
