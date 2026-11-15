# pyright: reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportIndexIssue=false, reportGeneralTypeIssues=false
"""``sattline check --sarif`` and ``sattline project --sarif``."""

from __future__ import annotations

import json
from pathlib import Path

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode
from sattline_parser.cli._findings import Finding
from sattline_parser.cli._sarif import sarif_document

from ._cli_support import CONSECUTIVE_STEPS_SOURCE, VALID_SOURCE, write_source

_SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def _run_json(capsys) -> dict[str, object]:
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    return payload


def test_check_sarif_is_a_complete_log(tmp_path: Path, capsys) -> None:
    source = write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["check", str(source), "--sarif"]) == ExitCode.FINDINGS
    log = _run_json(capsys)

    assert log["version"] == "2.1.0"
    assert log["$schema"] == _SARIF_SCHEMA
    run = log["runs"][0]
    driver = run["tool"]["driver"]
    assert driver["name"] == "sattline"
    assert driver["version"]
    result = run["results"][0]
    assert result["ruleId"] == "SL-V016"
    assert result["level"] == "error"
    assert result["message"]["text"]
    region = result["locations"][0]["physicalLocation"]["region"]
    assert region["startLine"] >= 1
    assert driver["rules"][0]["id"] == "SL-V016"


def test_check_sarif_reports_a_parse_error_under_its_own_id(tmp_path: Path, capsys) -> None:
    source = write_source(tmp_path, "Broken.s", "not a sattline source\n")

    assert main(["check", str(source), "--sarif"]) == ExitCode.FINDINGS
    log = _run_json(capsys)

    result = log["runs"][0]["results"][0]
    assert result["ruleId"] == "PARSE_ERROR"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"].endswith("Broken.s")


def test_sarif_refuses_the_json_output_flags(tmp_path: Path, capsys) -> None:
    source = write_source(tmp_path, "Clean.s", VALID_SOURCE)

    assert main(["check", str(source), "--sarif", "--json"]) == ExitCode.USAGE
    assert "cannot be combined" in capsys.readouterr().err


def test_project_sarif_uses_the_source_path(tmp_path: Path, capsys) -> None:
    write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["project", str(tmp_path), "--sarif", "--workers", "1"]) == ExitCode.FINDINGS
    log = _run_json(capsys)

    results = log["runs"][0]["results"]
    assert results
    assert results[0]["ruleId"] == "SL-V016"
    assert results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"].endswith("Steps.s")


def test_sarif_describes_each_rule_once_and_uses_its_details() -> None:
    findings = [
        Finding(severity="error", message="first", rule="DUPLICATE_VARIABLE_NAME", file="a.s", line=1),
        Finding(severity="error", message="second", rule="DUPLICATE_VARIABLE_NAME", file="a.s", line=2),
    ]

    log = sarif_document(findings, version="1.0")

    descriptors = log["runs"][0]["tool"]["driver"]["rules"]
    assert len(descriptors) == 1
    assert len(log["runs"][0]["results"]) == 2


def test_sarif_result_without_a_location_keeps_its_message() -> None:
    log = sarif_document(
        [Finding(severity="error", message="cannot load", rule="PROJECT_LOAD_ERROR")],
        version="1.0",
    )

    result = log["runs"][0]["results"][0]
    assert "locations" not in result
    assert result["message"]["text"] == "cannot load"


def test_a_finding_with_a_hint_gets_a_markdown_message() -> None:
    log = sarif_document(
        [Finding(severity="error", message="broken", rule="PARSE_ERROR", hint="add a colon")],
        version="1.0",
    )

    message = log["runs"][0]["results"][0]["message"]
    assert message["text"] == "broken. Help: add a colon"
    assert "**help:** add a colon" in message["markdown"]


def test_project_sarif_reports_a_load_failure(tmp_path: Path, capsys) -> None:
    write_source(tmp_path, "Broken.s", "not a sattline source\n")

    assert main(["project", str(tmp_path), "--sarif", "--workers", "1"]) == ExitCode.FINDINGS
    log = _run_json(capsys)

    result = log["runs"][0]["results"][0]
    assert result["ruleId"] == "PROJECT_LOAD_ERROR"
    assert "locations" not in result
