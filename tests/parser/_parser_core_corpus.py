# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
"""Fixture-corpus regression tests.

Each fixture documents one real SattLine feature or edge case (see the header
comment inside the .s file for the language question it pins down). These
tests assert the AST semantics the fixture is meant to preserve, so a fixture
is not just "parses without throwing".
"""

from ._parser_core_test_support import *


def _load_fixture(name: str) -> BasePicture:
    path = _repo_path("tests", "fixtures", "corpus", "valid", name)
    return parser_core_parse_source_text(path.read_text(encoding="utf-8"))


def _rejects_fixture(subdir: str, name: str) -> None:
    path = _repo_path("tests", "fixtures", "corpus", subdir, name)
    with pytest.raises(UnexpectedInput):
        parser_core_parse_source_text(path.read_text(encoding="utf-8"))


def test_fixture_sfc_unnamed_elements_preserves_none_names():
    bp = _load_fixture("SFCUnnamedElements.s")
    assert bp.modulecode is not None
    assert bp.modulecode.sequences is not None
    sequence = bp.modulecode.sequences[0]

    init_step = next(node for node in sequence.code if isinstance(node, SFCStep) and node.kind == "init")
    assert init_step.name is None
    assert len(init_step.code.enter) == 1

    transitions = [node for node in sequence.code if isinstance(node, SFCTransition)]
    assert len(transitions) == 2
    assert all(t.name is None for t in transitions)

    step = next(node for node in sequence.code if isinstance(node, SFCStep) and node.kind == "step")
    assert step.name is None
    assert len(step.code.enter) == 1
    assert len(step.code.exit) == 1


def test_fixture_multiple_moduledef_blocks_preserves_all_in_source_order():
    bp = _load_fixture("MultipleModuleDefBlocks.s")
    assert len(bp.moduledefs) == 2
    assert len(bp.modulecodes) == 2
    assert bp.moduledefs[0].clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))
    assert bp.moduledefs[1].clipping_bounds == ((-2.0, -2.0), (2.0, 2.0))
    assert [eq.name for mc in bp.modulecodes for eq in (mc.equations or [])] == ["Lower", "Upper"]
    assert bp.moduledef is bp.moduledefs[-1]
    assert bp.modulecode is bp.modulecodes[-1]


def test_fixture_graph_objects_section_layer_applies_to_all_objects():
    bp = _load_fixture("GraphObjectsSectionLayer.s")
    assert bp.moduledef is not None
    assert [go.properties.get("layer") for go in bp.moduledef.graph_objects] == [2, 2]


def test_fixture_graph_object_enable_tails_keep_tail_content():
    bp = _load_fixture("GraphObjectEnableTails.s")
    assert bp.moduledef is not None
    text = bp.moduledef.graph_objects[0]
    assert text.type == "TextObject"
    assert "%d" in cast(list[Any], text.properties.get("tails", []))
    colours = cast(list[Any], text.properties.get("colours", []))
    colour_repr = repr(colours)
    assert "Colour0" in colour_repr and "Colour1" in colour_repr and "ColourStyle" in colour_repr


def test_fixture_graph_object_shapes_keep_their_types():
    bp = _load_fixture("GraphObjectShapes.s")
    assert bp.moduledef is not None
    assert [go.type for go in bp.moduledef.graph_objects] == [
        "LineObject",
        "OvalObject",
        "PolygonObject",
        "SegmentObject",
    ]


def test_fixture_interact_enable_tails_keep_assignments_and_enables():
    bp = _load_fixture("InteractEnableTails.s")
    assert bp.moduledef is not None
    interactors = {io.type: io for io in bp.moduledef.interact_objects}
    assert set(interactors) == {"TextBox_", "ComBut_"}

    text_box = interactors["TextBox_"]
    body = cast(list[Any], text_box.properties.get("body", []))
    assigns = [b for b in body if isinstance(b, Tree) and b.data == "interact_body"]
    assigns_repr = " ".join(repr(cast(list[Any], t.children)) for t in assigns)
    assert "Variable" in assigns_repr
    assert "InputValue" in assigns_repr
    assert "EnableFlag" in assigns_repr

    combut = interactors["ComBut_"]
    combut_repr = repr(cast(list[Any], combut.properties.get("body", [])))
    assert "ToggleBit" in combut_repr


def test_fixture_deeply_nested_comments_roundtrip_as_single_comment():
    path = _repo_path("tests", "fixtures", "corpus", "edge_cases", "DeeplyNestedComments.s")
    bp = parser_core_parse_source_text(path.read_text(encoding="utf-8"))
    assert bp.modulecode is not None
    assert [c.text for c in bp.modulecode.comments] == [
        "(* level1 (* level2 (* level3 (* level4 (* level5 *) level4 *) level3 *) level2 *) level1 *)"
    ]


def test_fixture_moduledef_no_trailing_enddef_parses():
    path = _repo_path("tests", "fixtures", "corpus", "edge_cases", "ModuleDefNoTrailingEnddef.s")
    bp = parser_core_parse_source_text(path.read_text(encoding="utf-8"))
    assert bp.moduledef is not None
    assert bp.moduledef.clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))


def test_invalid_fixtures_are_rejected():
    _rejects_fixture("invalid", "ModuleCodeWithoutModuleDef.s")
    _rejects_fixture("invalid", "GraphObjectsDoubleLayer.s")
    _rejects_fixture("invalid", "UnterminatedComment.s")
