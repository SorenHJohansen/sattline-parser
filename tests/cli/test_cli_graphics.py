# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""``sattline graphics``: companion bindings and scan messages."""

from __future__ import annotations

import json

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import VALID_SOURCE, write_source

_COMPANION = '" Syntax version 2.23 "\r\n Var 0 12 OprPathIndex  Lit 0 2 -1     2\r\n Var 0 8 OtherVar\r\n'


def test_graphics_lists_bindings(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", _COMPANION)

    assert main(["graphics", str(companion)]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "bindings: 3" in out
    assert "OprPathIndex" in out
    assert "OtherVar" in out


def test_graphics_json_payload(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", _COMPANION)

    assert main(["graphics", str(companion), "--json"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.graphics"
    assert [row["kind"] for row in payload["bindings"]] == ["var", "lit", "var"]
    assert payload["messages"] == []


def test_graphics_reports_a_scan_warning_as_a_finding(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", " Expr  True  3 (((\r\n")

    assert main(["graphics", str(companion)]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "bindings: 1" in out


def test_non_companion_and_missing_files_are_refused(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.s", VALID_SOURCE)

    assert main(["graphics", str(source)]) == ExitCode.USAGE
    assert "not a graphics companion" in capsys.readouterr().err

    assert main(["graphics", str(tmp_path / "Absent.y")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err
