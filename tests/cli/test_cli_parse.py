# pyright: reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
"""``sattline parse``: summary, tree serialisation and parse failures."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from sattline_parser.api import parse_source_file
from sattline_parser.ast import walk
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
    assert payload["ok"] is True
    assert payload["findings"] == []

    assert main(["parse", str(source), "--jsonl"]) == ExitCode.OK
    one_line = capsys.readouterr().out.strip()
    assert "\n" not in one_line
    assert json.loads(one_line)["schema"] == "sattline.v1.parse"

    assert main(["parse", str(source), "--json", "--compact"]) == ExitCode.OK
    one_line = capsys.readouterr().out.strip()
    assert "\n" not in one_line
    assert json.loads(one_line)["counts"]["sequences"] == 1


def _walk_count(picture, field: str) -> int:
    return sum(1 for event in walk(picture) if event.field == field)


def test_summary_counts_the_whole_module_tree(tmp_path, capsys) -> None:
    """Nested submodules and module-type bodies contribute to every count."""
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "corpus" / "valid" / "UnCompressedFullGrammar.s"
    picture = parse_source_file(fixture)

    assert main(["parse", str(fixture), "--json"]) == ExitCode.OK
    counts = json.loads(capsys.readouterr().out)["counts"]

    assert counts == {
        "module_types": _walk_count(picture, "moduletype_defs"),
        "submodules": _walk_count(picture, "submodules"),
        "local_variables": _walk_count(picture, "localvariables"),
        "sequences": _walk_count(picture, "sequences"),
        "equationblocks": _walk_count(picture, "equationblocks"),
        "graph_objects": _walk_count(picture, "graph_objects"),
        "interact_objects": _walk_count(picture, "interact_objects"),
    }
    assert counts["graph_objects"] == 29
    assert counts["sequences"] == 2


def test_tree_serialises_the_ast_with_a_depth_limit(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Sample.s", VALID_SOURCE)

    assert main(["parse", str(source), "--tree", "--depth", "2", "--compact"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.parse"
    assert payload["tree"]["name"] == "BasePicture"
    assert payload["ok"] is True
    assert payload["findings"] == []
    # The layout blocks are plain optional fields, so the singular keys are the
    # only representation and the removed lists never appear.
    assert "moduledefs" not in payload["tree"]
    assert "modulecodes" not in payload["tree"]
    assert isinstance(payload["tree"]["moduledef"], dict)
    assert isinstance(payload["tree"]["modulecode"], dict)
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


def test_parse_failure_jsonl_streams_the_finding_then_a_summary(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    assert main(["parse", str(source), "--jsonl"]) == ExitCode.FINDINGS

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    [finding, summary] = (json.loads(line) for line in lines)
    assert finding["rule"] == "PARSE_ERROR"
    assert (finding["line"], finding["column"]) == (7, 21)
    assert finding["source_line"] == "ENDDEF (*BasePicture*)"
    assert summary == {
        "schema": "sattline.v1.parse",
        "summary": True,
        "counts": {"error": 1},
    }


def test_parse_reads_stdin_with_a_name(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", type("_Stdin", (), {"buffer": io.BytesIO(VALID_SOURCE.encode("cp1252"))})())

    assert main(["parse", "-", "--stdin-name", "Piped.s"]) == ExitCode.OK
    assert "file: Piped.s" in capsys.readouterr().out


def test_paths_absolute_applies_to_the_document_file(tmp_path, capsys, monkeypatch) -> None:
    write_source(tmp_path, "Sample.s", VALID_SOURCE)
    monkeypatch.chdir(tmp_path)

    assert main(["parse", "Sample.s", "--json", "--paths", "absolute"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["file"] == str((tmp_path / "Sample.s").resolve())

    assert main(["parse", "Sample.s", "--tree", "--paths", "absolute"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["file"] == str((tmp_path / "Sample.s").resolve())


def test_parse_reports_a_missing_file(tmp_path, capsys) -> None:
    assert main(["parse", str(tmp_path / "Absent.s")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err
