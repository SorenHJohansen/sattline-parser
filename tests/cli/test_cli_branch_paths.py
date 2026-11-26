# pyright: reportPrivateUsage=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
"""Branch coverage for CLI helpers whose rare sides normal commands do not reach."""

from __future__ import annotations

import argparse

from sattline_parser.ast import FrameModule, ModuleCode, ModuleHeader, Sequence, SFCTransition, Variable
from sattline_parser.cli._ast_walk import _QueryVisitor
from sattline_parser.cli._findings import Finding
from sattline_parser.cli._sarif import _location
from sattline_parser.cli.cmds._common import _print_finding_text
from sattline_parser.cli.cmds.graphics import _normalize_scan_message
from sattline_parser.cli.cmds.project import _emit_graph, _emit_programs, _tree
from sattline_parser.cli.cmds.rules import _print_rule
from sattline_parser.project import SattLineProgram
from sattline_parser.validation.diagnostics import DiagnosticCode
from sattline_parser.validation.rules import Rule, RuleScope, RuleStatus


def _header(name: str) -> ModuleHeader:
    return ModuleHeader(name=name, invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0))


def test_a_transition_without_a_condition_adds_only_its_symbol_row() -> None:
    visitor = _QueryVisitor()

    visitor.visit_SFCTransition(SFCTransition(name="Wait", condition=None))

    assert [(row.kind, row.name, row.detail) for row in visitor.rows] == [("symbols", "Wait", "transition")]


def test_a_frame_module_body_is_visited_without_its_declarations() -> None:
    visitor = _QueryVisitor()
    frame = FrameModule(
        header=_header("Frame"),
        localvariables=[Variable(name="Hidden", datatype="integer")],
        moduledef=None,
        modulecode=ModuleCode(sequences=[Sequence(name="Flow", type="SEQUENCE", position=(0.0, 0.0), size=(1.0, 1.0))]),
    )

    visitor._visit_module_body(frame, declarations=False)

    # The local variable is skipped, and the absent module definition does not
    # stop the walk from reaching the module code.
    assert [(row.kind, row.name, row.detail) for row in visitor.rows] == [
        ("sequences", "Flow", "SEQUENCE, 0 element(s)")
    ]


def test_a_finding_without_a_line_has_no_sarif_region() -> None:
    location = _location(Finding(severity="error", message="message", rule="R", file="Unit.s", line=None))

    assert location is not None
    physical = location["physicalLocation"]
    assert isinstance(physical, dict)
    assert "region" not in physical
    assert physical["artifactLocation"] == {"uri": "Unit.s"}


def test_a_finding_with_a_line_below_one_has_no_sarif_region() -> None:
    location = _location(Finding(severity="error", message="message", rule="R", file="Unit.s", line=0, column=2))

    assert location is not None
    physical = location["physicalLocation"]
    assert isinstance(physical, dict)
    assert "region" not in physical


def test_a_finding_with_a_source_line_but_no_column_prints_no_caret(capsys) -> None:
    finding = Finding(
        severity="error",
        message="bad value",
        rule="R",
        file="Unit.s",
        line=3,
        column=None,
        source_line="      Total = 1;",
    )

    _print_finding_text(finding)

    out = capsys.readouterr().out
    assert "Unit.s:3: bad value" in out
    assert "Total = 1;" in out
    assert "^" not in out


def test_a_scan_detail_that_is_not_parser_text_keeps_the_whole_message() -> None:
    message = "Could not parse expression: value missing"

    assert _normalize_scan_message(message) == message


def test_a_rule_without_details_prints_no_details_line(capsys) -> None:
    rule = Rule(
        code=DiagnosticCode.UNDEFINED_VARIABLE,
        summary="A used variable must be declared.",
        scope=RuleScope.CODE,
        status=RuleStatus.ACTIVE,
    )

    _print_rule(rule)

    out = capsys.readouterr().out
    assert "SL-V019" in out
    assert "summary:  A used variable must be declared." in out
    assert "details:" not in out


def test_a_tree_walk_keeps_an_already_visited_neighbour_as_an_edge() -> None:
    edges = [{"from": "Alpha", "to": "Beta"}, {"from": "Alpha", "to": "Beta"}]

    walked = _tree(edges, "Alpha", reverse=False, depth=None)

    assert walked == [{"from": "Alpha", "to": "Beta"}, {"from": "Alpha", "to": "Beta"}]


def test_project_text_without_diagnostics_and_a_row_without_a_line(capsys) -> None:
    programs: dict[str, SattLineProgram] = {}
    validation: list[dict[str, object]] = [
        {"program": "Unit", "code": "SL-V019", "message": "Missing name", "line": None, "column": None}
    ]

    _emit_programs(programs, [], [], validation, args=argparse.Namespace(json=False, jsonl=False))

    out = capsys.readouterr().out
    assert "programs: 0" in out
    assert "edges: 0" in out
    assert "diagnostics:" not in out
    assert "validation:" in out
    assert "  SL-V019 Unit: Missing name" in out


def test_graph_text_prints_a_row_without_a_line(capsys) -> None:
    validation: list[dict[str, object]] = [
        {"program": "Unit", "code": "SL-V019", "message": "Missing name", "line": None, "column": None}
    ]

    _emit_graph([], validation, args=argparse.Namespace(json=False, jsonl=False))

    out = capsys.readouterr().out
    assert out.splitlines() == ["validation:", "  SL-V019 Unit: Missing name"]
