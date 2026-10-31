# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportArgumentType=false
"""``sattline project`` validation reporting and ``--fail-on``."""

from __future__ import annotations

import json

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import CONSECUTIVE_STEPS_SOURCE, write_source


def test_project_reports_validation_findings_and_fails(tmp_path, capsys) -> None:
    write_source(tmp_path, "Sample.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["project", str(tmp_path), "--json"]) == ExitCode.FINDINGS

    payload = json.loads(capsys.readouterr().out)
    assert payload["validation"]
    assert payload["validation"][0]["code"] == "SL-V016"
    assert payload["validation"][0]["severity"] == "error"
    assert payload["validation"][0]["tentative"] is False
    assert payload["programs"][0]["library"] == tmp_path.name


def test_project_fail_on_none_keeps_a_success_exit(tmp_path, capsys) -> None:
    write_source(tmp_path, "Sample.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["project", str(tmp_path), "--json", "--fail-on", "none"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["validation"]


def test_project_no_validate_skips_validation(tmp_path, capsys) -> None:
    write_source(tmp_path, "Sample.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["project", str(tmp_path), "--json", "--no-validate"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["validation"] == []


def test_project_text_output_lists_validation_findings(tmp_path, capsys) -> None:
    write_source(tmp_path, "Sample.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["project", str(tmp_path)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert "validation:" in out
    assert "SL-V016" in out


def test_project_fail_on_warning_fails_on_any_finding(tmp_path, capsys) -> None:
    write_source(tmp_path, "Sample.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["project", str(tmp_path), "--json", "--fail-on", "warning"]) == ExitCode.FINDINGS

    payload = json.loads(capsys.readouterr().out)
    assert payload["validation"]
