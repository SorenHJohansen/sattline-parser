# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""Entry point, exit codes, dispatch and ``version``."""

from __future__ import annotations

import subprocess
import sys

import pytest

from sattline_parser import __main__ as entry_point
from sattline_parser import __version__
from sattline_parser.cli import build_parser, main
from sattline_parser.cli._exit import ExitCode
from sattline_parser.cli.cmds import check as check_command


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


def test_interrupt_is_a_usage_exit(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def interrupted(_args: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(check_command, "run", interrupted)

    assert main(["check", "nowhere.s"]) == ExitCode.USAGE
    assert "interrupted" in capsys.readouterr().err


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
