# pyright: reportPrivateUsage=false
"""Phase C: project load validation, provenance, datecodes, and cycles."""

from __future__ import annotations

from pathlib import Path

import pytest

from sattline_parser.api import parse_source_text
from sattline_parser.project import LoadMode, LoadValidation, SattLineProject
from sattline_parser.project.loader import ProjectLoader
from sattline_parser.project.models import SattLineProgram

_HEADER = """\"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N\"
\"Original file date: ---\"
\"Program date: 2026-04-23-12:00:00.000, name: {name}\"
"""


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


def _write(root: Path, rel: str, content: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _load(root: Path, target: str, **kwargs: object) -> SattLineProject:
    return SattLineProject.load(
        [root],
        mode=LoadMode.DRAFT,
        targets=(target,),
        **kwargs,  # type: ignore[arg-type]
    )


def test_load_populates_library_resolved_base_and_origin(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    _write(root, "Main.s", _source("Main"))
    project = _load(root, "Main")
    program = project.get("Main")
    assert program.library == "libs"
    assert program.resolved_base == root.resolve()
    assert program.code.origin_file == "Main.s"
    assert program.code.origin_lib == "libs"
    assert project.libraries() == ("libs",)


def test_load_reports_local_validation_findings(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    _write(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Bad: NotAType;\n"))
    program = _load(root, "Main").get("Main")
    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V020"]
    assert program.diagnostics[0].tentative is False


def test_load_with_validation_none_reports_nothing(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    _write(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Bad: NotAType;\n"))
    program = _load(root, "Main", validate=LoadValidation.NONE).get("Main")
    assert program.diagnostics == ()


def test_external_datatypes_are_visible_to_dependents(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    _write(
        root,
        "Dep.s",
        _source(
            "Dep",
            typedefs=(
                "TYPEDEFINITIONS\n"
                "   SensorType = RECORD DateCode_ 1\n"
                "      RawValue: real := 0.0;\n"
                "      Valid: boolean := False;\n"
                "   ENDDEF\n"
                "    (*SensorType*);\n"
            ),
        ),
    )
    _write(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Sensor: SensorType;\n"))
    _write(root, "Main.l", "Dep\n")
    program = _load(root, "Main").get("Main")
    assert program.diagnostics == ()


def test_instance_may_omit_every_parameter_mapping(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    moduletype = (
        "TYPEDEFINITIONS\n"
        "   ControllerType = MODULEDEFINITION DateCode_ 1\n"
        "   MODULEPARAMETERS\n"
        "      Setpoint: real := 0.0;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*ControllerType*);\n"
    )
    body = "SUBMODULES\n   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ControllerType;\n"
    _write(root, "Main.s", _source("Main", typedefs=moduletype, body=body))
    program = _load(root, "Main").get("Main")
    assert program.diagnostics == ()


def test_external_typedef_parameter_mapping_target_is_checked(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    records = "TYPEDEFINITIONS\n   RecType = RECORD DateCode_ 1\n      Value: integer := 0;\n   ENDDEF (*RecType*);\n"
    moduletype = (
        "TYPEDEFINITIONS\n"
        "   ChildType = MODULEDEFINITION DateCode_ 1\n"
        "   MODULEPARAMETERS\n"
        "      Param: RecType;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*ChildType*);\n"
    )
    _write(root, "Dep.s", _source("Dep", typedefs=records + moduletype))
    body = (
        "SUBMODULES\n"
        "   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ChildType (\n"
        '      Param.Value => "not an integer");\n'
    )
    _write(root, "Main.s", _source("Main", body=body))
    _write(root, "Main.l", "Dep\n")
    diagnostics = _load(root, "Main").get("Main").diagnostics
    assert [diagnostic.code.value for diagnostic in diagnostics] == ["SL-V050"]
    assert "Param.Value" in diagnostics[0].message


def test_external_record_fields_belong_to_the_defining_program(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    broken_record = (
        "TYPEDEFINITIONS\n"
        "   BrokenRecord = RECORD DateCode_ 1\n"
        "      BadField: MissingFieldType := 0;\n"
        "   ENDDEF (*BrokenRecord*);\n"
    )
    _write(root, "Dep.s", _source("Dep", typedefs=broken_record))
    _write(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Sensor: BrokenRecord;\n"))
    _write(root, "Main.l", "Dep\n")
    project = _load(root, "Main")
    assert project.get("Main").diagnostics == ()
    assert "MissingFieldType" in " ".join(d.message for d in project.get("Dep").diagnostics)


def test_visible_definitions_come_from_the_dependency_closure(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    hidden_type = (
        "TYPEDEFINITIONS\n   HiddenType = RECORD DateCode_ 1\n      Value: integer := 0;\n   ENDDEF (*HiddenType*);\n"
    )
    _write(root, "Other.s", _source("Other", typedefs=hidden_type))
    _write(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Value: HiddenType;\n"))
    project = SattLineProject.load([root], mode=LoadMode.DRAFT, targets=("Other", "Main"), strict=False)
    assert project.get("Other").diagnostics == ()
    assert [diagnostic.code.value for diagnostic in project.get("Main").diagnostics] == ["SL-V020"]


def test_invoked_validation_limits_dependencies_to_used_moduletypes(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    library_types = (
        "TYPEDEFINITIONS\n"
        "   UsedType = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n"
        "      BadUsed: MissingUsedType;\n"
        "   SUBMODULES\n"
        "      Deep Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : DeepType;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*UsedType*);\n"
        "   UnusedType = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n"
        "      BadUnused: MissingUnusedType;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*UnusedType*);\n"
        "   DeepType = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n"
        "      BadDeep: MissingDeepType;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*DeepType*);\n"
    )
    own_type = (
        "TYPEDEFINITIONS\n"
        "   OwnType = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n"
        "      BadOwn: MissingOwnType;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*OwnType*);\n"
    )
    other_types = (
        "TYPEDEFINITIONS\n"
        "   OnlyUnused = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n"
        "      BadOnlyUnused: MissingOtherType;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*OnlyUnused*);\n"
    )
    body = (
        "SUBMODULES\n"
        "   Used Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : UsedType;\n"
        "   UsedAgain Invocation ( 0.6 , 0.1 , 0.0 , 0.4 , 0.4 ) : UsedType;\n"
    )
    _write(root, "Lib.s", _source("Lib", typedefs=library_types))
    _write(root, "Other.s", _source("Other", typedefs=other_types))
    _write(root, "Main.s", _source("Main", typedefs=own_type, body=body))
    _write(root, "Main.l", "Lib\nOther\n")

    full = _load(root, "Main", validate=LoadValidation.FULL)
    full_library = " ".join(d.message for d in full.get("Lib").diagnostics)
    assert "MissingUsedType" in full_library
    assert "MissingUnusedType" in full_library
    assert "MissingDeepType" in full_library
    assert "MissingOtherType" in " ".join(d.message for d in full.get("Other").diagnostics)

    invoked = _load(root, "Main", validate=LoadValidation.INVOKED)
    invoked_library = " ".join(d.message for d in invoked.get("Lib").diagnostics)
    assert "MissingUsedType" in invoked_library
    assert "MissingDeepType" in invoked_library
    assert "MissingUnusedType" not in invoked_library
    assert invoked.get("Other").diagnostics == ()
    assert "MissingOwnType" in " ".join(d.message for d in invoked.get("Main").diagnostics)


def test_missing_dependency_marks_external_findings_tentative(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    _write(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Bad: NotAType;\n"))
    _write(root, "Main.l", "Missing\n")
    project = _load(root, "Main", strict=False)
    program = project.get("Main")
    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V020"]
    assert program.diagnostics[0].tentative is True

    invoked = _load(root, "Main", strict=False, validate=LoadValidation.INVOKED).get("Main")
    assert [diagnostic.code.value for diagnostic in invoked.diagnostics] == ["SL-V020"]
    assert invoked.diagnostics[0].tentative is True


def test_datecode_conflict_is_reported_on_the_later_program(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    moduletype = (
        "TYPEDEFINITIONS\n"
        "   ControllerType = MODULEDEFINITION DateCode_ {datecode}\n"
        "   MODULEPARAMETERS\n"
        "      Setpoint: real := 0.0;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*ControllerType*);\n"
    )
    _write(root, "Dep.s", _source("Dep", typedefs=moduletype.format(datecode=1)))
    _write(root, "Main.s", _source("Main", typedefs=moduletype.format(datecode=2)))
    _write(root, "Main.l", "Dep\n")
    program = _load(root, "Main").get("Main")
    conflicts = [diagnostic for diagnostic in program.diagnostics if diagnostic.code.value == "SL-V057"]
    assert len(conflicts) == 1
    assert "libs/Main.s" in conflicts[0].message
    assert "1 in libs/Dep.s" in conflicts[0].message


def test_cycles_are_returned_as_paths(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    _write(root, "A.s", _source("A"))
    _write(root, "B.s", _source("B"))
    _write(root, "A.l", "B\n")
    _write(root, "B.l", "A\n")
    project = _load(root, "A")
    assert project.cycles() == (("a", "b", "a"),)


def test_libraries_reports_every_resolving_root(tmp_path: Path) -> None:
    first = tmp_path / "lib_a"
    second = tmp_path / "lib_b"
    first.mkdir()
    second.mkdir()
    _write(first, "A.s", _source("A"))
    _write(second, "B.s", _source("B"))
    project = SattLineProject.load([first, second], mode=LoadMode.DRAFT, targets=("A", "B"))
    assert project.libraries() == ("lib_a", "lib_b")


def test_datatype_datecode_conflict_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    datatype = (
        "TYPEDEFINITIONS\n"
        "   SensorType = RECORD DateCode_ {datecode}\n"
        "      RawValue: real := 0.0;\n"
        "      Valid: boolean := False;\n"
        "   ENDDEF\n"
        "    (*SensorType*);\n"
    )
    _write(root, "Dep.s", _source("Dep", typedefs=datatype.format(datecode=1)))
    _write(root, "Main.s", _source("Main", typedefs=datatype.format(datecode=2)))
    _write(root, "Main.l", "Dep\n")
    program = _load(root, "Main").get("Main")
    conflicts = [diagnostic for diagnostic in program.diagnostics if diagnostic.code.value == "SL-V057"]
    assert len(conflicts) == 1
    assert "datatype 'SensorType'" in conflicts[0].message


def test_registry_post_order_assertion_catches_a_consumer_first(tmp_path: Path) -> None:
    loader = ProjectLoader(roots=[tmp_path], mode=LoadMode.DRAFT, strict=True, debug=None, cache_dir=None)
    consumer = parse_source_text(_source("A"))
    dependency = parse_source_text(_source("B"))
    loader._registry["a"] = SattLineProgram(name="A", code=consumer, dependencies=("B",))
    loader._registry["b"] = SattLineProgram(name="B", code=dependency)
    with pytest.raises(RuntimeError, match="not in post-order"):
        loader._assert_registry_post_order()


def test_cycles_fall_back_to_edges_for_directly_built_projects() -> None:
    code = parse_source_text(_source("X"))
    a = SattLineProgram(name="A", code=code, dependencies=("B",))
    b = SattLineProgram(name="B", code=code, dependencies=("A",))
    project = SattLineProject._from_programs({"A": a, "B": b})
    assert project.cycles() == (("a", "b", "a"),)


def test_cycles_fall_back_reports_no_cycle_for_a_dag() -> None:
    code = parse_source_text(_source("X"))
    a = SattLineProgram(name="A", code=code, dependencies=("B",))
    b = SattLineProgram(name="B", code=code)
    project = SattLineProject._from_programs({"A": a, "B": b})
    assert project.cycles() == ()
