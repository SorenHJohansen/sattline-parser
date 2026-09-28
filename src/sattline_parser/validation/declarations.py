"""Declaration-level validation rules for a parsed BasePicture.

Rules here are intra-file and operate on the transformed AST: definition-name
uniqueness, variable-name uniqueness per declaration scope, sibling submodule
uniqueness, record-field uniqueness, initializer/type consistency, built-in
datatype name typos, unknown datatype references, and datatypes shadowing a
built-in name.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

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
from sattline_parser.validation.literals import is_valid_duration, is_valid_time

Submodule = SingleModule | FrameModule | ModuleTypeInstance

# Datatype names the SattLine language accepts that are not modelled as
# Simple_DataType nor declared via TYPEDEFINITIONS. GroupData is the reserved
# scan-group connection type used by module definitions with a GroupConn tail.
_VALID_UNRESOLVED_DATATYPES = frozenset({"groupdata"})


def check_definition_uniqueness(bp: BasePicture, errors: list[Diagnostic]) -> None:
    """Flag duplicate datatype (DATATYPE) and moduletype (MODULEDEFINITION) names."""
    _record_first_duplicate(
        bp.datatype_defs,
        key=lambda d: d.name,
        code=DiagnosticCode.DUPLICATE_DATATYPE_NAME,
        what="datatype",
        errors=errors,
    )
    _record_first_duplicate(
        bp.moduletype_defs,
        key=lambda d: d.name,
        code=DiagnosticCode.DUPLICATE_MODULETYPE_NAME,
        what="moduletype",
        errors=errors,
    )


def check_builtin_datatype_shadows(bp: BasePicture, errors: list[Diagnostic]) -> None:
    """Flag DATATYPE declarations that reuse a built-in datatype name."""
    builtin_names = {datatype.value.casefold() for datatype in Simple_DataType}
    for datatype in bp.datatype_defs:
        if datatype.name.casefold() in builtin_names:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.BUILTIN_DATATYPE_SHADOWED,
                    message=f"Datatype {datatype.name!r} shadows a built-in datatype name",
                    span=datatype.declaration_span,
                )
            )


def check_scope_declarations(
    moduleparameters: list[Variable], localvariables: list[Variable], errors: list[Diagnostic]
) -> None:
    """Flag duplicate variable names across a module definition's declaration scope."""
    seen: dict[str, Variable] = {}
    for variable in (*moduleparameters, *localvariables):
        key = variable.name.casefold()
        if key in seen:
            original = seen[key]
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.DUPLICATE_VARIABLE_NAME,
                    message=(
                        f"Variable {variable.name!r} is already declared as {original.name!r} "
                        "in the same declaration scope"
                    ),
                    span=variable.declaration_span,
                )
            )
        else:
            seen[key] = variable


def check_sibling_submodules(submodules: list[Submodule], errors: list[Diagnostic]) -> None:
    """Flag duplicate sibling submodule instance/definition names."""
    seen: dict[str, ModuleHeader] = {}
    for child in submodules:
        key = child.header.name.casefold()
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
    """Run per-variable initializer and datatype-reference checks (all scopes and fields)."""
    for variable in variables:
        _check_init_value(variable, errors)
        _check_datatype_reference(variable, records, errors)


def check_record_fields(records: dict[str, DataType], errors: list[Diagnostic]) -> None:
    """Flag duplicate record field names and validate each field's declaration."""
    for record in records.values():
        _check_field_name_uniqueness(record, errors)
        check_variable_declarations(record.var_list, records, errors)


def _check_field_name_uniqueness(record: DataType, errors: list[Diagnostic]) -> None:
    seen: dict[str, Variable] = {}
    for field in record.var_list:
        key = field.name.casefold()
        if key in seen:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.DUPLICATE_RECORD_FIELD_NAME,
                    message=(f"Field {field.name!r} is already declared in record {record.name!r}"),
                    span=field.declaration_span,
                )
            )
        else:
            seen[key] = field


def _check_init_value(variable: Variable, errors: list[Diagnostic]) -> None:
    init = variable.init_value
    if init is None:
        return
    datatype = variable.datatype_text.casefold()
    if datatype == Simple_DataType.DURATION.value:
        _check_duration_init(variable, errors)
        return
    if datatype == Simple_DataType.TIME.value:
        _check_time_init(variable, errors)
        return
    if not isinstance(variable.datatype, Simple_DataType):
        return
    datatype = variable.datatype
    if _scalar_init_matches(datatype, init):
        return
    errors.append(
        Diagnostic(
            code=DiagnosticCode.INIT_VALUE_TYPE_MISMATCH,
            message=(
                f"Initializer for {variable.name} ({datatype.value}) has type "
                f"{_init_type_name(init)}; expected a {_expected_for(datatype)} initializer"
            ),
            span=variable.declaration_span,
        )
    )


def _check_duration_init(variable: Variable, errors: list[Diagnostic]) -> None:
    init = variable.init_value
    if variable.init_is_duration:
        if isinstance(init, str) and not is_valid_duration(init):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.MALFORMED_DURATION_LITERAL,
                    message=f"Duration_Value payload {init!r} does not match the expected duration format",
                    span=variable.declaration_span,
                )
            )
        return
    errors.append(
        Diagnostic(
            code=DiagnosticCode.BARE_DURATION_INIT,
            message=(
                f"Duration initializer for {variable.name} is missing the Duration_Value keyword "
                f"(got {_init_type_name(init)})"
            ),
            span=variable.declaration_span,
        )
    )


def _check_time_init(variable: Variable, errors: list[Diagnostic]) -> None:
    init = variable.init_value
    if isinstance(init, dict):
        time_string = init.get("Time_Value")
        if time_string is None:
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.BARE_TIME_INIT,
                    message=f"Time initializer for {variable.name} has no literal after Time_Value",
                    span=variable.declaration_span,
                )
            )
        elif not is_valid_time(time_string):
            errors.append(
                Diagnostic(
                    code=DiagnosticCode.MALFORMED_TIME_LITERAL,
                    message=(
                        f"Time_Value payload {time_string!r} does not match the expected YYYY-MM-DD-hh:mm:ss.ttt format"
                    ),
                    span=variable.declaration_span,
                )
            )
        return
    errors.append(
        Diagnostic(
            code=DiagnosticCode.BARE_TIME_INIT,
            message=(
                f"Time initializer for {variable.name} is missing the Time_Value keyword (got {_init_type_name(init)})"
            ),
            span=variable.declaration_span,
        )
    )


_STRING_LIKE_DATATYPES: frozenset[Simple_DataType] = frozenset(
    {
        Simple_DataType.STRING,
        Simple_DataType.IDENTSTRING,
        Simple_DataType.TAGSTRING,
        Simple_DataType.LINESTRING,
        Simple_DataType.MAXSTRING,
    }
)


def _scalar_init_matches(datatype: Simple_DataType, init: object) -> bool:
    if isinstance(init, bool):
        return datatype is Simple_DataType.BOOLEAN
    if isinstance(init, int):
        return datatype in {Simple_DataType.INTEGER, Simple_DataType.REAL}
    if isinstance(init, float):
        return datatype is Simple_DataType.REAL
    if isinstance(init, str):
        return datatype in _STRING_LIKE_DATATYPES
    return True


def _expected_for(datatype: Simple_DataType) -> str:
    return {
        Simple_DataType.BOOLEAN: "boolean",
        Simple_DataType.INTEGER: "integer",
        Simple_DataType.REAL: "real",
        Simple_DataType.STRING: "string",
        Simple_DataType.IDENTSTRING: "identstring",
        Simple_DataType.TAGSTRING: "tagstring",
        Simple_DataType.LINESTRING: "linestring",
        Simple_DataType.MAXSTRING: "maxstring",
    }.get(datatype, datatype.value)


def _init_type_name(init: object) -> str:
    if isinstance(init, dict):
        return "Time_Value literal" if "Time_Value" in init else "dictionary value"
    return type(init).__name__


def _check_datatype_reference(variable: Variable, records: dict[str, DataType], errors: list[Diagnostic]) -> None:
    if isinstance(variable.datatype, Simple_DataType):
        return
    name = variable.datatype_text
    folded = name.casefold()
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


def _record_first_duplicate(
    items: Sequence[ModuleTypeDef | DataType],
    key: Callable[[ModuleTypeDef | DataType], str],
    code: DiagnosticCode,
    what: str,
    errors: list[Diagnostic],
) -> None:
    seen: dict[str, str] = {}
    for item in items:
        name = key(item)
        folded = name.casefold()
        if folded in seen:
            errors.append(
                Diagnostic(
                    code=code,
                    message=f"{what.capitalize()} {name!r} is already defined (first definition: {seen[folded]!r})",
                    span=_declaration_span(item),
                )
            )
        else:
            seen[folded] = name


def _declaration_span(item: ModuleTypeDef | DataType) -> SourceSpan | None:
    return item.declaration_span
