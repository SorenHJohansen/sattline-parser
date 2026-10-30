"""Diagnostic model and error codes for the strict single-source validation pass."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sattline_parser.models.ast_model import SourceSpan


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class DiagnosticCode(StrEnum):
    DUPLICATE_DATATYPE_NAME = "SL-V001"
    DUPLICATE_MODULETYPE_NAME = "SL-V002"
    DUPLICATE_VARIABLE_NAME = "SL-V003"
    DUPLICATE_SIBLING_SUBMODULE = "SL-V004"
    OLD_NEW_ON_NON_STATE_VARIABLE = "SL-V005"
    OLD_NEW_ON_NON_STATE_FIELD = "SL-V006"
    WRITE_TO_CONST_VARIABLE = "SL-V007"
    INIT_VALUE_TYPE_MISMATCH = "SL-V008"
    BARE_DURATION_INIT = "SL-V009"
    BARE_TIME_INIT = "SL-V010"
    MALFORMED_DURATION_LITERAL = "SL-V011"
    MALFORMED_TIME_LITERAL = "SL-V012"
    BUILTIN_WRONG_ARITY = "SL-V013"
    BUILTIN_OUT_ARG_NOT_VARIABLE = "SL-V014"
    STRING_LITERAL_CALL_ARGUMENT = "SL-V015"
    CONSECUTIVE_SEQUENCE_STEPS = "SL-V016"
    SEQUENCE_FORK_UNKNOWN_TARGET = "SL-V017"
    BUILTIN_DATATYPE_TYPO = "SL-V018"
    UNDEFINED_VARIABLE = "SL-V019"
    UNKNOWN_DATATYPE_NAME = "SL-V020"
    DUPLICATE_SFC_ELEMENT_NAME = "SL-V021"
    SFC_INIT_STEP_PLACEMENT = "SL-V022"
    SFC_ALTERNATIVE_BRANCH_START = "SL-V023"
    SFC_PARALLEL_BRANCH_START = "SL-V024"
    DUPLICATE_RECORD_FIELD_NAME = "SL-V025"
    BUILTIN_DATATYPE_SHADOWED = "SL-V026"
    PARAM_TRANSFER_TYPE_MISMATCH = "SL-V027"
    OPERAND_NOT_NUMERIC = "SL-V028"
    ASSIGNMENT_TYPE_MISMATCH = "SL-V029"
    CONDITION_NOT_BOOLEAN = "SL-V030"
    ATTRIBUTE_COMBINATION_INVALID = "SL-V031"
    COORDINATE_NOT_REAL = "SL-V032"
    SEQUENCE_ENDS_WITH_STEP = "SL-V033"
    RESERVED_NAME_DECLARED = "SL-V034"
    OLD_STATE_NOT_WRITABLE = "SL-V035"
    SEQUENCE_POSITION_INVALID = "SL-V036"
    SEQUENCE_FORK_TARGET_KIND = "SL-V037"


#: Codes that are not enforced. They were implemented on the strength of the
#: editor refusing to *create* such a declaration through its UI, then disproved
#: by loading the same source directly instead: the UI guard is not a parser
#: rule, and rejecting files that load and parse was wrong.
#:
#: The enum members are kept so existing imports and stored diagnostics stay
#: valid, but nothing emits them. Each entry is a pending question for the
#: editors, not a gap in our parser.
RETIRED_CODES: dict[DiagnosticCode, str] = {
    DiagnosticCode.DUPLICATE_DATATYPE_NAME: "BadDupDatatypeName.x",
    DiagnosticCode.DUPLICATE_MODULETYPE_NAME: "BadDupModTypeName.x",
    DiagnosticCode.DUPLICATE_VARIABLE_NAME: "BadDupVariaNames.x",
    DiagnosticCode.DUPLICATE_RECORD_FIELD_NAME: "BadDupRecFldName.x",
    DiagnosticCode.BUILTIN_DATATYPE_SHADOWED: "BadDatatypeShadows.x",
    DiagnosticCode.INIT_VALUE_TYPE_MISMATCH: "BadInitValType.x",
    DiagnosticCode.BARE_DURATION_INIT: "BadBareDurStr.x",
    DiagnosticCode.BARE_TIME_INIT: "BadBareTimeStr.x",
    DiagnosticCode.MALFORMED_DURATION_LITERAL: "BadDurLit.x",
    DiagnosticCode.MALFORMED_TIME_LITERAL: "BadTimeLit.x",
    DiagnosticCode.SFC_INIT_STEP_PLACEMENT: "BadSfcInitStepNot.x, BadSfcInitStep.x",
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single validation finding, tied to a source span when available."""

    code: DiagnosticCode
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    span: SourceSpan | None = None
