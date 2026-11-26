"""Tests for the project-wide definition and usage index."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import cast

import pytest

from sattline_parser import parse_source_text
from sattline_parser.models.ast_model import BasePicture, Variable
from sattline_parser.models.freeze import freeze_ast
from sattline_parser.models.walk import WalkEvent
from sattline_parser.project import LoadMode, ProjectIndex, SattLineProgram, SattLineProject, SymbolKind
from sattline_parser.project import index as index_module

from ._support import write_file

_SOURCE = """\
"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: SimpleModuleTypeInv"

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   PumpType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      Speed: real;
   LOCALVARIABLES
      Running: boolean  := False;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK Eq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Running = Speed > 0.0;
   ENDDEF (*PumpType*);

LOCALVARIABLES
   SpeedRef: real  := 50.0;

SUBMODULES
   Pump Invocation
      ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5
       ) : PumpType (
      Speed => SpeedRef);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""


def _project() -> SattLineProject:
    program = SattLineProgram(name="SimpleModuleTypeInv", code=parse_source_text(_SOURCE))
    return SattLineProject.from_programs({"SimpleModuleTypeInv": program})


_ALIAS_MAIN_SOURCE = """\
"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: Main"

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   SpeedRef: real  := 50.0;

SUBMODULES
   Pump Invocation
      ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5
       ) : PumpType (
      Speed => SpeedRef);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""

_PLAIN_SOURCE = """\
"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: Plain"

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""


def test_index_reports_who_defines_a_module_type() -> None:
    project = _project()

    sites = project.index.definitions_of("pumptype")

    assert len(sites) == 1
    assert sites[0].kind is SymbolKind.MODULETYPE
    assert sites[0].program == "SimpleModuleTypeInv"
    assert sites[0].span is not None


def test_index_reports_who_uses_a_module_type() -> None:
    project = _project()

    sites = project.index.usages_of("PumpType")

    assert [site.kind for site in sites] == [SymbolKind.MODULETYPE]
    assert sites[0].program == "SimpleModuleTypeInv"


def test_index_reports_variable_definitions_and_uses() -> None:
    project = _project()

    definitions = project.index.definitions_of("SpeedRef")
    uses = project.index.usages_of("SpeedRef")

    assert [site.kind for site in definitions] == [SymbolKind.VARIABLE]
    assert uses
    assert all(site.kind is SymbolKind.VARIABLE for site in uses)


def test_index_reports_the_program_itself() -> None:
    project = _project()

    sites = project.index.definitions_of("simplemoduletypeinv")

    assert [site.kind for site in sites] == [SymbolKind.PROGRAM]


def test_index_is_case_insensitive_and_empty_for_an_unknown_name() -> None:
    project = _project()

    assert project.index.definitions_of("PUMPTYPE") == project.index.definitions_of("pumptype")
    assert project.index.usages_of("Nope") == ()
    assert project.index.definitions_of("Nope") == ()


def test_index_is_built_once_per_project() -> None:
    project = _project()

    assert project.index is project.index
    assert isinstance(project.index, ProjectIndex)
    assert "PumpType" in project.index.defined_names()


def test_index_filters_definitions_and_usages_by_kind() -> None:
    project = _project()

    assert [site.kind for site in project.index.definitions_of("PumpType", kind=SymbolKind.MODULETYPE)] == [
        SymbolKind.MODULETYPE
    ]
    assert project.index.definitions_of("PumpType", kind=SymbolKind.VARIABLE) == ()
    assert [site.kind for site in project.index.usages_of("PumpType", kind=SymbolKind.MODULETYPE)] == [
        SymbolKind.MODULETYPE
    ]
    assert project.index.usages_of("PumpType", kind=SymbolKind.VARIABLE) == ()
    moduletypes = project.index.defined_names(kind=SymbolKind.MODULETYPE)
    assert "PumpType" in moduletypes
    assert "SimpleModuleTypeInv" not in moduletypes


def test_project_reports_invoked_moduletypes() -> None:
    project = _project()

    assert project.invoked_moduletypes()["simplemoduletypeinv"] == frozenset({"PUMPTYPE"})
    assert project.invoked_moduletypes(("SimpleModuleTypeInv",))["simplemoduletypeinv"] == frozenset({"PUMPTYPE"})


def test_project_reports_an_empty_set_for_a_target_that_invokes_nothing(tmp_path: Path) -> None:
    write_file(tmp_path, "Plain.s", _PLAIN_SOURCE)
    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Plain"])

    assert project.invoked_moduletypes(("Plain",))["plain"] == frozenset()
    assert project.invoked_moduletypes(("Missing",)) == {}


def test_project_invoked_moduletypes_follows_a_resolved_alias_dependency(tmp_path: Path) -> None:
    write_file(tmp_path, "Base.s", _SOURCE)
    try:
        (tmp_path / "AliasBase.s").symlink_to(tmp_path / "Base.s")
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem cannot create a symlink")
    write_file(tmp_path, "Main.s", _ALIAS_MAIN_SOURCE)
    write_file(tmp_path, "Main.l", "AliasBase\n")

    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ("Base", "Main"))

    assert project.dependencies_of("Main") == ("AliasBase",)
    reachable = project.invoked_moduletypes(("Main",))
    assert reachable["base"] == frozenset({"PUMPTYPE"})
    assert reachable["main"] == frozenset()


def test_project_invoked_moduletypes_walks_a_diamond_once() -> None:
    project = SattLineProject.from_programs(
        {
            "Main": SattLineProgram(
                name="Main", code=parse_source_text(_ALIAS_MAIN_SOURCE), dependencies=("Left", "Right")
            ),
            "Left": SattLineProgram(name="Left", code=parse_source_text(_PLAIN_SOURCE), dependencies=("Base",)),
            "Right": SattLineProgram(name="Right", code=parse_source_text(_PLAIN_SOURCE), dependencies=("Base",)),
            "Base": SattLineProgram(name="Base", code=parse_source_text(_SOURCE)),
        }
    )

    assert project.invoked_moduletypes(("Main",))["base"] == frozenset({"PUMPTYPE"})


def test_index_walks_each_ast_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Definitions and usages come out of one traversal, not one each."""
    calls: list[int] = []
    real_walk = index_module.walk

    def counting(node: BasePicture) -> Iterator[WalkEvent]:
        calls.append(1)
        return real_walk(node)

    monkeypatch.setattr(index_module, "walk", counting)
    project = _project()

    assert project.index.usages_of("PumpType")
    assert len(calls) == 1


def test_attached_ast_is_frozen() -> None:
    project = _project()
    code = project.get("SimpleModuleTypeInv").code

    with pytest.raises(FrozenInstanceError):
        code.localvariables[0].name = "RenamedVariable"
    with pytest.raises(AttributeError):
        code.localvariables.append(code.localvariables[0])
    with pytest.raises(FrozenInstanceError):
        del code.localvariables


def test_freeze_ast_converts_containers() -> None:
    frozen = cast("Mapping[str, object]", freeze_ast({"items": [1, 2]}))

    assert frozen["items"] == (1, 2)
    with pytest.raises(TypeError):
        cast("dict[str, object]", frozen)["other"] = 3


def test_an_unfrozen_node_still_allows_attribute_deletion() -> None:
    variable = Variable(name="X", datatype="integer")

    del variable.name

    assert not hasattr(variable, "name")


def test_index_cannot_go_stale_after_a_rejected_mutation() -> None:
    project = _project()
    before = project.index.definitions_of("SpeedRef")

    with pytest.raises(FrozenInstanceError):
        project.get("SimpleModuleTypeInv").code.localvariables[0].name = "RenamedVariable"

    assert project.index.definitions_of("SpeedRef") == before
    assert project.index.definitions_of("RenamedVariable") == ()


def test_from_programs_does_not_freeze_the_callers_ast() -> None:
    source = parse_source_text(_SOURCE)
    project = SattLineProject.from_programs(
        {"SimpleModuleTypeInv": SattLineProgram(name="SimpleModuleTypeInv", code=source)}
    )

    source.localvariables[0].name = "CallerOwned"
    assert project.get("SimpleModuleTypeInv").code.localvariables[0].name == "SpeedRef"


def test_load_returns_a_frozen_tree(tmp_path: Path) -> None:
    write_file(tmp_path, "SimpleModuleTypeInv.s", _SOURCE)
    project = SattLineProject.load([tmp_path], mode=LoadMode.DRAFT, targets=["SimpleModuleTypeInv"])

    with pytest.raises(FrozenInstanceError):
        project.get("SimpleModuleTypeInv").code.localvariables[0].name = "RenamedVariable"


def test_index_covers_a_loaded_project(tmp_path: Path) -> None:
    source = write_file(tmp_path, "SimpleModuleTypeInv.s", _SOURCE)

    project = SattLineProject.load(
        [tmp_path],
        mode=LoadMode.DRAFT,
        targets=["SimpleModuleTypeInv"],
    )

    assert source.exists()
    assert project.index.usages_of("PumpType")


_RECORD_SOURCE = """\
"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: IndexedRecord"

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   Reading = RECORD DateCode_ 1
      Field: integer;
   ENDDEF (*Reading*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""


def test_index_reports_a_datatype_definition() -> None:
    program = SattLineProgram(name="IndexedRecord", code=parse_source_text(_RECORD_SOURCE))
    project = SattLineProject.from_programs({"IndexedRecord": program})

    sites = project.index.definitions_of("reading")

    assert [site.kind for site in sites] == [SymbolKind.DATATYPE]
    assert project.index.definitions_of("Field")
