"""Partial-success multi-target loading (``SattLineProject.load_many``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sattline_parser.api import parse_source_bytes
from sattline_parser.models.ast_model import BasePicture
from sattline_parser.project import (
    ArtifactLoadError,
    DependencyCycleError,
    DependencyNotFoundError,
    LoadMode,
    LoadValidation,
    ModuleTypeCycleError,
    ProjectLoader,
    ProjectLoadError,
    SattLineProject,
    TargetLoadResult,
)
from sattline_parser.project import executor as executor_module

from ._support import write_file

_HEADER = """\"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N\"
\"Original file date: ---\"
\"Program date: 2026-04-23-12:00:00.000, name: {name}\"
"""

_CODE = (
    _HEADER.format(name="Prog")
    + """
BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""
)

_BROKEN = "this is not a SattLine program at all $$$"


def _source(
    name: str,
    *,
    typedefs: str = "",
    locals_block: str = "",
    body: str = "",
) -> str:
    return (
        _HEADER.format(name=name)
        + f"""
BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1
{typedefs}{locals_block}{body}
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""
    )


_LOOP_TYPEDEFS = """TYPEDEFINITIONS
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
"""

_LOOP = (
    _HEADER.format(name="Loop")
    + """
BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1
"""
    + _LOOP_TYPEDEFS
    + """
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""
)


def _load_many(
    root: Path,
    targets: tuple[str, ...],
    *,
    validate: LoadValidation | None = None,
) -> dict[str, TargetLoadResult]:
    kwargs: dict[str, Any] = {}
    if validate is not None:
        kwargs["validate"] = validate
    return SattLineProject.load_many([root], LoadMode.DRAFT, targets, **kwargs)


def test_load_many_keeps_successful_targets_beside_a_broken_one(tmp_path: Path) -> None:
    write_file(tmp_path, "Healthy.s", _CODE)
    write_file(tmp_path, "Broken.s", _BROKEN)
    write_file(tmp_path, "Other.s", _CODE)

    results = _load_many(tmp_path, ("Healthy", "Broken", "Other"))

    assert set(results) == {"Healthy", "Broken", "Other"}
    assert results["Healthy"].ok
    assert results["Healthy"].project is not None
    assert results["Healthy"].error is None
    assert results["Broken"].project is None
    assert isinstance(results["Broken"].error, ArtifactLoadError)
    assert results["Other"].ok


def test_load_many_shares_a_dependency_and_parses_it_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_file(tmp_path, "A.s", _CODE)
    write_file(tmp_path, "A.l", "Shared\n")
    write_file(tmp_path, "B.s", _CODE)
    write_file(tmp_path, "B.l", "Shared\n")
    write_file(tmp_path, "Shared.s", _CODE)

    seen: list[str] = []

    def counting_parse(raw_bytes: bytes, **kwargs: object) -> BasePicture:
        source_path = kwargs.get("source_path")
        assert isinstance(source_path, Path)
        seen.append(source_path.name)
        return parse_source_bytes(raw_bytes)

    monkeypatch.setattr(executor_module, "parse_source_bytes", counting_parse)

    results = _load_many(tmp_path, ("A", "B"))

    assert results["A"].project is not None
    assert results["B"].project is not None
    assert seen.count("Shared.s") == 1
    assert set(results["A"].project.programs()) == {"a", "shared"}
    assert set(results["B"].project.programs()) == {"b", "shared"}


def test_load_many_reports_a_missing_dependency_against_its_target(tmp_path: Path) -> None:
    write_file(tmp_path, "Good.s", _CODE)
    write_file(tmp_path, "Missing.s", _CODE)
    write_file(tmp_path, "Missing.l", "Ghost\n")

    results = _load_many(tmp_path, ("Good", "Missing"))

    assert results["Good"].ok
    assert isinstance(results["Missing"].error, DependencyNotFoundError)


def test_load_many_reports_a_cycle_against_its_target(tmp_path: Path) -> None:
    write_file(tmp_path, "Good.s", _CODE)
    write_file(tmp_path, "Alpha.s", _CODE)
    write_file(tmp_path, "Alpha.l", "Beta\n")
    write_file(tmp_path, "Beta.s", _CODE)
    write_file(tmp_path, "Beta.l", "Alpha\n")

    results = _load_many(tmp_path, ("Good", "Alpha"))

    assert results["Good"].ok
    assert isinstance(results["Alpha"].error, DependencyCycleError)


def test_load_many_propagates_a_dependency_assembly_failure(tmp_path: Path) -> None:
    write_file(tmp_path, "Good.s", _CODE)
    write_file(tmp_path, "BadDep.s", _CODE)
    write_file(tmp_path, "BadDep.p", "DistributionData ( ) SourceCodeSystems ( ) ExecutingSystems ( )")
    write_file(tmp_path, "Consumer.s", _CODE)
    write_file(tmp_path, "Consumer.l", "BadDep\n")

    results = _load_many(tmp_path, ("Good", "BadDep", "Consumer"))

    assert results["Good"].ok
    assert isinstance(results["BadDep"].error, ArtifactLoadError)
    assert results["Consumer"].error is results["BadDep"].error


def test_load_many_keeps_a_module_type_cycle_inside_its_target(tmp_path: Path) -> None:
    write_file(tmp_path, "Good.s", _CODE)
    write_file(tmp_path, "Loop.s", _LOOP)

    results = _load_many(tmp_path, ("Good", "Loop"))

    assert results["Good"].ok
    assert isinstance(results["Loop"].error, ModuleTypeCycleError)


def test_load_many_scopes_diagnostics_to_each_target(tmp_path: Path) -> None:
    write_file(tmp_path, "Alpha.s", _CODE)
    write_file(tmp_path, "Beta.s", _CODE)

    results = _load_many(tmp_path, ("Alpha", "Beta"))

    assert results["Alpha"].project is not None
    assert results["Beta"].project is not None
    assert {diagnostic.program for diagnostic in results["Alpha"].project.diagnostics()} == {"Alpha"}
    assert {diagnostic.program for diagnostic in results["Beta"].project.diagnostics()} == {"Beta"}


def test_load_many_keeps_a_skipped_file_finding_for_every_target(tmp_path: Path) -> None:
    write_file(tmp_path, "Alpha.s", _CODE)
    write_file(tmp_path, "Pump.v2.s", _CODE)

    results = _load_many(tmp_path, ("Alpha",))

    assert results["Alpha"].project is not None
    kinds = {diagnostic.kind.value for diagnostic in results["Alpha"].project.diagnostics()}
    assert "skipped-file" in kinds


@pytest.mark.parametrize("validate", list(LoadValidation))
def test_load_many_applies_each_validation_scope(tmp_path: Path, validate: LoadValidation) -> None:
    write_file(tmp_path, "Alpha.s", _CODE)

    results = _load_many(tmp_path, ("Alpha",), validate=validate)

    assert results["Alpha"].project is not None
    assert results["Alpha"].project.get("Alpha").diagnostics == ()


def test_load_many_reports_a_bad_root_for_every_target(tmp_path: Path) -> None:
    results = _load_many(tmp_path / "missing", ("A", "B"))

    assert set(results) == {"A", "B"}
    assert isinstance(results["A"].error, ProjectLoadError)
    assert results["B"].project is None


def test_load_many_with_no_targets_returns_nothing(tmp_path: Path) -> None:
    assert _load_many(tmp_path, ()) == {}


def test_load_many_handles_a_diamond_inside_one_target(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Left\nRight\n")
    write_file(tmp_path, "Left.s", _CODE)
    write_file(tmp_path, "Left.l", "Base\n")
    write_file(tmp_path, "Right.s", _CODE)
    write_file(tmp_path, "Right.l", "Base\n")
    write_file(tmp_path, "Base.s", _CODE)

    results = _load_many(tmp_path, ("Main",))

    assert results["Main"].project is not None
    assert set(results["Main"].project.programs()) == {"main", "left", "right", "base"}


def test_load_many_replans_a_rolled_back_body_for_a_later_target(tmp_path: Path) -> None:
    write_file(tmp_path, "Alpha.s", _CODE)
    write_file(tmp_path, "Alpha.l", "Ghost\n")
    write_file(tmp_path, "Beta.s", _CODE)
    write_file(tmp_path, "Beta.l", "Alpha\n")

    results = _load_many(tmp_path, ("Alpha", "Beta"))

    assert isinstance(results["Alpha"].error, DependencyNotFoundError)
    assert isinstance(results["Beta"].error, DependencyNotFoundError)


def test_load_many_reuses_a_closed_dependency_after_a_sibling_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path, "Alpha.s", _CODE)
    write_file(tmp_path, "Alpha.l", "Shared\nGhost\n")
    write_file(tmp_path, "Beta.s", _CODE)
    write_file(tmp_path, "Beta.l", "Shared\n")
    write_file(tmp_path, "Shared.s", _CODE)

    seen: list[str] = []

    def counting_parse(raw_bytes: bytes, **kwargs: object) -> BasePicture:
        source_path = kwargs.get("source_path")
        assert isinstance(source_path, Path)
        seen.append(source_path.name)
        return parse_source_bytes(raw_bytes)

    monkeypatch.setattr(executor_module, "parse_source_bytes", counting_parse)

    results = _load_many(tmp_path, ("Alpha", "Beta"))

    assert isinstance(results["Alpha"].error, DependencyNotFoundError)
    assert results["Beta"].project is not None
    assert "Shared" in results["Beta"].project
    assert seen.count("Shared.s") == 1


@pytest.mark.parametrize("validate", list(LoadValidation))
def test_load_many_matches_load_validation_findings(tmp_path: Path, validate: LoadValidation) -> None:
    library_types = (
        "TYPEDEFINITIONS\n"
        "   Shared = RECORD DateCode_ 1\n      Value: integer;\n   ENDDEF (*Shared*);\n"
        "   Shared = RECORD DateCode_ 2\n      Value: integer;\n   ENDDEF (*Shared*);\n"
        "TYPEDEFINITIONS\n"
        "   UsedType = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n      Value: integer;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ModuleCode\n"
        "   EQUATIONBLOCK Eq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "      Value = MissingUsed;\n"
        "   ENDDEF (*UsedType*);\n"
    )
    main_types = (
        "TYPEDEFINITIONS\n"
        "   MainRec = RECORD DateCode_ 1\n      Value: integer;\n   ENDDEF (*MainRec*);\n"
        "   MainRec = RECORD DateCode_ 2\n      Value: integer;\n   ENDDEF (*MainRec*);\n"
    )
    body = "SUBMODULES\n   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : UsedType;\n"
    write_file(tmp_path, "Lib.s", _source("Lib", typedefs=library_types))
    write_file(tmp_path, "Main.s", _source("Main", typedefs=main_types, body=body))
    write_file(tmp_path, "Main.l", "Lib\n")

    loaded = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Main"], validate=validate)
    many = _load_many(tmp_path, ("Main",), validate=validate)["Main"].project
    assert many is not None
    assert set(many.programs()) == set(loaded.programs())
    for key, program in loaded.programs().items():
        assert many.programs()[key].diagnostics == program.diagnostics

    messages = " ".join(
        diagnostic.message for program in many.programs().values() for diagnostic in program.diagnostics
    )
    codes = {diagnostic.code.value for program in many.programs().values() for diagnostic in program.diagnostics}
    if validate is LoadValidation.NONE:
        assert "MissingUsed" not in messages
        assert "SL-V057" not in codes
    else:
        assert "MissingUsed" in messages
        assert "SL-V057" in codes


def test_load_many_flushes_the_lookup_cache(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    cache_dir = tmp_path / "cache"

    results = SattLineProject.load_many([tmp_path], LoadMode.DRAFT, ["Main"], cache_dir=cache_dir)

    assert results["Main"].project is not None
    assert (cache_dir / "file_lookup_cache.json").exists()


def test_resolve_many_refuses_a_second_resolve(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    loader = ProjectLoader(
        roots=[tmp_path],
        mode=LoadMode.DRAFT,
        debug=None,
        cache_dir=None,
        defer_validation=True,
    )
    loader.resolve_many(("Main",))

    with pytest.raises(RuntimeError, match="already resolved"):
        loader.resolve_many(("Main",))


def test_resolve_many_requires_deferred_validation(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    loader = ProjectLoader(roots=[tmp_path], mode=LoadMode.DRAFT, debug=None, cache_dir=None)

    with pytest.raises(RuntimeError, match="defer_validation=True"):
        loader.resolve_many(("Main",))


def test_resolve_rejects_deferred_validation(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    loader = ProjectLoader(
        roots=[tmp_path],
        mode=LoadMode.DRAFT,
        debug=None,
        cache_dir=None,
        defer_validation=True,
    )

    with pytest.raises(RuntimeError, match="defers validation"):
        loader.resolve(("Main",))


def test_target_load_result_exposes_ok() -> None:
    assert TargetLoadResult(target="A", error=ProjectLoadError("A", "boom")).ok is False
