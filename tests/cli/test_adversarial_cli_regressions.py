# pyright: reportPrivateUsage=false
"""Regression probes for CLI output and input contracts found adversarially."""

from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from sattline_parser.cli import main
from sattline_parser.cli._errors import CliError
from sattline_parser.cli._exit import ExitCode
from sattline_parser.cli._io import read_source
from sattline_parser.cli._json import dumps
from sattline_parser.cli._sarif import _artifact_uri
from sattline_parser.cli.cmds import corpus as corpus_module


class _FailingStdout:
    """A stream whose buffered write fails only on the final flush."""

    encoding = "utf-8"

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        raise self._error

    def fileno(self) -> int:
        raise AttributeError("no descriptor")


@pytest.mark.parametrize(
    "error",
    [BrokenPipeError(), OSError(errno.ENOSPC, "No space left on device")],
    ids=["closed-pipe", "full-device"],
)
def test_a_short_report_flushes_to_the_output_problem_exit_code(
    monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    monkeypatch.setattr("sys.stdout", _FailingStdout(error))

    assert main(["version"]) == ExitCode.USAGE


def test_a_non_output_flush_failure_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdout", _FailingStdout(ValueError("not an output error")))

    with pytest.raises(ValueError, match="not an output error"):
        main(["version"])


def test_json_output_is_ascii_and_round_trips() -> None:
    text = dumps({"name": "Straße"})

    assert text.isascii()
    assert json.loads(text)["name"] == "Straße"


def test_an_empty_stdin_name_is_refused() -> None:
    with pytest.raises(CliError, match="requires --stdin-name"):
        read_source("-", name="")
    with pytest.raises(CliError, match="requires --stdin-name"):
        read_source("-", name="   ")


def test_sarif_uri_survives_a_non_utf8_filename(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    uri = _artifact_uri("caf\udce9.s")

    assert uri == "caf%E9.s"


def test_an_unreadable_corpus_directory_is_an_input_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def failing_walk(_root: Path, onerror: object) -> object:
        assert callable(onerror)
        onerror(PermissionError(errno.EACCES, "Permission denied", str(tmp_path)))
        return iter(())

    monkeypatch.setattr(corpus_module.os, "walk", failing_walk)

    with pytest.raises(CliError, match="cannot read"):
        list(corpus_module._source_paths(tmp_path))


def test_an_unreadable_corpus_directory_without_a_filename_names_the_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def failing_walk(_root: Path, onerror: object) -> object:
        assert callable(onerror)
        onerror(PermissionError(errno.EACCES, "Permission denied"))
        return iter(())

    monkeypatch.setattr(corpus_module.os, "walk", failing_walk)

    with pytest.raises(CliError, match=f"cannot read {tmp_path}"):
        list(corpus_module._source_paths(tmp_path))


def test_a_corpus_directory_keeps_only_source_suffixes(tmp_path: Path) -> None:
    (tmp_path / "Program.s").write_text("", encoding="utf-8")
    (tmp_path / "Notes.txt").write_text("", encoding="utf-8")

    assert [path.name for path in corpus_module._source_paths(tmp_path)] == ["Program.s"]
