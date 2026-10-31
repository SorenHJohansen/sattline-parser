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

import re

from sattline_parser.grammar import constants as const
from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    FrameModule,
    ModuleCode,
    ModuleHeader,
    ModuleTypeDef,
    ModuleTypeInstance,
    SFCAlternative,
    SFCBodyItem,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
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

_MAX_IDENTIFIER_LENGTH = 20
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_ALLOWED_IDENTIFIER_KEYWORDS = frozenset(fold_identifier(name) for name in ("colour", "newwindow"))
#: On/Off have their own rule (RESERVED_NAME_DECLARED), so keep them out of
#: the general keyword set to avoid reporting the same declaration twice.
_SPECIAL_RESERVED_NAMES = frozenset(fold_identifier(name) for name in ("on", "off"))


def _build_reserved_identifier_keywords() -> frozenset[str]:
    reserved: set[str] = set()
    for name in dir(const):
        if not name.startswith("GRAMMAR_VALUE_"):
            continue
        value = getattr(const, name)
        if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
            continue
        folded = fold_identifier(value)
        if folded in _ALLOWED_IDENTIFIER_KEYWORDS or folded in _SPECIAL_RESERVED_NAMES:
            continue
        reserved.add(folded)
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
        check_identifier(moduletype.name, "Moduletype", moduletype.declaration_span, errors)
        _check_variable_names(moduletype.moduleparameters, errors)
        _check_variable_names(moduletype.localvariables, errors)
        _check_modulecode_identifiers(moduletype.modulecode, errors)
        for submodule in moduletype.submodules:
            _check_submodule_identifiers(submodule, errors)
    _check_variable_names(bp.localvariables, errors)
    _check_modulecode_identifiers(bp.modulecode, errors)
    for submodule in bp.submodules:
        _check_submodule_identifiers(submodule, errors)


def _check_variable_names(variables: list[Variable], errors: list[Diagnostic]) -> None:
    for variable in variables:
        check_identifier(variable.name, "Variable", variable.declaration_span, errors)


def _check_submodule_identifiers(submodule: Submodule, errors: list[Diagnostic]) -> None:
    check_identifier(submodule.header.name, "Submodule", submodule.header.declaration_span, errors)
    if isinstance(submodule, ModuleTypeInstance):
        check_identifier(submodule.moduletype_name, "Module type reference", submodule.header.declaration_span, errors)
        return
    if isinstance(submodule, SingleModule):
        _check_variable_names(submodule.moduleparameters, errors)
        _check_variable_names(submodule.localvariables, errors)
        _check_modulecode_identifiers(submodule.modulecode, errors)
    for nested in submodule.submodules:
        _check_submodule_identifiers(nested, errors)


def _check_modulecode_identifiers(modulecode: ModuleCode | None, errors: list[Diagnostic]) -> None:
    if modulecode is None:
        return
    for equation in modulecode.equations or ():
        check_identifier(equation.name, "Equation", None, errors)
    for sequence in modulecode.sequences or ():
        check_identifier(sequence.name, "Sequence", None, errors)
        _check_sequence_identifiers(sequence.code, errors)


def _check_sequence_identifiers(items: list[SFCBodyItem], errors: list[Diagnostic]) -> None:
    for item in items:
        name: str | None = None
        span: SourceSpan | None = None
        if isinstance(item, SFCStep | SFCTransition | SFCTransitionSub | SFCSubsequence):
            name = item.name
            span = item.span
        if name:
            check_identifier(name, "Sequence element", span, errors)
        if isinstance(item, SFCStep | SFCTransition) and item.fork is not None:
            for target in item.fork.targets:
                check_identifier(target, "Fork target", span, errors)
        if isinstance(item, SFCAlternative | SFCParallel):
            for branch in item.branches:
                _check_sequence_identifiers(branch, errors)
        elif isinstance(item, SFCSubsequence | SFCTransitionSub):
            _check_sequence_identifiers(item.body, errors)


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
