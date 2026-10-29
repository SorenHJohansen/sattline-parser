# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""``sattline graphics``: companion records, paths and marker correlation."""

from __future__ import annotations

import json

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import VALID_SOURCE, write_source

_COMPANION = (
    " 5\r\n"
    " None  True   0.00000E+000 0.00000E+000\r\n"
    "  1.40000E+000 1.00000E-001\r\n"
    " 0\r\n"
    " 2\r\n"
    " None 0  None -1     1\r\n"
    "1 0 ++First\r\n"
    " 0 default.bmp\r\n"
    " None  True  \r\n"
    "t\r\n"
    "           0\r\n"
)

_GRAPHICS_SOURCE = VALID_SOURCE.replace(
    "ModuleCode\n",
    "GraphObjects :\n   CompositeObject\nModuleCode\n",
)


def test_graphics_summarises_records_and_paths(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", _COMPANION)

    assert main(["graphics", str(companion)]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "records: 1" in out
    assert "picture displays: 1" in out
    assert "++First" in out
    assert "default.bmp (default)" in out


def test_graphics_json_and_asset_paths(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", _COMPANION)

    assert main(["graphics", str(companion), "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.graphics"
    assert payload["records"] == [{"index": 1, "family": "5", "start_line": 1, "end_line": 11}]
    assert payload["paths"][0]["text"] == "++First"
    assert payload["paths"][1]["is_default"] is True

    assert main(["graphics", str(companion), "--asset-paths"]) == ExitCode.OK
    assert capsys.readouterr().out.splitlines() == ["++First", "default.bmp"]


def test_correlation_pairs_markers_with_records(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", _COMPANION)
    source = write_source(tmp_path, "M.s", _GRAPHICS_SOURCE)

    assert main(["graphics", str(companion), "--correlate", "--source", str(source)]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "marker #1 at line" in out
    assert "-> record #1 (family 5)" in out


def test_correlation_needs_a_source(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", _COMPANION)

    assert main(["graphics", str(companion), "--correlate"]) == ExitCode.USAGE
    assert "--correlate needs --source" in capsys.readouterr().err


def test_correlation_reports_an_unparseable_source(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", _COMPANION)
    source = write_source(tmp_path, "M.s", '"only one header line"\n')

    assert main(["graphics", str(companion), "--correlate", "--source", str(source)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert "expected a string" in out or "unexpected" in out


def test_non_companion_and_missing_files_are_refused(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.s", VALID_SOURCE)
    assert main(["graphics", str(source)]) == ExitCode.USAGE
    assert "not a graphics companion" in capsys.readouterr().err

    assert main(["graphics", str(tmp_path / "Absent.y")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err

    companion = write_source(tmp_path, "M.y", _COMPANION)
    assert main(["graphics", str(companion), "--correlate", "--source", str(tmp_path / "Absent.s")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err


def test_asset_paths_json_payload(tmp_path, capsys) -> None:
    companion = write_source(tmp_path, "M.y", _COMPANION)

    assert main(["graphics", str(companion), "--asset-paths", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.graphics"
    assert [row["text"] for row in payload["paths"]] == ["++First", "default.bmp"]


def test_companion_messages_become_findings(tmp_path, capsys) -> None:
    # An unterminated family-5 record: the reader stops with a message.
    broken = write_source(tmp_path, "M.y", " 5\r\n None  True  0 0\r\n")

    assert main(["graphics", str(broken)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert "GRAPHICS_RECORD" not in out
    assert "Unterminated graphics record" in out
