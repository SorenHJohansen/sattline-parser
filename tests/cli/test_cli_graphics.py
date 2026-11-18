# pyright: reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
"""``sattline graphics``: companion bindings and scan messages."""

from __future__ import annotations

import io
import json
import sys

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

    # A scan message means the companion was only partly understood, so it is a
    # finding and the command exits 1 even when its severity is ``warning``.
    assert main(["graphics", str(companion)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert "bindings: 1" in out
    assert "Could not parse graphics expression '((('" in out
    # The parser's token dump is never reproduced.
    assert "Expected one of" not in out
    assert "Token(" not in out


def test_graphics_json_counts_keep_the_warning_bucket(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", " Expr  True  3 (((\r\n")

    assert main(["graphics", str(companion), "--json"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"] == {"error": 0, "warning": 1}
    assert payload["ok"] is False
    [message] = payload["messages"]
    assert message["message"] == "Could not parse graphics expression '((('"

    assert main(["graphics", str(companion), "--jsonl"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"] == {"error": 0, "warning": 1}


def test_non_companion_and_missing_files_are_refused(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.s", VALID_SOURCE)

    assert main(["graphics", str(source)]) == ExitCode.USAGE
    assert "not a graphics companion" in capsys.readouterr().err

    assert main(["graphics", str(tmp_path / "Absent.y")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err


def test_stdin_is_accepted_as_a_companion() -> None:
    original = sys.stdin
    sys.stdin = type("_Stdin", (), {"buffer": io.BytesIO(_COMPANION.encode("cp1252"))})()  # type: ignore[assignment]
    try:
        assert main(["graphics", "-", "--stdin-name", "Companion.y"]) == ExitCode.OK
    finally:
        sys.stdin = original


def test_stdin_requires_a_name_like_every_source_command(capsys) -> None:
    assert main(["graphics", "-"]) == ExitCode.USAGE
    assert "requires --stdin-name" in capsys.readouterr().err


def test_a_stdin_name_that_is_source_is_refused(capsys) -> None:
    # The shared naming rule applies: a piped source is refused exactly like a
    # ``.s`` path, before any content is read.
    assert main(["graphics", "-", "--stdin-name", "Companion.s"]) == ExitCode.USAGE
    assert "Companion.s is not a graphics companion (.g/.y)" in capsys.readouterr().err


def test_paths_absolute_applies_to_the_document_file(tmp_path, capsys, monkeypatch) -> None:
    write_source(tmp_path, "M.y", _COMPANION)
    monkeypatch.chdir(tmp_path)

    assert main(["graphics", "M.y", "--json", "--paths", "absolute"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["file"] == str((tmp_path / "M.y").resolve())
