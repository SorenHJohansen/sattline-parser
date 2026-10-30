# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""``sattline decode``, ``diff`` and ``corpus``."""

from __future__ import annotations

import json
from pathlib import Path

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import CONSECUTIVE_STEPS_SOURCE, VALID_SOURCE, write_source

#: A tiny compact source: ``#22`` is SEQUENCE, ``#01``/``#8?`` are punctuation.
_COMPACT = '"Syntax version 2.23, date: 2026-10-28-00:00:00.000 C"\n#22 Tail\n'


def test_decode_prints_plain_text(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.s", VALID_SOURCE)

    assert main(["decode", str(source)]) == ExitCode.OK

    assert capsys.readouterr().out == VALID_SOURCE


def test_decode_reports_and_embeds_json(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.x", _COMPACT)

    assert main(["decode", str(source), "--report"]) == ExitCode.OK
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "sattline.v1.decode"
    assert report["coded"] is True
    assert (
        report["decoded_length"]
        == len("SEQUENCE Tail\n") + len(source.read_bytes().decode("cp1252").splitlines()[0]) + 1
    )

    assert main(["decode", str(source), "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert "SEQUENCE" in payload["decoded"]


def test_decode_refuses_undecodable_input(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Broken.x", '"Syntax version 2.23, date: 2026-10-28-00:00:00.000 C"\n#ZZ\n')

    assert main(["decode", str(source)]) == ExitCode.USAGE
    assert "Unknown compressed marker" in capsys.readouterr().err


def test_decode_report_and_json_are_mutually_exclusive(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.s", VALID_SOURCE)

    assert main(["decode", str(source), "--report", "--json"]) == ExitCode.USAGE
    assert "not allowed with argument" in capsys.readouterr().err


def test_diff_reports_no_differences(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.s", VALID_SOURCE)

    assert main(["diff", str(source), str(source)]) == ExitCode.OK
    assert capsys.readouterr().out.strip() == "no differences"


def test_diff_reports_added_findings_and_count_changes(tmp_path, capsys) -> None:
    old = write_source(tmp_path, "Old.s", VALID_SOURCE)
    new = write_source(tmp_path, "New.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["diff", str(old), str(new)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert "+ CONSECUTIVE_SEQUENCE_STEPS: Consecutive SFC steps" in out


def test_diff_json_payload(tmp_path, capsys) -> None:
    old = write_source(tmp_path, "Old.s", VALID_SOURCE)
    new = write_source(tmp_path, "New.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["diff", str(old), str(new), "--json"]) == ExitCode.FINDINGS

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.diff"
    assert payload["old"]["parsed"] is True
    [added] = payload["findings"]["added"]
    assert added["rule"] == "CONSECUTIVE_SEQUENCE_STEPS"


def test_diff_reports_structural_count_changes(tmp_path, capsys) -> None:
    with_equation = VALID_SOURCE.replace(
        "ENDDEF (*BasePicture*);",
        "EQUATIONBLOCK Extra COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n   Flag = True;\nENDDEF (*BasePicture*);",
    )
    old = write_source(tmp_path, "Old.s", VALID_SOURCE)
    new = write_source(tmp_path, "New.s", with_equation)

    assert main(["diff", str(old), str(new), "--json"]) == ExitCode.FINDINGS

    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"]["added"] == []
    assert payload["counts"]["changed"] == {"equations": {"old": 0, "new": 1}}

    assert main(["diff", str(old), str(new)]) == ExitCode.FINDINGS
    assert "~ equations: 0 -> 1" in capsys.readouterr().out


def test_diff_reports_a_source_that_stops_parsing(tmp_path, capsys) -> None:
    old = write_source(tmp_path, "Old.s", VALID_SOURCE)
    new = write_source(tmp_path, "New.s", '"only one header"\n')

    assert main(["diff", str(old), str(new)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert "does not parse" in out


def test_diff_reports_removed_findings_and_an_unparseable_old(tmp_path, capsys) -> None:
    old = write_source(tmp_path, "Old.s", CONSECUTIVE_STEPS_SOURCE)
    new = write_source(tmp_path, "New.s", VALID_SOURCE)

    assert main(["diff", str(old), str(new)]) == ExitCode.FINDINGS
    assert "- CONSECUTIVE_SEQUENCE_STEPS: Consecutive SFC steps" in capsys.readouterr().out

    broken = write_source(tmp_path, "Broken.s", '"only one header"\n')
    assert main(["diff", str(broken), str(new)]) == ExitCode.FINDINGS
    assert "Broken.s: does not parse" in capsys.readouterr().out


def test_corpus_summary_and_exit_codes(tmp_path, capsys) -> None:
    write_source(tmp_path, "Clean.s", VALID_SOURCE)
    write_source(tmp_path, "Steps.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["corpus", str(tmp_path), "--summary"]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "files: 2  clean: 1  failing: 1" in out
    assert "CONSECUTIVE_SEQUENCE_STEPS: 1" in out

    assert main(["corpus", str(tmp_path), "--fail-on", "never"]) == ExitCode.OK
    capsys.readouterr()

    assert main(["corpus", str(tmp_path), "--jobs", "2", "--jsonl"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.corpus"
    assert payload["files"] == 2
    assert {Path(row["file"]).name for row in payload["results"]} == {"Clean.s", "Steps.s"}


def test_corpus_reports_unreadable_files(tmp_path, capsys) -> None:
    (tmp_path / "Bad.s").write_bytes(b"\x81")
    write_source(tmp_path, "Clean.s", VALID_SOURCE)

    assert main(["corpus", str(tmp_path), "--fail-on", "any"]) == ExitCode.FINDINGS
    assert "READ_ERROR: 1" in capsys.readouterr().out


def test_corpus_needs_a_directory(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.s", VALID_SOURCE)

    assert main(["corpus", str(source)]) == ExitCode.USAGE
    assert "not a directory" in capsys.readouterr().err

    assert main(["corpus", str(tmp_path), "--jobs", "0"]) == ExitCode.USAGE
    assert "must be 1 or greater" in capsys.readouterr().err

    assert main(["corpus", str(tmp_path), "--jobs", "many"]) == ExitCode.USAGE
    assert "expected an integer" in capsys.readouterr().err
