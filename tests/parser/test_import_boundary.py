"""The parser-only import path must not load the project layer."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import sattline_parser

_SRC = Path(__file__).resolve().parents[2] / "src"


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
    )


def test_importing_the_parser_facade_does_not_load_the_project_layer() -> None:
    completed = _run("import sys, sattline_parser.api; print('sattline_parser.project' in sys.modules)")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False"


def test_project_exports_resolve_in_process_and_unknown_names_raise() -> None:
    assert callable(sattline_parser.parse_graphics_text)

    with pytest.raises(AttributeError, match="has no attribute"):
        _ = sattline_parser.not_a_real_export


def test_project_exports_are_lazy() -> None:
    completed = _run(
        "import sys, sattline_parser; "
        "before = 'sattline_parser.project' in sys.modules; "
        "value = sattline_parser.parse_graphics_text; "
        "after = 'sattline_parser.project' in sys.modules; "
        "print(before, after, callable(value))"
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False True True"
