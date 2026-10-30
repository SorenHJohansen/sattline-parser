# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""``sattline parse``: summary, tree serialisation and parse failures."""

from __future__ import annotations

import io
import json
import sys

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import PARSE_ERROR_SOURCE, VALID_SOURCE, write_source


def test_summary_is_text_by_default(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Sample.s", VALID_SOURCE)

    assert main(["parse", str(source)]) == ExitCode.OK

    out = capsys.readouterr().out
    assert f"file: {source}" in out
    assert "program: Sample" in out
    assert "encoding: plain" in out
    assert "  sequences: 1" in out
    assert "  local_variables: 1" in out


def test_summary_json_and_jsonl(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Sample.s", VALID_SOURCE)

    assert main(["parse", str(source), "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.parse"
    assert payload["counts"]["sequences"] == 1

    assert main(["parse", str(source), "--jsonl"]) == ExitCode.OK
    one_line = capsys.readouterr().out.strip()
    assert "\n" not in one_line
    assert json.loads(one_line)["schema"] == "sattline.v1.parse"


def test_tree_serialises_the_ast_with_a_depth_limit(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Sample.s", VALID_SOURCE)

    assert main(["parse", str(source), "--tree", "--depth", "2", "--compact"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.parse"
    assert payload["tree"]["name"] == "BasePicture"
    # Depth-limited values become placeholders instead of disappearing silently.
    assert payload["tree"]["moduletype_defs"] == []
    assert payload["tree"]["localvariables"] == ["<Variable>"]


def test_depth_must_be_a_positive_integer(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Sample.s", VALID_SOURCE)

    assert main(["parse", str(source), "--depth", "zero"]) == ExitCode.USAGE
    assert "expected an integer" in capsys.readouterr().err

    assert main(["parse", str(source), "--depth", "0"]) == ExitCode.USAGE
    assert "must be 1 or greater" in capsys.readouterr().err


def test_parse_failure_is_a_finding_not_a_crash(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    assert main(["parse", str(source)]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "unexpected end of file" in out
    assert f"{source}:7:21:" in out

    assert main(["parse", str(source), "--json"]) == ExitCode.FINDINGS
    [finding] = json.loads(capsys.readouterr().out)["findings"]
    assert finding["rule"] == "PARSE_ERROR"


def test_parse_reads_stdin_with_a_name(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", type("_Stdin", (), {"buffer": io.BytesIO(VALID_SOURCE.encode("cp1252"))})())

    assert main(["parse", "-", "--stdin-name", "Piped.s"]) == ExitCode.OK
    assert "file: Piped.s" in capsys.readouterr().out


def test_parse_reports_a_missing_file(tmp_path, capsys) -> None:
    assert main(["parse", str(tmp_path / "Absent.s")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err
