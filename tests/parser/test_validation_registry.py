# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""Tests for the validation rule registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from sattline_parser.validation.diagnostics import DiagnosticCode
from sattline_parser.validation.rules import (
    RETIRED_CODES,
    RULES,
    RULES_BY_CODE,
    RULES_BY_ID,
    RULES_BY_NAME,
    RuleStatus,
    UnknownRuleError,
    find_rule,
    render_markdown_table,
    require_rule,
)

_DOCS = Path(__file__).resolve().parents[2] / "docs" / "validation.md"
_START = "<!-- RULE-TABLE:START -->"
_END = "<!-- RULE-TABLE:END -->"

_UNIMPLEMENTED = {
    DiagnosticCode.DATATYPE_TOO_FEW_FIELDS,
    DiagnosticCode.DIVISION_BY_ZERO,
    DiagnosticCode.SEQUENCE_TRANSITION_AFTER_TRANSITION,
    DiagnosticCode.PARALLEL_BRANCH_INCOMPLETE,
    DiagnosticCode.SUBSEQTRANSITION_STARTS_WITH_STEP,
    DiagnosticCode.SEQUENCE_REQUIRES_INIT_STEP,
}


def test_registry_covers_every_diagnostic_code_exactly_once() -> None:
    assert set(RULES_BY_CODE) == set(DiagnosticCode)
    assert len(RULES) == len(DiagnosticCode)


def test_rule_identity_is_derived_from_the_enum() -> None:
    for rule in RULES:
        assert rule.id == rule.code.value
        assert rule.name == rule.code.name
        assert RULES_BY_ID[rule.id.casefold()] is rule
        assert RULES_BY_NAME[rule.name.casefold()] is rule


def test_ids_and_names_are_unique_and_well_formed() -> None:
    ids = [rule.id for rule in RULES]
    names = [rule.name for rule in RULES]

    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))
    assert all(rule.id.startswith("SL-V") and len(rule.id) == 7 for rule in RULES)


def test_every_rule_has_a_summary() -> None:
    for rule in RULES:
        assert rule.summary
        assert rule.summary.endswith(".")


def test_retired_codes_come_from_the_registry() -> None:
    retired = {rule.code for rule in RULES if rule.retired}

    assert set(RETIRED_CODES) == retired
    assert retired
    for code, reason in RETIRED_CODES.items():
        rule = RULES_BY_CODE[code]
        assert rule.status is RuleStatus.RETIRED
        assert not rule.enabled
        assert reason


def test_unimplemented_codes_are_recorded_not_enabled() -> None:
    unimplemented = {rule.code for rule in RULES if not rule.implemented}

    assert unimplemented == _UNIMPLEMENTED
    for rule in RULES:
        if rule.code in _UNIMPLEMENTED:
            assert rule.status is RuleStatus.UNIMPLEMENTED
            assert not rule.enabled


def test_active_rules_are_the_only_enabled_ones() -> None:
    for rule in RULES:
        assert rule.enabled is (rule.status is RuleStatus.ACTIVE)


def test_active_rules_have_an_emit_site() -> None:
    sources = [
        *Path(__file__).resolve().parents[2].glob("src/sattline_parser/validation/*.py"),
        Path(__file__).resolve().parents[2] / "src" / "sattline_parser" / "project" / "loader.py",
    ]
    text = "\n".join(
        source.read_text(encoding="utf-8") for source in sources if source.name not in {"rules.py", "diagnostics.py"}
    )

    missing = [rule.name for rule in RULES if rule.enabled and f"DiagnosticCode.{rule.name}" not in text]

    assert missing == []


def test_retired_and_unimplemented_rules_never_overlap() -> None:
    assert not any(rule.retired and not rule.implemented for rule in RULES)


def test_find_rule_accepts_ids_and_names_case_insensitively() -> None:
    by_id = find_rule("SL-V019")
    by_name = find_rule("undefined_variable")

    assert by_id is not None
    assert by_id is by_name
    assert by_id.name == "UNDEFINED_VARIABLE"


def test_unknown_rule_reports_a_close_name() -> None:
    with pytest.raises(UnknownRuleError) as exc_info:
        require_rule("UNDEFINED_VARIABEL")

    assert "UNDEFINED_VARIABLE" in str(exc_info.value)


def test_documentation_table_matches_the_registry() -> None:
    text = _DOCS.read_text(encoding="utf-8")
    before, separator, rest = text.partition(_START)
    table, separator, _after = rest.partition(_END)

    assert separator
    assert table.strip() == render_markdown_table()
    assert before


def test_markdown_table_can_hide_retired_rules() -> None:
    table = render_markdown_table(include_retired=False)

    assert "SL-V001" not in table
    assert "SL-V004" in table


def test_rule_json_shape() -> None:
    rule = RULES_BY_CODE[DiagnosticCode.UNDEFINED_VARIABLE]
    payload = rule.to_json()

    assert payload == {
        "id": "SL-V019",
        "name": "UNDEFINED_VARIABLE",
        "scope": "code",
        "status": "active",
        "retired": False,
        "summary": rule.summary,
        "details": None,
    }
