# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""``sattline project``: programs, artifacts, dependency graph and cycles."""

from __future__ import annotations

import json

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import VALID_SOURCE, write_source

_LIB_SOURCE = VALID_SOURCE.replace("name: Sample", "name: {name}")


def _program(directory, name: str, dependencies: str | None = None) -> None:
    """Write a code unit, plus a .l sidecar when dependencies are declared."""
    write_source(directory, f"{name}.s", _LIB_SOURCE.replace("{name}", name))
    if dependencies is not None:
        (directory / f"{name}.l").write_bytes(dependencies.encode("cp1252"))


def test_programs_artifacts_and_edges(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")
    _program(tmp_path, "Child", "Base")
    _program(tmp_path, "Leaf", "Child")

    assert main(["project", str(tmp_path)]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "programs: 3" in out
    # Program rows keep the declared casing; graph edges use canonical keys.
    assert "Child" in out and "depends on: Base" in out
    assert "edges: 2" in out


def test_graph_only_and_traversal(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")
    _program(tmp_path, "Child", "Base")
    _program(tmp_path, "Leaf", "Child")

    assert main(["project", str(tmp_path), "--graph"]) == ExitCode.OK
    assert "child -> base" in capsys.readouterr().out

    assert main(["project", str(tmp_path), "--graph", "--of", "Leaf", "--depth", "1"]) == ExitCode.OK
    assert capsys.readouterr().out.strip().splitlines() == ["leaf -> child"]

    assert main(["project", str(tmp_path), "--graph", "--of", "Base", "--reverse", "--depth", "1"]) == ExitCode.OK
    assert "child -> base" in capsys.readouterr().out


def test_json_payload(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")
    _program(tmp_path, "Child", "Base")

    assert main(["project", str(tmp_path), "--json"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.project"
    assert payload["mode"] == "draft"
    names = {program["name"] for program in payload["programs"]}
    assert names == {"Base", "Child"}
    child = next(program for program in payload["programs"] if program["name"] == "Child")
    assert child["code"] == ".s"
    assert child["dependencies"] == ["Base"]
    assert payload["edges"] == [{"from": "child", "to": "base"}]
    assert payload["cycles"] == []


def test_missing_root_and_empty_tree_are_usage_errors(tmp_path, capsys) -> None:
    assert main(["project", str(tmp_path / "Absent")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err

    assert main(["project", str(tmp_path)]) == ExitCode.USAGE
    assert "no source files directly under" in capsys.readouterr().err


def test_sources_nested_below_a_root_are_not_discovered(tmp_path, capsys) -> None:
    library = tmp_path / "ABBLib"
    library.mkdir()
    _program(library, "Base")

    # A root is a library directory: the loader resolves artifacts directly
    # inside it, so discovery must not promise files it cannot load.
    assert main(["project", str(tmp_path)]) == ExitCode.USAGE
    assert "pass each library directory as a root" in capsys.readouterr().err

    assert main(["project", str(library)]) == ExitCode.OK
    assert "programs: 1" in capsys.readouterr().out


def test_strict_load_failure_is_a_finding_and_lenient_continues(tmp_path, capsys) -> None:
    _program(tmp_path, "Child", "MissingLib")

    assert main(["project", str(tmp_path)]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "cannot load project" in out
    assert "MissingLib" in out

    # --lenient keeps what loaded, but the omission is a finding, not silence.
    assert main(["project", str(tmp_path), "--lenient"]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "programs: 1" in out
    assert "load-skipped MissingLib" in out

    assert main(["project", str(tmp_path), "--lenient", "--json"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert [row["name"] for row in payload["programs"]] == ["Child"]
    assert [row["kind"] for row in payload["diagnostics"]] == ["load-skipped"]


def test_targets_flag_limits_the_load(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")
    _program(tmp_path, "Child", "Base")

    assert main(["project", str(tmp_path), "--targets", "Child"]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "programs: 2" in out
    assert "Child" in out


def test_bad_target_is_a_finding(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")

    assert main(["project", str(tmp_path), "--targets", "Nope"]) == ExitCode.FINDINGS
    assert "cannot load project" in capsys.readouterr().out


def test_of_without_depth_walks_the_whole_tree(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")
    _program(tmp_path, "Child", "Base")
    _program(tmp_path, "Leaf", "Child")

    assert main(["project", str(tmp_path), "--graph", "--of", "Leaf"]) == ExitCode.OK
    assert capsys.readouterr().out.splitlines() == ["leaf -> child", "child -> base"]


def test_graph_json_payload(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")
    _program(tmp_path, "Child", "Base")

    assert main(["project", str(tmp_path), "--graph", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.project"
    assert payload["edges"] == [{"from": "child", "to": "base"}]
    assert payload["cycles"] == []


def test_dependency_cycle_is_a_finding(tmp_path, capsys) -> None:
    _program(tmp_path, "Alpha", "Beta")
    _program(tmp_path, "Beta", "Alpha")

    assert main(["project", str(tmp_path)]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "cycles:" in out
    assert "alpha -> beta -> alpha" in out
    assert "dependency-cycle" in out

    assert main(["project", str(tmp_path), "--cycles"]) == ExitCode.FINDINGS
    assert capsys.readouterr().out.strip() == "alpha -> beta -> alpha"

    assert main(["project", str(tmp_path), "--cycles", "--json"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["cycles"] == [["alpha", "beta"]]


def test_bad_depth_is_a_usage_error(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")

    assert main(["project", str(tmp_path), "--depth", "zero"]) == ExitCode.USAGE
    assert "expected an integer" in capsys.readouterr().err

    assert main(["project", str(tmp_path), "--depth", "0"]) == ExitCode.USAGE
    assert "must be 1 or greater" in capsys.readouterr().err
