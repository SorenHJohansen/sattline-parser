from collections.abc import Sequence

from sattline_parser.models.ast_model import (
    BasePicture,
    FrameModule,
    ModuleHeader,
    ModuleTypeDef,
    ModuleTypeInstance,
    SingleModule,
)
from sattline_parser.names import fold_identifier
from sattline_parser.project.models import SattLineProgram
from sattline_parser.project.reachability import invoked_moduletypes, iter_moduletype_refs, visible_program_keys


def _header(name: str) -> ModuleHeader:
    return ModuleHeader(name=name, invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0))


def test_iter_moduletype_refs_walks_nested_frames_and_instances() -> None:
    deep = ModuleTypeInstance(header=_header("Deep"), moduletype_name="DeepType")
    frame = FrameModule(header=_header("Frame"), submodules=[deep])
    single = SingleModule(header=_header("Single"), submodules=[frame])

    assert list(iter_moduletype_refs([single])) == ["DeepType"]


def test_invoked_moduletypes_ignores_an_unknown_target() -> None:
    assert invoked_moduletypes({}, ["Missing"]) == {}


def _program(
    name: str,
    *,
    dependencies: tuple[str, ...] = (),
    moduletypes: Sequence[ModuleTypeDef] = (),
    submodules: Sequence[SingleModule | FrameModule | ModuleTypeInstance] = (),
) -> SattLineProgram:
    code = BasePicture(
        header=_header(name),
        moduletype_defs=list(moduletypes),
        submodules=list(submodules),
    )
    return SattLineProgram(name=name, code=code, dependencies=dependencies)


def _invocation(name: str) -> ModuleTypeInstance:
    return ModuleTypeInstance(header=_header(name), moduletype_name="BType")


def test_visible_program_keys_returns_loaded_transitive_dependencies() -> None:
    programs = {
        "a": _program("A", dependencies=("B", "Ghost", "A")),
        "b": _program("B", dependencies=("C",)),
        "c": _program("C"),
    }

    assert visible_program_keys(programs, "a", programs["a"].dependencies) == frozenset({"a", "b", "c"})


def test_visible_program_keys_ignores_a_dependency_that_is_not_loaded() -> None:
    programs = {"a": _program("A", dependencies=("Ghost",))}

    assert visible_program_keys(programs, "a", programs["a"].dependencies) == frozenset({"a"})


def test_invoked_moduletypes_walks_declared_dependencies_by_default() -> None:
    programs = {
        "a": _program(
            "A",
            dependencies=("B",),
            submodules=(SingleModule(header=_header("A"), submodules=[_invocation("Call")]),),
        ),
        "b": _program("B", moduletypes=(ModuleTypeDef(name="BType"),)),
    }

    assert invoked_moduletypes(programs, ["a"]) == {"b": {fold_identifier("BType")}}
