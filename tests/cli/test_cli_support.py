# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""Shared CLI plumbing: AST serialisation, path display and finding mapping."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pytest

from sattline_parser.cli._findings import Finding, finding_from_diagnostic
from sattline_parser.cli._io import display_path
from sattline_parser.cli._json import to_jsonable
from sattline_parser.models.ast_model import SourceSpan
from sattline_parser.project import LoadMode
from sattline_parser.validation import Diagnostic, DiagnosticCode


class _Colour(Enum):
    RED = "red"


@dataclass
class _Node:
    name: str
    child: object = None
    items: tuple[object, ...] = ()
    parse_tree: object = "tooling state"


def test_to_jsonable_handles_scalars_enums_paths_and_spans() -> None:
    span = SourceSpan(start=1, end=4, line=2, column=3)

    assert to_jsonable(None, depth=1) is None
    assert to_jsonable(True, depth=1) is True
    assert to_jsonable(7, depth=1) == 7
    assert to_jsonable(2.5, depth=1) == 2.5
    assert to_jsonable("text", depth=1) == "text"
    assert to_jsonable(_Colour.RED, depth=1) == "red"
    assert to_jsonable(Path("/tmp/x"), depth=1) == "/tmp/x"
    assert to_jsonable(span, depth=1) == {"start": 1, "end": 4, "line": 2, "column": 3}
    assert to_jsonable(LoadMode.DRAFT, depth=1) == "draft"


def test_to_jsonable_recurses_into_dataclasses_and_containers() -> None:
    node = _Node(name="top", child=_Node(name="inner"), items=(1, {"a": "b"}))

    payload = to_jsonable(node, depth=4)

    assert payload == {
        "name": "top",
        "child": {"name": "inner", "child": None, "items": []},
        "items": [1, {"a": "b"}],
    }


def test_to_jsonable_emits_placeholders_at_the_depth_limit() -> None:
    node = _Node(name="top", child=_Node(name="inner"), items=(1, 2, 3))

    assert to_jsonable(node, depth=0) == "<_Node>"
    assert to_jsonable([1, 2], depth=0) == "<2 items>"
    assert to_jsonable({"a": 1}, depth=0) == "<1 keys>"
    assert to_jsonable(node, depth=1) == {"name": "top", "child": "<_Node>", "items": "<3 items>"}


def test_to_jsonable_falls_back_to_repr() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "opaque-value"

    assert to_jsonable(Opaque(), depth=3) == "opaque-value"


def test_display_path_respects_the_mode_and_keeps_stdin_names(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "A.s").write_text("", encoding="utf-8")

    assert display_path("A.s", absolute=False) == "A.s"
    assert display_path("A.s", absolute=True) == str(tmp_path / "A.s")
    assert display_path("<stdin>", absolute=True) == "<stdin>"


def test_finding_from_diagnostic_attaches_the_source_line() -> None:
    diagnostic = Diagnostic(
        code=DiagnosticCode.CONSECUTIVE_SEQUENCE_STEPS,
        message="Consecutive SFC steps",
        span=SourceSpan(start=10, end=20, line=2, column=4),
    )

    finding = finding_from_diagnostic(
        diagnostic, file="M.s", source_text="line one\n   SEQSTEP S2\n", absolute_paths=False
    )

    assert finding.rule == "CONSECUTIVE_SEQUENCE_STEPS"
    assert finding.severity == "error"
    assert (finding.line, finding.column) == (2, 4)
    assert finding.source_line == "   SEQSTEP S2"
    assert (finding.start, finding.end) == (10, 20)
    assert finding.location() == "M.s:2:4: "


def test_finding_locations_degrade_gracefully() -> None:
    base = {
        "severity": "error",
        "message": "m",
        "rule": "R",
    }
    assert Finding(**base).location() == ""
    assert Finding(**base, file="M.s").location() == "M.s: "
    assert Finding(**base, file="M.s", line=3).location() == "M.s:3: "
    assert Finding(**base, file="M.s", line=3, column=5).location() == "M.s:3:5: "


def test_finding_from_diagnostic_without_source_line() -> None:
    diagnostic = Diagnostic(code=DiagnosticCode.SEQUENCE_POSITION_INVALID, message="no span")

    finding = finding_from_diagnostic(diagnostic, file="M.s", source_text="", absolute_paths=False)

    assert finding.line is None
    assert finding.source_line is None
    assert finding.is_error is True


def test_finding_from_diagnostic_out_of_range_line() -> None:
    diagnostic = Diagnostic(
        code=DiagnosticCode.SEQUENCE_POSITION_INVALID,
        message="far away",
        span=SourceSpan(start=0, end=0, line=9, column=1),
    )

    finding = finding_from_diagnostic(diagnostic, file="M.s", source_text="one line\n", absolute_paths=False)

    assert finding.source_line is None


@pytest.mark.parametrize("severity", ["error"])
def test_finding_json_shape(severity: str) -> None:
    payload = Finding(severity="error", message="m", rule="R", file="M.s").to_json()

    assert payload["severity"] == severity
    assert set(payload) == {
        "severity",
        "message",
        "rule",
        "file",
        "line",
        "column",
        "start",
        "end",
        "hint",
        "source_line",
    }
