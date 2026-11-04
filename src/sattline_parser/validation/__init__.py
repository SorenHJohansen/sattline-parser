"""Strict single-source validation for the sattline-parser package."""

from __future__ import annotations

from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.rules import (
    RETIRED_CODES,
    RULES,
    RULES_BY_CODE,
    RULES_BY_ID,
    RULES_BY_NAME,
    Rule,
    RuleScope,
    RuleStatus,
    UnknownRuleError,
    find_rule,
    render_markdown_table,
    require_rule,
)
from sattline_parser.validation.validator import validate_basepicture

__all__ = [
    "RETIRED_CODES",
    "RULES",
    "RULES_BY_CODE",
    "RULES_BY_ID",
    "RULES_BY_NAME",
    "Diagnostic",
    "DiagnosticCode",
    "Rule",
    "RuleScope",
    "RuleStatus",
    "UnknownRuleError",
    "find_rule",
    "render_markdown_table",
    "require_rule",
    "validate_basepicture",
]
