from sattline_parser.models.ast_model import FrameModule, ModuleHeader, ModuleTypeInstance, SingleModule
from sattline_parser.project.reachability import invoked_moduletypes, iter_moduletype_refs


def _header(name: str) -> ModuleHeader:
    return ModuleHeader(name=name, invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0))


def test_iter_moduletype_refs_walks_nested_frames_and_instances() -> None:
    deep = ModuleTypeInstance(header=_header("Deep"), moduletype_name="DeepType")
    frame = FrameModule(header=_header("Frame"), submodules=[deep])
    single = SingleModule(header=_header("Single"), moduledef=None, submodules=[frame])

    assert list(iter_moduletype_refs([single])) == ["DeepType"]


def test_invoked_moduletypes_ignores_an_unknown_target() -> None:
    assert invoked_moduletypes({}, ["Missing"]) == {}
