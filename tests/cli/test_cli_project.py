# pyright: reportMissingParameterType=false, reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
"""``sattline project``: programs, artifacts, dependency graph and cycles."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode
from sattline_parser.cli.cmds import project as project_cmd
from sattline_parser.project._cycles import dependency_cycles

from ._cli_support import CONSECUTIVE_STEPS_SOURCE, PARSE_ERROR_SOURCE, VALID_SOURCE, write_source


def _cycles(edges: list[tuple[str, str]]) -> list[list[str]]:
    return [list(cycle[:-1]) for cycle in dependency_cycles(edges)]


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


def test_a_later_library_with_the_same_name_is_not_discovered(tmp_path, capsys) -> None:
    """The loading path holds one library per name; a shadowed root adds no targets."""
    first = tmp_path / "one" / "libs"
    second = tmp_path / "two" / "libs"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    _program(first, "Alpha")
    _program(second, "Beta")

    assert main(["project", str(first), str(second)]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "programs: 1" in out
    assert "Alpha" in out
    assert "Beta" not in out


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


_DISTRIBUTION = (
    "DistributionData\n"
    ' ( Version "Distributiondata version 1.0" )\n'
    "SourceCodeSystems\n"
    " (  )\n"
    "ExecutingSystems\n"
    " ( Controller\n"
    '    ( Name "172.18.0.1"\n'
    "      Download ShortStopReconfig ) )\n"
)

_DISTRIBUTION_EMPTY = (
    'DistributionData\n ( Version "Distributiondata version 1.0" )\nSourceCodeSystems\n (  )\nExecutingSystems\n (  )\n'
)


def test_json_payload_reports_executing_system(tmp_path, capsys) -> None:
    _program(tmp_path, "Running")
    _program(tmp_path, "Idle")
    _program(tmp_path, "Unknown")
    write_source(tmp_path, "Running.p", _DISTRIBUTION)
    write_source(tmp_path, "Idle.p", _DISTRIBUTION_EMPTY)

    assert main(["project", str(tmp_path), "--json"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    rows = {row["name"]: row for row in payload["programs"]}
    assert rows["Running"]["has_executing_system"] is True
    assert rows["Running"]["distribution"] == ".p"
    assert rows["Running"]["executing_systems"] == [
        {"kind": "Controller", "name": "172.18.0.1", "download": "ShortStopReconfig"}
    ]
    assert rows["Idle"]["has_executing_system"] is False
    assert rows["Idle"]["executing_systems"] == []
    assert rows["Unknown"]["has_executing_system"] is None
    assert rows["Unknown"]["distribution"] is None


def test_text_output_reports_executing_system(tmp_path, capsys) -> None:
    _program(tmp_path, "Running")
    _program(tmp_path, "Idle")
    _program(tmp_path, "Unknown")
    write_source(tmp_path, "Running.p", _DISTRIBUTION)
    write_source(tmp_path, "Idle.p", _DISTRIBUTION_EMPTY)

    assert main(["project", str(tmp_path)]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "distribution=.p exec=yes (172.18.0.1)" in out
    assert "distribution=.p exec=no" in out
    assert "distribution=- exec=-" in out


def test_malformed_distribution_companion_is_a_finding(tmp_path, capsys) -> None:
    _program(tmp_path, "Main")
    write_source(tmp_path, "Main.p", "not a distribution companion\n")

    assert main(["project", str(tmp_path)]) == ExitCode.FINDINGS
    assert "distribution companion" in capsys.readouterr().out


def test_default_cache_dir_ignores_a_relative_xdg_cache_home(tmp_path, monkeypatch) -> None:
    """A relative cache root would put the cache inside the tree being read."""
    monkeypatch.setenv("XDG_CACHE_HOME", "relative-cache")

    assert project_cmd._default_cache_dir() is None


def test_default_cache_dir_survives_an_unknown_home(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(project_cmd.Path, "home", classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError())))

    assert project_cmd._default_cache_dir() is None


def test_default_cache_dir_honours_an_absolute_xdg_cache_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    assert project_cmd._default_cache_dir() == tmp_path / "sattline-parser" / "project"


def test_search_path_notation_uses_the_written_order(tmp_path, capsys) -> None:
    gc = tmp_path / "LibA" / "UnitLib"
    ha = tmp_path / "LibB" / "UnitLib"
    gc.mkdir(parents=True)
    ha.mkdir(parents=True)
    _program(gc, "Program1")
    _program(ha, "Program1")

    assert (
        main(
            [
                "project",
                "--search-path",
                r"LibA\UnitLib,LibB\UnitLib",
                "--search-path-base",
                str(tmp_path),
                "--targets",
                "Program1",
                "--json",
            ]
        )
        == ExitCode.OK
    )

    payload = json.loads(capsys.readouterr().out)
    assert [row["resolved_base"] for row in payload["programs"]] == [str(gc.resolve())]


def test_positional_roots_use_the_written_order(tmp_path, capsys) -> None:
    gc = tmp_path / "LibA" / "UnitLib"
    ha = tmp_path / "LibB" / "UnitLib"
    gc.mkdir(parents=True)
    ha.mkdir(parents=True)
    _program(gc, "Program1")
    _program(ha, "Program1")

    assert main(["project", str(ha), str(gc), "--targets", "Program1", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert [row["resolved_base"] for row in payload["programs"]] == [str(ha.resolve())]

    assert main(["project", str(gc), str(ha), "--targets", "Program1", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert [row["resolved_base"] for row in payload["programs"]] == [str(gc.resolve())]


def test_search_path_and_positional_roots_are_mutually_exclusive(tmp_path, capsys) -> None:
    _program(tmp_path, "Program1")

    assert main(["project", str(tmp_path), "--search-path", str(tmp_path)]) == ExitCode.USAGE
    assert "either ROOT... or --search-path" in capsys.readouterr().err


def test_search_path_base_requires_search_path(tmp_path, capsys) -> None:
    _program(tmp_path, "Program1")

    assert main(["project", str(tmp_path), "--search-path-base", str(tmp_path)]) == ExitCode.USAGE
    assert "--search-path-base requires --search-path" in capsys.readouterr().err


def test_search_path_with_no_entries_is_a_usage_error(tmp_path, capsys) -> None:
    assert main(["project", "--search-path", " , ,, "]) == ExitCode.USAGE
    assert "no entries" in capsys.readouterr().err


def test_project_without_a_root_is_a_usage_error(capsys) -> None:
    assert main(["project"]) == ExitCode.USAGE
    assert "expected at least one root" in capsys.readouterr().err


def test_missing_root_and_empty_tree_are_usage_errors(tmp_path, capsys) -> None:
    assert main(["project", str(tmp_path / "Absent")]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err

    not_a_directory = tmp_path / "File.txt"
    not_a_directory.write_text("x")
    assert main(["project", str(not_a_directory)]) == ExitCode.USAGE
    assert "not a directory" in capsys.readouterr().err

    assert main(["project", str(tmp_path)]) == ExitCode.USAGE
    assert "no source files directly under" in capsys.readouterr().err


def test_sources_nested_below_a_root_are_not_discovered(tmp_path, capsys) -> None:
    library = tmp_path / "Library"
    library.mkdir()
    _program(library, "Base")

    # A root is a library directory: the loader resolves artifacts directly
    # inside it, so discovery must not promise files it cannot load.
    assert main(["project", str(tmp_path)]) == ExitCode.USAGE
    assert "pass each library directory as a root" in capsys.readouterr().err

    assert main(["project", str(library)]) == ExitCode.OK
    assert "programs: 1" in capsys.readouterr().out


def test_load_failure_is_a_finding(tmp_path, capsys) -> None:
    _program(tmp_path, "Child", "MissingLib")

    assert main(["project", str(tmp_path)]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "cannot load project" in out
    assert "MissingLib" in out

    assert main(["project", str(tmp_path), "--json"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["programs"] == []
    assert [row["rule"] for row in payload["findings"]] == ["PROJECT_LOAD_ERROR"]


def test_a_load_failure_logs_no_parser_trace_without_debug(tmp_path, capsys, caplog) -> None:
    """A failed parse is the structured finding, not a parser log on stderr."""
    write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    with caplog.at_level(logging.ERROR, logger="sattline_parser"):
        assert main(["project", str(tmp_path), "--json"]) == ExitCode.FINDINGS
    captured = capsys.readouterr()
    assert [row["rule"] for row in json.loads(captured.out)["findings"]] == ["PROJECT_LOAD_ERROR"]
    assert captured.err == ""
    assert caplog.records == []


def test_a_parse_failure_in_the_tree_carries_its_position(tmp_path, capsys) -> None:
    """A load finding keeps the cause's parser sentence and location."""
    write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    assert main(["project", str(tmp_path), "--json", "--workers", "1"]) == ExitCode.FINDINGS

    [finding] = json.loads(capsys.readouterr().out)["findings"]
    assert finding["rule"] == "PROJECT_LOAD_ERROR"
    assert (finding["line"], finding["column"]) == (7, 21)
    assert "unexpected end of file; expected ';'" in finding["message"]
    assert finding["hint"].startswith("the unit ends before a required ';'")


@pytest.mark.parametrize("workers", ["1", "2"])
def test_a_load_failure_names_the_broken_file_and_its_failing_line(tmp_path, capsys, workers) -> None:
    """The finding carries the artifact path and the excerpt, not just a number."""
    write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    assert main(["project", str(tmp_path), "--json", "--no-cache", "--workers", workers]) == ExitCode.FINDINGS

    [finding] = json.loads(capsys.readouterr().out)["findings"]
    assert finding["file"] == str(tmp_path / "Broken.s")
    assert finding["line"] == 7
    assert finding["source_line"] == "ENDDEF (*BasePicture*)"


def test_debug_keeps_the_parser_trace_for_a_load_failure(tmp_path, caplog, capsys) -> None:
    write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    with caplog.at_level(logging.ERROR, logger="sattline_parser"):
        assert main(["--debug", "project", str(tmp_path), "--json"]) == ExitCode.FINDINGS
    records = [record for record in caplog.records if record.name == "sattline_parser"]
    assert records and any(record.exc_info is not None for record in records)
    # The log reaches stderr through the CLI's own handler, exactly once.
    assert capsys.readouterr().err.count("Parser parse failure") == 1


def test_cli_an_unreadable_root_is_an_input_error(tmp_path, capsys) -> None:
    """A root the process may not list is exit 2, never an internal error."""
    if os.name != "posix" or os.geteuid() == 0:
        pytest.skip("mode bits deny reads on POSIX, and root bypasses them")
    root = tmp_path / "closed"
    root.mkdir()
    _program(root, "Hidden")
    root.chmod(0o000)
    try:
        assert main(["project", str(root)]) == ExitCode.USAGE
        assert "cannot read" in capsys.readouterr().err
    finally:
        root.chmod(0o755)


def test_a_root_that_cannot_be_probed_is_an_input_error(tmp_path, capsys, monkeypatch) -> None:
    root = tmp_path / "probe"
    root.mkdir()
    real_exists = Path.exists

    def failing_exists(self: Path) -> bool:
        if self == root:
            raise OSError(13, "Permission denied")
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", failing_exists)

    assert main(["project", str(root)]) == ExitCode.USAGE
    assert "cannot read" in capsys.readouterr().err


def test_targets_flag_limits_the_load(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")
    _program(tmp_path, "Child", "Base")

    assert main(["project", str(tmp_path), "--targets", "Child"]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "programs: 2" in out
    assert "Child" in out


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as a non-root user")
def test_an_unreadable_body_is_a_finding_not_an_internal_error(tmp_path, capsys) -> None:
    _program(tmp_path, "Broken")
    (tmp_path / "Broken.s").chmod(0)

    assert main(["project", str(tmp_path), "--json"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["rule"] == "PROJECT_LOAD_ERROR"


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


def test_unknown_of_is_a_finding(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")

    assert main(["project", str(tmp_path), "--graph", "--of", "Nope"]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "not in the loaded graph" in out

    assert main(["project", str(tmp_path), "--graph", "--of", "Nope", "--json"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["rule"] == "PROJECT_QUERY_ERROR"


def test_graph_mode_prints_and_reports_validation_findings(tmp_path, capsys) -> None:
    write_source(tmp_path, "Faulty.s", CONSECUTIVE_STEPS_SOURCE)

    assert main(["project", str(tmp_path), "--graph"]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "validation:" in out
    assert "SL-V016" in out

    assert main(["project", str(tmp_path), "--graph", "--json"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["validation"][0]["code"] == "SL-V016"


def test_dependency_cycle_is_a_load_error(tmp_path, capsys) -> None:
    _program(tmp_path, "Alpha", "Beta")
    _program(tmp_path, "Beta", "Alpha")

    assert main(["project", str(tmp_path)]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "cannot load project" in out
    assert "dependency cycle: alpha -> beta -> alpha" in out

    assert main(["project", str(tmp_path), "--json"]) == ExitCode.FINDINGS
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["severity"] == "error"
    assert "dependency cycle: alpha -> beta -> alpha" in payload["findings"][0]["message"]

    assert main(["project", str(tmp_path), "--cycles"]) == ExitCode.USAGE


_RECURSIVE_MODULE_TYPE_SOURCE = """\
"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: Loop"

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1
TYPEDEFINITIONS
   LoopType = MODULEDEFINITION DateCode_ 1
   LOCALVARIABLES
      Value: integer := 0;
   SUBMODULES
      Child Invocation
         ( 0.0 , 0.0 , 0.0 , 0.4 , 0.4
          ) : LoopType;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*LoopType*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""


def test_moduletype_cycle_is_a_load_error(tmp_path, capsys) -> None:
    (tmp_path / "Loop.s").write_text(_RECURSIVE_MODULE_TYPE_SOURCE, encoding="utf-8")

    assert main(["project", str(tmp_path)]) == ExitCode.FINDINGS
    out = capsys.readouterr().out
    assert "cannot load project" in out
    assert "module type instantiates itself recursively: LoopType -> LoopType" in out


def test_bad_depth_is_a_usage_error(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")

    assert main(["project", str(tmp_path), "--depth", "zero"]) == ExitCode.USAGE
    assert "expected an integer" in capsys.readouterr().err

    assert main(["project", str(tmp_path), "--depth", "0"]) == ExitCode.USAGE
    assert "must be 1 or greater" in capsys.readouterr().err


def test_cycles_reports_each_elementary_cycle_once() -> None:
    edges = [("a", "b"), ("b", "a"), ("b", "c"), ("c", "b"), ("c", "d")]

    assert _cycles(edges) == [["a", "b"], ["b", "c"]]


def test_cycles_ignores_a_dag_with_many_converging_paths() -> None:
    """Cycle search is limited to cyclic components, so path count is irrelevant.

    This layered graph has two nodes per layer and every node wired to both
    nodes of the next layer: 2 ** 39 paths and not one cycle.
    """
    edges: list[tuple[str, str]] = []
    for layer in range(39):
        for source in ("a", "b"):
            for target in ("a", "b"):
                edges.append((f"n{layer}{source}", f"n{layer + 1}{target}"))

    assert _cycles(edges) == []


def test_cycles_reports_a_self_loop() -> None:
    assert _cycles([("a", "a")]) == [["a"]]


def test_cycles_preserves_edge_order_instead_of_sorting_members() -> None:
    assert _cycles([("z", "m"), ("m", "a"), ("a", "z")]) == [["a", "z", "m"]]


def test_cycles_keeps_opposite_orderings_with_the_same_members_apart() -> None:
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("a", "c"), ("c", "b"), ("b", "a")]

    assert _cycles(edges) == [
        ["a", "b"],
        ["a", "b", "c"],
        ["a", "c"],
        ["a", "c", "b"],
        ["b", "c"],
    ]


def test_cache_flags(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")
    _program(tmp_path, "Child", "Base")
    explicit = tmp_path / "explicit-cache"

    default_cache = project_cmd._default_cache_dir()
    assert default_cache is not None

    assert main(["project", str(tmp_path), "--no-cache"]) == ExitCode.OK
    assert "programs: 2" in capsys.readouterr().out
    assert not default_cache.exists()

    assert main(["project", str(tmp_path), "--cache-dir", str(explicit), "--workers", "1"]) == ExitCode.OK
    assert "programs: 2" in capsys.readouterr().out
    assert any(explicit.rglob("*"))


def test_default_cache_dir_is_the_xdg_cache(tmp_path, capsys, monkeypatch) -> None:
    _program(tmp_path, "Base")
    cache_home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))

    assert main(["project", str(tmp_path)]) == ExitCode.OK
    assert "programs: 1" in capsys.readouterr().out
    default_cache = project_cmd._default_cache_dir()
    assert default_cache == cache_home / "sattline-parser" / "project"
    assert default_cache is not None
    assert any(default_cache.rglob("*"))


def test_workers_flag_defaults_to_cpu_count_capped(monkeypatch) -> None:
    monkeypatch.setattr(project_cmd.os, "cpu_count", lambda: 2)
    assert project_cmd._default_workers() == 2
    monkeypatch.setattr(project_cmd.os, "cpu_count", lambda: 64)
    assert project_cmd._default_workers() == project_cmd._MAX_DEFAULT_WORKERS
    monkeypatch.setattr(project_cmd.os, "cpu_count", lambda: None)
    assert project_cmd._default_workers() == 1


def test_workers_flag_rejects_a_count_past_the_cap(tmp_path, capsys) -> None:
    _program(tmp_path, "Base")

    assert main(["project", str(tmp_path), "--workers", "1000"]) == ExitCode.USAGE
    assert "or less" in capsys.readouterr().err


def test_two_roots_with_a_shared_unit_name_use_the_first_root(tmp_path, capsys) -> None:
    """The earlier root wins; the later body is not loaded and not reported."""
    first = tmp_path / "r1"
    second = tmp_path / "r2"
    first.mkdir()
    second.mkdir()
    _program(first, "Util")
    _program(second, "Util")
    _program(first, "Main1", "Util")
    _program(second, "Main2", "Util")

    assert main(["project", str(first), str(second), "--json"]) == ExitCode.OK

    payload = json.loads(capsys.readouterr().out)
    kinds = [row["kind"] for row in payload["diagnostics"]]
    assert "name-resolution-conflict" not in kinds
    util = next(row for row in payload["programs"] if row["name"] == "Util")
    assert util["resolved_base"] == str(first.resolve())
