# pyright: reportPrivateUsage=false
"""Phase C: project load validation, provenance, datecodes, and cycles."""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

from sattline_parser.api import parse_source_text
from sattline_parser.project import (
    DependencyCycleError,
    LoadMode,
    LoadValidation,
    ModuleTypeCycleError,
    SattLineProject,
)
from sattline_parser.project._cycles import cycle_key, dependency_cycles, first_cycle
from sattline_parser.project.loader import ProjectLoader
from sattline_parser.project.models import SattLineProgram

from ._support import write_file

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
    write_file(root, "Main.s", _source("Main"))
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
    write_file(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Bad: NotAType;\n"))
    program = _load(root, "Main").get("Main")
    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V020"]
    assert program.diagnostics[0].tentative is False


def test_load_with_validation_none_reports_nothing(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    write_file(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Bad: NotAType;\n"))
    program = _load(root, "Main", validate=LoadValidation.NONE).get("Main")
    assert program.diagnostics == ()


def test_external_datatypes_are_visible_to_dependents(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    write_file(
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
    write_file(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Sensor: SensorType;\n"))
    write_file(root, "Main.l", "Dep\n")
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
    write_file(root, "Main.s", _source("Main", typedefs=moduletype, body=body))
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
    write_file(root, "Dep.s", _source("Dep", typedefs=records + moduletype))
    body = (
        "SUBMODULES\n"
        "   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ChildType (\n"
        '      Param.Value => "not an integer");\n'
    )
    write_file(root, "Main.s", _source("Main", body=body))
    write_file(root, "Main.l", "Dep\n")
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
    write_file(root, "Dep.s", _source("Dep", typedefs=broken_record))
    write_file(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Sensor: BrokenRecord;\n"))
    write_file(root, "Main.l", "Dep\n")
    # Ownership of an external field finding is a FULL-mode property: INVOKED
    # limits a dependency to its invoked module types, and Dep contributes a
    # record datatype only.
    project = _load(root, "Main", validate=LoadValidation.FULL)
    assert project.get("Main").diagnostics == ()
    assert "MissingFieldType" in " ".join(d.message for d in project.get("Dep").diagnostics)

    invoked = _load(root, "Main", validate=LoadValidation.INVOKED)
    assert invoked.get("Main").diagnostics == ()
    assert invoked.get("Dep").diagnostics == ()


def test_visible_definitions_come_from_the_dependency_closure(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    hidden_type = (
        "TYPEDEFINITIONS\n   HiddenType = RECORD DateCode_ 1\n      Value: integer := 0;\n   ENDDEF (*HiddenType*);\n"
    )
    write_file(root, "Other.s", _source("Other", typedefs=hidden_type))
    write_file(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Value: HiddenType;\n"))
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
    write_file(root, "Lib.s", _source("Lib", typedefs=library_types))
    write_file(root, "Other.s", _source("Other", typedefs=other_types))
    write_file(root, "Main.s", _source("Main", typedefs=own_type, body=body))
    write_file(root, "Main.l", "Lib\nOther\n")

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
    write_file(root, "Main.s", _source("Main", locals_block="LOCALVARIABLES\n   Bad: NotAType;\n"))
    write_file(root, "Main.l", "Missing\n")
    project = _load(root, "Main", strict=False)
    program = project.get("Main")
    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V020"]
    assert program.diagnostics[0].tentative is True

    invoked = _load(root, "Main", strict=False, validate=LoadValidation.INVOKED).get("Main")
    assert [diagnostic.code.value for diagnostic in invoked.diagnostics] == ["SL-V020"]
    assert invoked.diagnostics[0].tentative is True

    # FULL marks the same finding tentative through its own code path.
    full = _load(root, "Main", strict=False, validate=LoadValidation.FULL).get("Main")
    assert [diagnostic.code.value for diagnostic in full.diagnostics] == ["SL-V020"]
    assert full.diagnostics[0].tentative is True


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
    write_file(root, "Dep.s", _source("Dep", typedefs=moduletype.format(datecode=1)))
    write_file(root, "Main.s", _source("Main", typedefs=moduletype.format(datecode=2)))
    write_file(root, "Main.l", "Dep\n")
    program = _load(root, "Main").get("Main")
    conflicts = [diagnostic for diagnostic in program.diagnostics if diagnostic.code.value == "SL-V057"]
    assert len(conflicts) == 1
    assert "libs/Main.s" in conflicts[0].message
    assert "1 in libs/Dep.s" in conflicts[0].message


def test_datecode_conflict_names_only_the_differing_version(tmp_path: Path) -> None:
    """A visible version equal to the program's own is not a conflict.

    With versions 1 and 2 both visible, a program declaring 1 conflicts with 2
    and must not report 1 against itself.
    """
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
    write_file(root, "First.s", _source("First", typedefs=moduletype.format(datecode=1)))
    write_file(root, "Second.s", _source("Second", typedefs=moduletype.format(datecode=2)))
    write_file(root, "Main.s", _source("Main", typedefs=moduletype.format(datecode=1)))
    write_file(root, "Main.l", "First\nSecond\n")

    program = _load(root, "Main").get("Main")

    conflicts = [diagnostic for diagnostic in program.diagnostics if diagnostic.code.value == "SL-V057"]
    assert len(conflicts) == 1
    assert "conflicts with 2 in libs/Second.s" in conflicts[0].message
    assert "1 in libs/First.s" not in conflicts[0].message


def test_a_duplicate_datecode_is_not_a_conflict(tmp_path: Path) -> None:
    """Copies of a declaration at the same datecode are the same revision."""
    root = tmp_path / "libs"
    root.mkdir()
    datatype = (
        "TYPEDEFINITIONS\n"
        "   SensorType = RECORD DateCode_ 1\n"
        "      RawValue: real := 0.0;\n"
        "   ENDDEF\n"
        "    (*SensorType*);\n"
    )
    write_file(root, "Dep.s", _source("Dep", typedefs=datatype))
    write_file(root, "Main.s", _source("Main", typedefs=datatype))
    write_file(root, "Main.l", "Dep\n")

    program = _load(root, "Main").get("Main")

    assert [d.code.value for d in program.diagnostics] == []


def test_invoked_validation_stays_inside_the_referencing_closure(tmp_path: Path) -> None:
    """A same-named module type in an unrelated closure is not validated.

    ``Main`` depends on ``A`` and invokes ``SharedType``. ``B`` also defines
    ``SharedType`` but is loaded only through ``Other``, which invokes nothing.
    The reference in ``Main`` must resolve to ``A``, never to ``B``.
    """
    root = tmp_path / "libs"
    root.mkdir()
    body = "SUBMODULES\n   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : SharedType;\n"
    shared = (
        "TYPEDEFINITIONS\n"
        "   SharedType = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n"
        "      {local}: MissingType;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*SharedType*);\n"
    )
    write_file(root, "A.s", _source("A", typedefs=shared.format(local="BadInA")))
    write_file(root, "B.s", _source("B", typedefs=shared.format(local="BadInB")))
    write_file(root, "Main.s", _source("Main", body=body))
    write_file(root, "Main.l", "A\n")
    write_file(root, "Other.s", _source("Other"))
    write_file(root, "Other.l", "B\n")

    project = SattLineProject.load(
        [root],
        mode=LoadMode.DRAFT,
        targets=("Main", "Other"),
        validate=LoadValidation.INVOKED,
    )

    assert project.get("Main").diagnostics == ()
    assert "MissingType" in " ".join(d.message for d in project.get("A").diagnostics)
    assert project.get("B").diagnostics == ()


def test_datecode_conflicts_only_cover_the_program_closure(tmp_path: Path) -> None:
    """A sibling program that the target cannot see is not a conflict.

    Unit libraries load dozens of independent programs that each declare their
    own local module types; those copies must not be compared with each other.
    """
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
    write_file(root, "Unrelated.s", _source("Unrelated", typedefs=moduletype.format(datecode=1)))
    write_file(root, "Dep.s", _source("Dep", typedefs=moduletype.format(datecode=2)))
    write_file(root, "Main.s", _source("Main", typedefs=moduletype.format(datecode=3)))
    write_file(root, "Main.l", "Dep\n")

    # Both targets are loaded into one project; neither may see the other.
    project = SattLineProject.load(
        [root],
        mode=LoadMode.DRAFT,
        targets=("Unrelated", "Main"),
    )
    codes = {
        program.name: [diagnostic.code.value for diagnostic in program.diagnostics]
        for program in project.programs().values()
    }
    assert codes["Unrelated"] == []
    assert codes["Main"] == ["SL-V057"]
    assert "libs/Unrelated.s" not in project.get("Main").diagnostics[0].message


def test_dependency_cycle_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    write_file(root, "A.s", _source("A"))
    write_file(root, "B.s", _source("B"))
    write_file(root, "A.l", "B\n")
    write_file(root, "B.l", "A\n")
    with pytest.raises(DependencyCycleError) as excinfo:
        _load(root, "A")
    assert excinfo.value.cycle == ("a", "b", "a")
    assert "dependency cycle: a -> b -> a" in str(excinfo.value)


def test_dependency_cycle_is_canonical_for_a_three_node_cycle(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    write_file(root, "A.s", _source("A"))
    write_file(root, "B.s", _source("B"))
    write_file(root, "C.s", _source("C"))
    write_file(root, "A.l", "B\n")
    write_file(root, "B.l", "C\n")
    write_file(root, "C.l", "A\n")
    with pytest.raises(DependencyCycleError) as excinfo:
        _load(root, "B")
    assert excinfo.value.cycle == ("a", "b", "c", "a")


def test_dependency_cycle_is_structural_even_when_a_source_is_unparseable(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    write_file(root, "A.s", "not SattLine\n")
    write_file(root, "B.s", "not SattLine\n")
    write_file(root, "A.l", "B\n")
    write_file(root, "B.l", "A\n")

    with pytest.raises(DependencyCycleError):
        SattLineProject.load(
            [root],
            mode=LoadMode.DRAFT,
            targets=("A", "B"),
            strict=False,
            validate=LoadValidation.NONE,
        )


def test_official_sidecar_cycle_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    write_file(root, "A.x", _source("A"))
    write_file(root, "B.x", _source("B"))
    write_file(root, "A.z", "B\n")
    write_file(root, "B.z", "A\n")
    with pytest.raises(DependencyCycleError):
        SattLineProject.load([root], mode=LoadMode.OFFICIAL, targets=("A",))


def _moduletype(name: str, *, instantiates: str | None = None) -> str:
    submodules = ""
    if instantiates is not None:
        submodules = (
            "   SUBMODULES\n"
            "      Child Invocation\n"
            "         ( 0.0 , 0.0 , 0.0 , 0.4 , 0.4\n"
            f"          ) : {instantiates};\n"
        )
    return (
        f"   {name} = MODULEDEFINITION DateCode_ 1\n"
        "   LOCALVARIABLES\n"
        "      Value: integer := 0;\n"
        f"{submodules}"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        f"   ENDDEF (*{name}*);\n"
    )


def _typedefinitions(*moduletypes: str) -> str:
    return "TYPEDEFINITIONS\n" + "".join(moduletypes)


def test_moduletype_that_instantiates_itself_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    typedefs = _typedefinitions(_moduletype("LoopType", instantiates="LoopType"))
    write_file(root, "Main.s", _source("Main", typedefs=typedefs))
    with pytest.raises(ModuleTypeCycleError) as excinfo:
        _load(root, "Main")
    assert excinfo.value.cycle == ("LoopType", "LoopType")
    assert "module type instantiates itself recursively: LoopType -> LoopType" in str(excinfo.value)


def test_mutually_recursive_moduletypes_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    typedefs = _typedefinitions(
        _moduletype("AType", instantiates="BType"),
        _moduletype("BType", instantiates="AType"),
    )
    write_file(root, "Main.s", _source("Main", typedefs=typedefs))
    with pytest.raises(ModuleTypeCycleError) as excinfo:
        _load(root, "Main")
    assert excinfo.value.cycle == ("AType", "BType", "AType")


def test_moduletype_cycle_across_programs_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    write_file(
        root,
        "A.s",
        _source("A", typedefs=_typedefinitions(_moduletype("AType", instantiates="BType"))),
    )
    write_file(
        root,
        "B.s",
        _source("B", typedefs=_typedefinitions(_moduletype("BType", instantiates="AType"))),
    )
    write_file(root, "A.l", "B\n")
    with pytest.raises(ModuleTypeCycleError) as excinfo:
        _load(root, "A")
    assert excinfo.value.cycle == ("AType", "BType", "AType")
    assert str(excinfo.value).startswith("A: ")


def test_moduletype_cycle_is_structural_in_a_lenient_load(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    typedefs = _typedefinitions(_moduletype("LoopType", instantiates="LoopType"))
    write_file(root, "Main.s", _source("Main", typedefs=typedefs))
    with pytest.raises(ModuleTypeCycleError):
        _load(root, "Main", strict=False)


def test_uninvoked_recursive_moduletype_in_a_dependency_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    write_file(root, "Main.s", _source("Main"))
    typedefs = _typedefinitions(_moduletype("LoopType", instantiates="LoopType"))
    write_file(root, "Dep.s", _source("Dep", typedefs=typedefs))
    write_file(root, "Main.l", "Dep\n")
    with pytest.raises(ModuleTypeCycleError):
        _load(root, "Main")


def test_acyclic_moduletype_instances_load(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    typedefs = _typedefinitions(
        _moduletype("Outer", instantiates="Inner"),
        _moduletype("Inner"),
    )
    write_file(root, "Main.s", _source("Main", typedefs=typedefs))
    project = _load(root, "Main")
    assert tuple(project.programs()) == ("main",)
    assert project.cycles() == ()


def test_same_type_names_in_unrelated_closures_are_not_a_cycle(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    left_types = _typedefinitions(
        _moduletype("AType", instantiates="BType"),
        _moduletype("BType"),
    )
    right_types = _typedefinitions(
        _moduletype("BType", instantiates="AType"),
        _moduletype("AType"),
    )
    write_file(left, "Left.s", _source("Left", typedefs=left_types))
    write_file(right, "Right.s", _source("Right", typedefs=right_types))

    project = SattLineProject.load([left, right], mode=LoadMode.DRAFT, targets=("Left", "Right"))

    assert set(project.programs()) == {"left", "right"}


def test_same_type_names_in_unrelated_closures_are_not_a_cycle_under_one_consumer(tmp_path: Path) -> None:
    """A build root that pulls both libraries in must not merge their type graphs."""
    root = tmp_path / "libs"
    root.mkdir()
    left_types = _typedefinitions(
        _moduletype("AType", instantiates="BType"),
        _moduletype("BType"),
    )
    right_types = _typedefinitions(
        _moduletype("BType", instantiates="AType"),
        _moduletype("AType"),
    )
    write_file(root, "Left.s", _source("Left", typedefs=left_types))
    write_file(root, "Right.s", _source("Right", typedefs=right_types))
    write_file(root, "Main.s", _source("Main"))
    write_file(root, "Main.l", "Left\nRight\n")

    project = _load(root, "Main")

    assert set(project.programs()) == {"main", "left", "right"}


def test_a_library_may_shadow_a_dependency_type_name(tmp_path: Path) -> None:
    """A local definition wins, so wrapping a dependency's type is not recursion."""
    root = tmp_path / "libs"
    root.mkdir()
    base_types = _typedefinitions(
        _moduletype("Valve", instantiates="Motor"),
        _moduletype("Motor"),
    )
    ext_types = _typedefinitions(_moduletype("Motor", instantiates="Valve"))
    write_file(root, "Base.s", _source("Base", typedefs=base_types))
    write_file(root, "Ext.s", _source("Ext", typedefs=ext_types))
    write_file(root, "Ext.l", "Base\n")

    project = _load(root, "Ext")

    assert set(project.programs()) == {"base", "ext"}


def test_project_errors_survive_pickling() -> None:
    """An error raised in a worker must reach the parent with its fields intact."""
    cycle_error = DependencyCycleError(("a", "b", "a"))
    moduletype_error = ModuleTypeCycleError("Main", ("AType", "BType", "AType"))

    restored_cycle = pickle.loads(pickle.dumps(cycle_error))
    restored_moduletype = pickle.loads(pickle.dumps(moduletype_error))

    assert restored_cycle.cycle == ("a", "b", "a")
    assert str(restored_cycle) == str(cycle_error)
    assert restored_moduletype.cycle == ("AType", "BType", "AType")
    assert restored_moduletype.program == "Main"


def test_cycle_key_keeps_direction_and_folds_rotation() -> None:
    assert cycle_key(("a", "b", "c", "a")) == cycle_key(("b", "c", "a", "b")) == ("a", "b", "c")
    assert cycle_key(("a", "b", "c", "a")) != cycle_key(("a", "c", "b", "a"))
    assert cycle_key(()) == ()


def test_first_cycle_stops_at_the_first_cycle() -> None:
    """A dense graph holds exponentially many cycles; rejection must not list them."""
    names = [f"t{index:02d}" for index in range(14)]
    edges = [(name, other) for name in names for other in names]

    assert first_cycle(edges) == ("t00", "t00")


def test_first_cycle_is_canonical_and_closed() -> None:
    edges = (("b", "c"), ("c", "a"), ("a", "b"))

    found = first_cycle(edges)

    assert found == ("a", "b", "c", "a")
    assert found in dependency_cycles(edges)


def test_first_cycle_is_none_for_a_dag() -> None:
    assert first_cycle((("a", "b"), ("b", "c"), ("a", "c"))) is None


def test_first_cycle_keeps_opposite_orderings_apart() -> None:
    assert first_cycle((("a", "b"), ("b", "a"))) == ("a", "b", "a")
    assert first_cycle((("a", "b"), ("b", "c"), ("c", "a"), ("a", "c"), ("c", "b"), ("b", "a"))) == ("a", "b", "a")


def test_dependency_cycles_does_not_collapse_orderings_with_the_same_members() -> None:
    edges = (("a", "b"), ("b", "c"), ("c", "a"), ("a", "c"), ("c", "b"), ("b", "a"))
    assert dependency_cycles(edges) == (
        ("a", "b", "a"),
        ("a", "b", "c", "a"),
        ("a", "c", "a"),
        ("a", "c", "b", "a"),
        ("b", "c", "b"),
    )


def test_libraries_reports_every_resolving_root(tmp_path: Path) -> None:
    first = tmp_path / "lib_a"
    second = tmp_path / "lib_b"
    first.mkdir()
    second.mkdir()
    write_file(first, "A.s", _source("A"))
    write_file(second, "B.s", _source("B"))
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
    write_file(root, "Dep.s", _source("Dep", typedefs=datatype.format(datecode=1)))
    write_file(root, "Main.s", _source("Main", typedefs=datatype.format(datecode=2)))
    write_file(root, "Main.l", "Dep\n")
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
    loader._resolved_dependencies["a"] = ("b",)
    with pytest.raises(RuntimeError, match="not in post-order"):
        loader._assert_registry_post_order()


def test_cycles_are_computed_for_directly_built_projects() -> None:
    code = parse_source_text(_source("X"))
    a = SattLineProgram(name="A", code=code, dependencies=("B",))
    b = SattLineProgram(name="B", code=code, dependencies=("A",))
    project = SattLineProject._from_programs({"A": a, "B": b})
    assert project.cycles() == (("a", "b", "a"),)


def test_cycles_report_no_cycle_for_a_dag() -> None:
    code = parse_source_text(_source("X"))
    a = SattLineProgram(name="A", code=code, dependencies=("B",))
    b = SattLineProgram(name="B", code=code)
    project = SattLineProject._from_programs({"A": a, "B": b})
    assert project.cycles() == ()


# --- per-finding tentativeness (VAL-11) ---------------------------------------

_LOCAL_CHILD = (
    "TYPEDEFINITIONS\n"
    "   ChildType = MODULEDEFINITION DateCode_ 1\n"
    "   MODULEPARAMETERS\n"
    "      {parameter}\n"
    "   ModuleDef\n"
    "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "   ENDDEF (*ChildType*);\n"
)


def test_a_local_parameter_transfer_mismatch_stays_final_with_a_skipped_dependency(tmp_path: Path) -> None:
    """A purely local mismatch does not depend on the missing dependency."""
    root = tmp_path / "libs"
    root.mkdir()
    typedefs = _LOCAL_CHILD.format(parameter="EnableFlag: boolean := False;")
    body = (
        "SUBMODULES\n"
        "   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ChildType (\n"
        "      EnableFlag => CounterValue);\n"
    )
    write_file(
        root,
        "Main.s",
        _source(
            "Main",
            typedefs=typedefs,
            locals_block="LOCALVARIABLES\n   CounterValue: integer := 0;\n",
            body=body,
        ),
    )
    write_file(root, "Main.l", "Ghost\n")

    program = _load(root, "Main", strict=False).get("Main")

    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V027"]
    assert program.diagnostics[0].tentative is False


def test_a_local_mapping_target_finding_stays_final_with_a_skipped_dependency(tmp_path: Path) -> None:
    root = tmp_path / "libs"
    root.mkdir()
    typedefs = _LOCAL_CHILD.format(parameter="Param: integer := 0;")
    body = "SUBMODULES\n   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ChildType (\n      Param.Field => 1);\n"
    write_file(root, "Main.s", _source("Main", typedefs=typedefs, body=body))
    write_file(root, "Main.l", "Ghost\n")

    program = _load(root, "Main", strict=False).get("Main")

    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V048"]
    assert program.diagnostics[0].tentative is False


def test_an_unknown_moduletype_stays_tentative_with_a_skipped_dependency(tmp_path: Path) -> None:
    """The missing definition may live in the dependency that was skipped."""
    root = tmp_path / "libs"
    root.mkdir()
    body = "SUBMODULES\n   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : GhostType;\n"
    write_file(root, "Main.s", _source("Main", body=body))
    write_file(root, "Main.l", "Ghost\n")

    program = _load(root, "Main", strict=False).get("Main")

    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V058"]
    assert program.diagnostics[0].tentative is True


def test_a_mapping_through_a_loaded_dependency_stays_final(tmp_path: Path) -> None:
    """A loaded dependency's module type is fully known, so the finding is final."""
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
    write_file(root, "Dep.s", _source("Dep", typedefs=records + moduletype))
    body = (
        "SUBMODULES\n"
        "   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ChildType (\n"
        '      Param.Value => "not an integer");\n'
    )
    write_file(root, "Main.s", _source("Main", body=body))
    write_file(root, "Main.l", "Dep\n")

    program = _load(root, "Main").get("Main")

    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V050"]
    assert program.diagnostics[0].tentative is False


def test_a_mapping_against_a_datatype_from_a_skipped_dependency_is_tentative(tmp_path: Path) -> None:
    """The parameter datatype came from the dependency that did not load."""
    root = tmp_path / "libs"
    root.mkdir()
    typedefs = _LOCAL_CHILD.format(parameter="Param: DepRec;")
    body = "SUBMODULES\n   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ChildType (\n      Param => 5);\n"
    write_file(root, "Main.s", _source("Main", typedefs=typedefs, body=body))
    write_file(root, "Main.l", "Ghost\n")

    program = _load(root, "Main", strict=False).get("Main")

    codes = [diagnostic.code.value for diagnostic in program.diagnostics]
    assert "SL-V050" in codes
    assert all(diagnostic.tentative for diagnostic in program.diagnostics)


def test_a_mapping_through_an_incomplete_dependency_moduletype_is_tentative(tmp_path: Path) -> None:
    """The invoked module type itself came from a dependency that is incomplete."""
    root = tmp_path / "libs"
    root.mkdir()
    childtype = (
        "TYPEDEFINITIONS\n"
        "   ChildType = MODULEDEFINITION DateCode_ 1\n"
        "   MODULEPARAMETERS\n"
        "      Param: integer := 0;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*ChildType*);\n"
    )
    body = "SUBMODULES\n   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ChildType (\n      Param.Field => 1);\n"
    write_file(root, "Dep.s", _source("Dep", typedefs=childtype))
    write_file(root, "Dep.l", "GhostInner\n")
    write_file(root, "Main.s", _source("Main", body=body))
    write_file(root, "Main.l", "Dep\nGhost\n")

    program = _load(root, "Main", strict=False).get("Main")

    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V048"]
    assert program.diagnostics[0].tentative is True


def test_a_mapping_against_an_incomplete_dependency_datatype_is_tentative(tmp_path: Path) -> None:
    """The module type is complete, but its parameter datatype came from a dependency that is not."""
    root = tmp_path / "libs"
    root.mkdir()
    childtype = (
        "TYPEDEFINITIONS\n"
        "   ChildType = MODULEDEFINITION DateCode_ 1\n"
        "   MODULEPARAMETERS\n"
        "      Param: SharedRec;\n"
        "   ModuleDef\n"
        "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "   ENDDEF (*ChildType*);\n"
    )
    shared = (
        "TYPEDEFINITIONS\n   SharedRec = RECORD DateCode_ 1\n      Value: integer := 0;\n   ENDDEF (*SharedRec*);\n"
    )
    body = "SUBMODULES\n   Child Invocation ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4 ) : ChildType (\n      Param.Field => 1);\n"
    write_file(root, "Complete.s", _source("Complete", typedefs=childtype))
    write_file(root, "Shared.s", _source("Shared", typedefs=shared))
    write_file(root, "Shared.l", "GhostInner\n")
    write_file(root, "Main.s", _source("Main", body=body))
    write_file(root, "Main.l", "Complete\nShared\nGhost\n")

    program = _load(root, "Main", strict=False).get("Main")

    assert [diagnostic.code.value for diagnostic in program.diagnostics] == ["SL-V048"]
    assert program.diagnostics[0].tentative is True
