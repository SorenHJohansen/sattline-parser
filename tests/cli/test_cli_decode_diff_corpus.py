# pyright: reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
"""``sattline decode``, ``diff`` and ``corpus``."""

from __future__ import annotations

import json
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode
from sattline_parser.cli.cmds import corpus as corpus_command

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
    source = write_source(tmp_path, "Broken.x", '"Syntax version 2.23, date: 2026-10-28-00:00:00.000 C"\n#00\n')

    assert main(["decode", str(source)]) == ExitCode.USAGE
    assert "Unknown compressed marker" in capsys.readouterr().err


def test_paths_absolute_applies_to_decode_and_diff(tmp_path, capsys, monkeypatch) -> None:
    write_source(tmp_path, "M.s", VALID_SOURCE)
    monkeypatch.chdir(tmp_path)
    resolved = str((tmp_path / "M.s").resolve())

    assert main(["decode", "M.s", "--report", "--paths", "absolute"]) == ExitCode.OK
    assert json.loads(capsys.readouterr().out)["file"] == resolved

    assert main(["diff", "M.s", "M.s", "--json", "--paths", "absolute"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["old"]["file"] == resolved
    assert payload["new"]["file"] == resolved


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
    assert payload["counts"]["changed"] == {"equationblocks": {"old": 0, "new": 1}}

    assert main(["diff", str(old), str(new)]) == ExitCode.FINDINGS
    assert "~ equationblocks: 0 -> 1" in capsys.readouterr().out


_NESTED_CHILD = (
    "SUBMODULES\n"
    "   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : MODULEDEFINITION DateCode_ 1\n"
    "   ModuleDef\n"
    "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "{code_block}"
    "   ENDDEF (*Child*);\n"
)

_NESTED_SEQUENCE = (
    "   ModuleCode\n"
    "      SEQUENCE Inner COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
    "         SEQINITSTEP Init\n"
    "         SEQTRANSITION Tr WAIT_FOR True\n"
    "      ENDSEQUENCE\n"
)


def test_diff_reports_a_nested_only_sequence_change(tmp_path, capsys) -> None:
    """A sequence added inside a submodule is a count change, not a silent pass."""
    root = "ModuleDef\nClippingBounds"
    old = write_source(tmp_path, "Old.s", VALID_SOURCE.replace(root, _NESTED_CHILD.format(code_block="") + root))
    new = write_source(
        tmp_path,
        "New.s",
        VALID_SOURCE.replace(root, _NESTED_CHILD.format(code_block=_NESTED_SEQUENCE) + root),
    )

    assert main(["diff", str(old), str(new), "--json"]) == ExitCode.FINDINGS

    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"]["added"] == []
    # VALID_SOURCE carries one root sequence; the child adds the second.
    assert payload["counts"]["changed"] == {"sequences": {"old": 1, "new": 2}}


def test_diff_reports_a_source_that_stops_parsing(tmp_path, capsys) -> None:
    old = write_source(tmp_path, "Old.s", VALID_SOURCE)
    new = write_source(tmp_path, "New.s", '"only one header"\n')

    assert main(["diff", str(old), str(new)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert "does not parse" in out


def test_diff_reports_no_count_changes_when_a_side_does_not_parse(tmp_path, capsys) -> None:
    old = write_source(tmp_path, "Old.s", VALID_SOURCE)
    new = write_source(tmp_path, "New.s", '"only one header"\n')

    assert main(["diff", str(old), str(new), "--json"]) == ExitCode.FINDINGS

    payload = json.loads(capsys.readouterr().out)
    assert payload["old"]["parsed"] is True
    assert payload["new"]["parsed"] is False
    # A missing summary is not a set of zero counts, so no count is reported as
    # changed from null.
    assert payload["counts"]["changed"] == {}

    assert main(["diff", str(old), str(new)]) == ExitCode.FINDINGS
    assert "~" not in capsys.readouterr().out


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

    assert main(["corpus", str(tmp_path), "--fail-on", "none"]) == ExitCode.OK
    capsys.readouterr()

    assert main(["corpus", str(tmp_path), "--jobs", "2", "--jsonl"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.corpus"
    assert payload["files"] == 2
    assert {Path(row["file"]).name for row in payload["results"]} == {"Clean.s", "Steps.s"}
    assert all("warnings" not in row for row in payload["results"])


def test_corpus_jobs_match_a_serial_run(tmp_path, capsys) -> None:
    for index in range(6):
        write_source(
            tmp_path,
            f"Unit{index}.s",
            VALID_SOURCE if index % 2 else CONSECUTIVE_STEPS_SOURCE,
        )

    assert main(["corpus", str(tmp_path), "--jobs", "1", "--json"]) == ExitCode.FINDINGS
    serial = json.loads(capsys.readouterr().out)
    assert main(["corpus", str(tmp_path), "--jobs", "4", "--json"]) == ExitCode.FINDINGS
    pooled = json.loads(capsys.readouterr().out)

    assert pooled == serial


def test_corpus_falls_back_when_a_pool_cannot_start(tmp_path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    from sattline_parser.cli.cmds import corpus as corpus_command  # noqa: PLC0415

    write_source(tmp_path, "Clean.s", VALID_SOURCE)
    write_source(tmp_path, "Other.s", VALID_SOURCE)

    def unavailable(max_workers: int) -> object:
        raise OSError("no fork today")

    monkeypatch.setattr(corpus_command, "process_pool", unavailable)

    assert main(["corpus", str(tmp_path), "--jobs", "2", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"] == 2


def test_corpus_rejects_removed_fail_on_values(tmp_path, capsys) -> None:
    write_source(tmp_path, "Clean.s", VALID_SOURCE)

    for value in ("warning", "any", "never"):
        assert main(["corpus", str(tmp_path), "--fail-on", value]) == ExitCode.USAGE
        assert "expected one of" in capsys.readouterr().err


def test_corpus_reports_unreadable_files(tmp_path, capsys) -> None:
    (tmp_path / "Bad.s").write_bytes(b"\x81")
    write_source(tmp_path, "Clean.s", VALID_SOURCE)

    assert main(["corpus", str(tmp_path), "--fail-on", "error"]) == ExitCode.FINDINGS
    assert "READ_ERROR: 1" in capsys.readouterr().out


def test_corpus_needs_a_directory(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "M.s", VALID_SOURCE)

    assert main(["corpus", str(source)]) == ExitCode.USAGE
    assert "not a directory" in capsys.readouterr().err

    assert main(["corpus", str(tmp_path), "--jobs", "0"]) == ExitCode.USAGE
    assert "must be 1 or greater" in capsys.readouterr().err

    assert main(["corpus", str(tmp_path), "--jobs", "many"]) == ExitCode.USAGE
    assert "expected an integer" in capsys.readouterr().err

    assert main(["corpus", str(tmp_path), "--jobs", "1000"]) == ExitCode.USAGE
    assert "or less" in capsys.readouterr().err


def test_corpus_falls_back_when_the_pool_dies(tmp_path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    write_source(tmp_path, "Clean.s", VALID_SOURCE)
    write_source(tmp_path, "Other.s", VALID_SOURCE)

    class DeadPool:
        def map(self, function, iterable, chunksize: int = 1):
            raise BrokenProcessPool("a worker died")

        def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
            return None

    def dead_pool(max_workers: int) -> DeadPool:
        return DeadPool()

    monkeypatch.setattr(corpus_command, "process_pool", dead_pool)

    assert main(["corpus", str(tmp_path), "--jobs", "2", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"] == 2


def test_corpus_cancels_a_dead_pool_on_interrupt(tmp_path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    write_source(tmp_path, "Clean.s", VALID_SOURCE)
    write_source(tmp_path, "Other.s", VALID_SOURCE)
    shutdowns: list[dict[str, object]] = []

    class InterruptedPool:
        def map(self, function, iterable, chunksize: int = 1):
            raise KeyboardInterrupt

        def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
            shutdowns.append({"wait": wait, "cancel_futures": cancel_futures})

    def interrupted_pool(max_workers: int) -> InterruptedPool:
        return InterruptedPool()

    monkeypatch.setattr(corpus_command, "process_pool", interrupted_pool)

    assert main(["corpus", str(tmp_path), "--jobs", "2"]) == ExitCode.INTERRUPTED
    assert shutdowns == [{"wait": False, "cancel_futures": True}]


def test_corpus_stays_in_process_in_a_daemonic_parent(tmp_path, capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    write_source(tmp_path, "Clean.s", VALID_SOURCE)
    write_source(tmp_path, "Other.s", VALID_SOURCE)
    monkeypatch.setattr(corpus_command, "pool_allowed", lambda: False)

    assert main(["corpus", str(tmp_path), "--jobs", "2", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"] == 2
