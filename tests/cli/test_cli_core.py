# pyright: reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
"""Entry point, exit codes, dispatch and ``version``."""

from __future__ import annotations

import io
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from sattline_parser import __main__ as entry_point
from sattline_parser import __version__
from sattline_parser.cli import build_parser, main
from sattline_parser.cli._exit import ExitCode
from sattline_parser.cli.cmds import check as check_command

from ._cli_support import VALID_SOURCE

_SRC = Path(__file__).resolve().parents[2] / "src"


def _many_findings_source(count: int) -> str:
    """A unit with *count* undefined variables, so its report fills a pipe buffer."""
    assignments = "".join(f"   Flag = Missing{index};\n" for index in range(count))
    return VALID_SOURCE.replace(
        "ENDDEF (*BasePicture*);",
        f"EQUATIONBLOCK Extra COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n{assignments}ENDDEF (*BasePicture*);",
    )


def test_version_prints_the_tool_and_schema_versions(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == ExitCode.OK
    assert capsys.readouterr().out == f"sattline {__version__}\n"

    assert main(["version", "--json"]) == ExitCode.OK
    payload = capsys.readouterr().out
    assert '"schema": "sattline.v1.version"' in payload
    assert f'"version": "{__version__}"' in payload
    assert '"check": "sattline.v1.check"' in payload


def test_unknown_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["explain", "SL-V033"]) == ExitCode.USAGE
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err
    assert "sattline --help" in captured.err


def test_missing_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == ExitCode.USAGE
    assert "required" in capsys.readouterr().err


def test_mutually_exclusive_output_flags(capsys: pytest.CaptureFixture[str], tmp_path) -> None:
    source = tmp_path / "A.s"
    source.write_text("", encoding="utf-8")
    assert main(["check", str(source), "--json", "--jsonl"]) == ExitCode.USAGE
    assert "not allowed with argument" in capsys.readouterr().err


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_internal_errors_return_a_clean_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(_args: object) -> int:
        raise RuntimeError("transformer exploded")

    monkeypatch.setattr(check_command, "run", boom)

    assert main(["check", "nowhere.s"]) == ExitCode.INTERNAL
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "internal error: RuntimeError: transformer exploded" in captured.err
    assert "Traceback" not in captured.err


def test_debug_prints_the_traceback(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def boom(_args: object) -> int:
        raise RuntimeError("transformer exploded")

    monkeypatch.setattr(check_command, "run", boom)

    assert main(["--debug", "check", "nowhere.s"]) == ExitCode.INTERNAL
    assert "Traceback" in capsys.readouterr().err


def test_interrupt_is_a_dedicated_exit(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def interrupted(_args: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(check_command, "run", interrupted)

    assert main(["check", "nowhere.s"]) == ExitCode.INTERRUPTED
    assert int(ExitCode.INTERRUPTED) == 130
    assert "interrupted" in capsys.readouterr().err


def test_a_broken_pipe_is_a_usage_exit_not_an_internal_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_args: object) -> int:
        raise BrokenPipeError

    monkeypatch.setattr(check_command, "run", broken)
    # A stream without a descriptor exercises the guard in the stdout discard.
    monkeypatch.setattr(sys, "stdout", io.StringIO())

    assert main(["check", "nowhere.s"]) == ExitCode.USAGE
    assert capsys.readouterr().err == ""


def test_a_closed_stdout_stops_the_report_in_a_subprocess(tmp_path) -> None:
    source = tmp_path / "Many.s"
    source.write_bytes(_many_findings_source(2000).encode("cp1252"))
    process = subprocess.Popen(
        [sys.executable, "-m", "sattline_parser", "check", str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
    )
    assert process.stdout is not None
    assert process.stderr is not None
    process.stdout.close()
    stderr = process.stderr.read()
    assert process.wait(timeout=60) == ExitCode.USAGE, stderr
    # The interpreter's exit flush must not report a second failure (exit 120).
    assert b"Exception ignored" not in stderr


def test_argv_defaults_to_the_process_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["sattline", "version"])
    assert main() == ExitCode.OK
    assert capsys.readouterr().out.startswith("sattline ")


def test_parser_declares_the_three_p0_commands() -> None:
    parser = build_parser()
    actions = [action for action in parser._actions if action.dest == "command"]
    assert actions and isinstance(actions[0].choices, dict)
    assert sorted(actions[0].choices) == [
        "check",
        "corpus",
        "decode",
        "diff",
        "graphics",
        "parse",
        "project",
        "query",
        "rules",
        "version",
    ]


def test_module_entry_point_is_importable() -> None:
    assert entry_point.main is main
    assert entry_point.main(["version"]) == ExitCode.OK


def test_module_entry_point_runs_as_a_process() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "sattline_parser", "version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("sattline ")


def test_module_entry_point_guard_returns_the_cli_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["sattline", "version"])
    monkeypatch.delitem(sys.modules, "sattline_parser.__main__", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("sattline_parser.__main__", run_name="__main__", alter_sys=True)

    assert exc_info.value.code == ExitCode.OK
    assert capsys.readouterr().out.startswith("sattline ")
