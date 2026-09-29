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


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single validation finding, tied to a source span when available."""

    code: DiagnosticCode
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    span: SourceSpan | None = None
