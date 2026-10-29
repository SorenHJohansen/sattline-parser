# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""``sattline`` on byte-coded sources: the binary ``.x`` framing the editor writes."""

from __future__ import annotations

import io
import json
import sys

import pytest

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import VALID_SOURCE, encode_coded, write_coded, write_source


def test_check_reads_a_coded_source(tmp_path, capsys) -> None:
    source = write_coded(tmp_path, "Coded.x", VALID_SOURCE)

    assert main(["check", str(source)]) == ExitCode.OK

    assert capsys.readouterr().out == ""


def test_parse_reports_the_coded_flavor(tmp_path, capsys) -> None:
    source = write_coded(tmp_path, "Coded.x", VALID_SOURCE)

    assert main(["parse", str(source), "--json"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["encoding"] == "coded"
    assert payload["program"] == "Sample"
    assert payload["counts"]["sequences"] == 1


def test_query_walks_a_coded_source(tmp_path, capsys) -> None:
    source = write_coded(tmp_path, "Coded.x", VALID_SOURCE)

    assert main(["query", str(source), "--what", "symbols", "--limit", "1"]) == ExitCode.OK

    assert "variable Flag" in capsys.readouterr().out


def test_decode_prints_and_reports_coded_input(tmp_path, capsys) -> None:
    source = write_coded(tmp_path, "Coded.x", VALID_SOURCE)

    assert main(["decode", str(source)]) == ExitCode.OK
    assert capsys.readouterr().out == VALID_SOURCE

    assert main(["decode", str(source), "--report"]) == ExitCode.OK
    report = json.loads(capsys.readouterr().out)
    assert report["coded"] is True
    assert report["original_length"] == len(source.read_bytes())
    assert report["decoded_length"] == len(VALID_SOURCE)


def test_corpus_reads_coded_files_without_read_errors(tmp_path, capsys) -> None:
    write_coded(tmp_path, "Coded.x", VALID_SOURCE)
    write_source(tmp_path, "Plain.s", VALID_SOURCE)

    assert main(["corpus", str(tmp_path), "--json"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["files"] == 2
    assert payload["rules"] == {}
    assert all("READ_ERROR" not in row["rules"] for row in payload["results"])


def test_stdin_accepts_a_coded_stream(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", type("_Stdin", (), {"buffer": io.BytesIO(encode_coded(VALID_SOURCE))})())

    assert main(["check", "-", "--stdin-name", "Piped.x"]) == ExitCode.OK
    assert capsys.readouterr().out == ""

    monkeypatch.setattr(sys, "stdin", type("_Stdin", (), {"buffer": io.BytesIO(encode_coded(VALID_SOURCE))})())
    assert main(["parse", "-", "--stdin-name", "Piped.x", "--json"]) == ExitCode.OK
    assert json.loads(capsys.readouterr().out)["encoding"] == "coded"


def test_malformed_coded_stream_is_a_usage_error(tmp_path, capsys) -> None:
    broken = tmp_path / "Broken.x"
    broken.write_bytes(b"\x80 3.1\r\n" + b"\x80" * 3)

    assert main(["check", str(broken)]) == ExitCode.USAGE

    assert "cannot decode" in capsys.readouterr().err


def test_a_coded_source_that_does_not_parse_reports_a_finding(tmp_path, capsys) -> None:
    source = write_coded(tmp_path, "Broken.x", '"only one header line"\n')

    assert main(["check", str(source)]) == ExitCode.FINDINGS

    assert "unexpected end of file" in capsys.readouterr().out


def test_an_undefined_byte_outside_a_comment_is_still_refused(tmp_path, capsys) -> None:
    plain = tmp_path / "HighByte.s"
    plain.write_bytes(b'"Syntax version 2.23"\nA \x81 B\n')

    assert main(["check", str(plain)]) == ExitCode.USAGE

    assert "not valid Windows-1252" in capsys.readouterr().err


def test_an_undefined_byte_inside_a_comment_is_tolerated(tmp_path, capsys) -> None:
    plain = tmp_path / "CommentByte.s"
    plain.write_bytes(
        VALID_SOURCE.encode("cp1252").replace(
            b"ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n",
            b"ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n(* byte \x81 here *)\n",
        )
    )

    assert main(["check", str(plain)]) == ExitCode.OK
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("command", ["parse", "query", "decode"])
def test_commands_share_the_coded_reader(tmp_path, capsys, command: str) -> None:
    source = write_coded(tmp_path, "Coded.x", VALID_SOURCE)

    assert main([command, str(source)]) == ExitCode.OK
