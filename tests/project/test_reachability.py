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


def _caller() -> SattLineProgram:
    return _program(
        "Main",
        dependencies=("Lib",),
        submodules=(SingleModule(header=_header("Main"), submodules=[_invocation("Call")]),),
    )


def _library() -> SattLineProgram:
    return _program("Lib", moduletypes=(ModuleTypeDef(name="BType"),))


def test_invoked_moduletypes_accepts_spelled_keys() -> None:
    """The documented contract is the caller's own key space, not folded keys."""
    programs = {"Main": _caller(), "Lib": _library()}

    assert invoked_moduletypes(programs, ["Main"]) == {"Lib": {fold_identifier("BType")}}


def test_invoked_moduletypes_accepts_folded_keys() -> None:
    programs = {"main": _caller(), "lib": _library()}

    assert invoked_moduletypes(programs, ["main"]) == {"lib": {fold_identifier("BType")}}


def test_invoked_moduletypes_resolves_a_target_by_program_name() -> None:
    """A caller may key by plan identity and still target a program by its name."""
    programs = {"plan-main": _caller(), "plan-lib": _library()}

    assert invoked_moduletypes(programs, ["Main"]) == {"plan-lib": {fold_identifier("BType")}}


def test_invoked_moduletypes_returns_the_callers_keys() -> None:
    programs = {"Main": _caller(), "Lib": _library()}

    reachable = invoked_moduletypes(programs, ["Main"])

    assert set(reachable) <= set(programs)


def test_visible_program_keys_resolves_each_key_space() -> None:
    spelled = {"Main": _caller(), "Lib": _library()}
    folded = {"main": _caller(), "lib": _library()}
    by_path = {"plan-main": _caller(), "plan-lib": _library()}

    assert visible_program_keys(spelled, "Main", ("Lib",)) == frozenset({"Main", "Lib"})
    assert visible_program_keys(folded, "main", ("Lib",)) == frozenset({"main", "lib"})
    assert visible_program_keys(by_path, "plan-main", ("Lib",)) == frozenset({"plan-main", "plan-lib"})


def test_visible_program_keys_keeps_language_distinct_names_apart() -> None:
    """``STRASSE`` is a different unit from ``Straße``, whatever the view key is."""
    programs = {
        "main": _program("Straße", dependencies=("STRASSE",)),
        "lib": _program("STRASSE"),
    }

    assert visible_program_keys(programs, "main", ("STRASSE",)) == frozenset({"main", "lib"})


def test_invoked_moduletypes_keeps_language_distinct_names_apart() -> None:
    programs = {
        "main": _program(
            "Straße",
            dependencies=("STRASSE",),
            submodules=(SingleModule(header=_header("Straße"), submodules=[_invocation("Call")]),),
        ),
        "lib": _program("STRASSE", moduletypes=(ModuleTypeDef(name="BType"),)),
    }

    assert invoked_moduletypes(programs, ["main"]) == {"lib": {fold_identifier("BType")}}


def test_invoked_moduletypes_does_not_borrow_a_sharp_s_entry_for_a_view_key() -> None:
    """A caller keyed by the casefold view key must not absorb ``STRASSE``."""
    programs = {
        "strasse": _program(
            "Straße",
            dependencies=("STRASSE",),
            submodules=(SingleModule(header=_header("Straße"), submodules=[_invocation("Call")]),),
        ),
        "STRASSE": _program("STRASSE", moduletypes=(ModuleTypeDef(name="BType"),)),
    }

    assert invoked_moduletypes(programs, ["strasse"]) == {"STRASSE": {fold_identifier("BType")}}
