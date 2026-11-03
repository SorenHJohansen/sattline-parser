# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""Tests for ``sattline rules`` and registry-backed rule selection."""

from __future__ import annotations

import json

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode
from sattline_parser.validation.rules import RULES

from ._cli_support import VALID_SOURCE, write_source


def test_rules_lists_active_rules_by_default(capsys) -> None:
    assert main(["rules"]) == ExitCode.OK
    out = capsys.readouterr().out

    assert "SL-V016" in out
    assert "CONSECUTIVE_SEQUENCE_STEPS" in out
    assert "SL-V001" not in out


def test_rules_include_retired_flag(capsys) -> None:
    assert main(["rules", "--include-retired"]) == ExitCode.OK
    out = capsys.readouterr().out

    assert "SL-V001" in out
    assert "retired" in out


def test_rules_single_lookup_accepts_id_and_name(capsys) -> None:
    assert main(["rules", "SL-V019"]) == ExitCode.OK
    out = capsys.readouterr().out
    assert "SL-V019" in out
    assert "UNDEFINED_VARIABLE" in out
    assert "status:" in out

    assert main(["rules", "undefined_variable"]) == ExitCode.OK
    assert "SL-V019" in capsys.readouterr().out


def test_rules_single_lookup_sees_retired_rules(capsys) -> None:
    assert main(["rules", "DUPLICATE_DATATYPE_NAME"]) == ExitCode.OK
    out = capsys.readouterr().out

    assert "SL-V001" in out
    assert "retired" in out
    assert "details:" in out


def test_rules_json_matches_the_registry(capsys) -> None:
    assert main(["rules", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "sattline.v1.rules"
    assert payload["count"] == len([rule for rule in RULES if not rule.retired])
    assert any(row["id"] == "SL-V019" for row in payload["rules"])
    assert all("status" in row and "severity" in row for row in payload["rules"])


def test_rules_jsonl_ends_with_a_summary(capsys) -> None:
    assert main(["rules", "SL-V016", "--jsonl"]) == ExitCode.OK
    lines = capsys.readouterr().out.splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "CONSECUTIVE_SEQUENCE_STEPS"
    assert json.loads(lines[1]) == {
        "schema": "sattline.v1.rules",
        "summary": True,
        "count": 1,
    }


def test_unknown_rule_is_a_usage_error(capsys) -> None:
    assert main(["rules", "NOT_A_RULE"]) == ExitCode.USAGE
    assert "unknown rule" in capsys.readouterr().err


def test_check_rejects_a_retired_rule(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Valid.s", VALID_SOURCE)

    assert main(["check", str(source), "--rule", "SL-V001"]) == ExitCode.USAGE
    assert "retired" in capsys.readouterr().err
