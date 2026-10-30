# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""``sattline check``: findings, output formats, filters and exit codes."""

from __future__ import annotations

import io
import json
import sys

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import (
    CONSECUTIVE_STEPS_SOURCE,
    DECODE_ERROR_SOURCE,
    PARSE_ERROR_SOURCE,
    VALID_SOURCE,
    write_source,
)


def test_clean_source_prints_nothing_and_succeeds(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Clean.s", VALID_SOURCE)

    assert main(["check", str(source)]) == ExitCode.OK

    assert capsys.readouterr().out == ""


def test_findings_render_as_a_located_sentence_with_the_source_line(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["check", str(source)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert f"{source}:12:4: Consecutive SFC steps without an intervening SEQTRANSITION" in out
    assert "SEQSTEP Second" in out
    assert "^" in out
    # Rule ids are machine-only: a finding explains itself without them.
    assert "CONSECUTIVE_SEQUENCE_STEPS" not in out


def test_json_document_carries_the_structured_finding(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["check", str(source), "--json"]) == ExitCode.FINDINGS

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.check"
    assert payload["ok"] is False
    assert payload["counts"] == {"error": 1, "warning": 0}
    [finding] = payload["findings"]
    assert finding == {
        "severity": "error",
        "message": "Consecutive SFC steps without an intervening SEQTRANSITION",
        "rule": "CONSECUTIVE_SEQUENCE_STEPS",
        "file": str(source),
        "line": 12,
        "column": 4,
        "start": finding["start"],
        "end": finding["end"],
        "hint": None,
        "source_line": "   SEQSTEP Second",
    }
    assert isinstance(finding["start"], int) and isinstance(finding["end"], int)


def test_jsonl_streams_findings_then_a_summary(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["check", str(source), "--jsonl"]) == ExitCode.FINDINGS

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["rule"] == "CONSECUTIVE_SEQUENCE_STEPS"
    assert json.loads(lines[1]) == {
        "schema": "sattline.v1.check",
        "summary": True,
        "counts": {"error": 1, "warning": 0},
    }


def test_severity_and_rule_filters(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["check", str(source), "--severity", "warning"]) == ExitCode.OK
    assert capsys.readouterr().out == ""

    assert main(["check", str(source), "--rule", "CONSECUTIVE_SEQUENCE_STEPS"]) == ExitCode.FINDINGS
    assert "Consecutive SFC steps" in capsys.readouterr().out

    assert main(["check", str(source), "--rule", "SOMETHING_ELSE"]) == ExitCode.OK
    assert capsys.readouterr().out == ""


def test_max_findings_limits_output_but_not_the_exit_code(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["check", str(source), "--max-findings", "0"]) == ExitCode.FINDINGS
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "1 more finding(s) not shown" in captured.err

    assert main(["check", str(source), "--max-findings", "-1"]) == ExitCode.FINDINGS
    assert "Consecutive SFC steps" in capsys.readouterr().out


def test_fail_on_policy(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["check", str(source), "--fail-on", "never"]) == ExitCode.OK
    assert "Consecutive SFC steps" in capsys.readouterr().out

    assert main(["check", str(source), "--fail-on", "any"]) == ExitCode.FINDINGS
    capsys.readouterr()


def test_parse_error_is_one_finding_with_a_hint(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    assert main(["check", str(source)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert f"{source}:7:21: unexpected end of file; expected ';'" in out
    assert "help: the unit ends before a required ';'" in out
    assert "ENDDEF (*BasePicture*)" in out
    assert "Token(" not in out


def test_parse_error_json_carries_rule_and_sentence(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    assert main(["check", str(source), "--json"]) == ExitCode.FINDINGS

    [finding] = json.loads(capsys.readouterr().out)["findings"]
    assert finding["rule"] == "PARSE_ERROR"
    assert finding["message"].startswith("unexpected end of file; expected ';'")
    assert finding["hint"].startswith("the unit ends before a required ';'")
    assert finding["source_line"] == "ENDDEF (*BasePicture*)"
    assert (finding["line"], finding["column"]) == (7, 21)


def test_decode_error_is_a_located_finding_without_a_position(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Coded.s", DECODE_ERROR_SOURCE)

    assert main(["check", str(source), "--json"]) == ExitCode.FINDINGS

    [finding] = json.loads(capsys.readouterr().out)["findings"]
    assert finding["rule"] == "DECODE_ERROR"
    assert "Unknown compressed marker" in finding["message"]
    assert finding["line"] is None


def test_several_paths_report_together(tmp_path, capsys) -> None:
    clean = write_source(tmp_path, "Clean.s", VALID_SOURCE)
    broken = write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    assert main(["check", str(clean), str(broken)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert str(broken) in out
    assert str(clean) not in out


def test_stdin_requires_a_name(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", type("_Stdin", (), {"buffer": io.BytesIO(VALID_SOURCE.encode("cp1252"))})())

    assert main(["check", "-"]) == ExitCode.USAGE
    assert "requires --stdin-name" in capsys.readouterr().err

    assert main(["check", "-", "--stdin-name", "Piped.s"]) == ExitCode.OK
    assert capsys.readouterr().out == ""


def test_missing_and_undecodable_inputs_are_usage_errors(tmp_path, capsys) -> None:
    assert main(["check", str(tmp_path / "Absent.s")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err

    bad = tmp_path / "Bad.s"
    bad.write_bytes(b"\x81")
    assert main(["check", str(bad)]) == ExitCode.USAGE
    assert "not valid Windows-1252" in capsys.readouterr().err


def test_absolute_paths_are_configurable(tmp_path, capsys, monkeypatch) -> None:
    write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)
    monkeypatch.chdir(tmp_path)

    assert main(["check", "Steps.s", "--paths", "absolute"]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert str((tmp_path / "Steps.s").resolve()) in out


def test_companion_files_are_refused_with_a_pointed_message(tmp_path, capsys) -> None:
    companion = tmp_path / "M.y"
    companion.write_text("", encoding="utf-8")

    assert main(["check", str(companion)]) == ExitCode.USAGE

    err = capsys.readouterr().err
    assert "is a graphics companion (.y)" in err
    assert "read SattLine source units" in err
