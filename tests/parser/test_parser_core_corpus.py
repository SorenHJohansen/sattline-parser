# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
"""Fixture-corpus regression tests.

Each fixture documents one real SattLine feature or edge case (see the header
comment inside the .s file for the language question it pins down). These
tests assert the AST semantics the fixture is meant to preserve, so a fixture
is not just "parses without throwing".
"""

from ._parser_core_test_support import *


def _load_fixture(name: str, subdir: str = "valid") -> BasePicture:
    path = _repo_path("tests", "fixtures", "corpus", subdir, name)
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
    assert len(bp.moduledefs) == 1
    assert len(bp.modulecodes) == 1
    assert bp.moduledefs[0].clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))
    assert [eq.name for mc in bp.modulecodes for eq in (mc.equations or [])] == ["Lower"]
    assert bp.moduledef is bp.moduledefs[-1]
    assert bp.modulecode is bp.modulecodes[-1]


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


def _interact_entries(interactor: Any) -> list[dict[str, Any]]:
    body = cast(list[Any], interactor.properties.get("body", []))
    entries: list[dict[str, Any]] = []
    for node in body:
        assert isinstance(node, Tree)
        assert node.data == "interact_body"
        assert len(node.children) == 1
        entry = node.children[0]
        assert isinstance(entry, dict)
        entries.append(cast(dict[str, Any], entry))
    return entries


def test_fixture_interact_enable_tails_keep_assignments_and_enables():
    bp = _load_fixture("InteractEnableTails.s")
    assert bp.moduledef is not None
    interactors = {io.type: io for io in bp.moduledef.interact_objects}
    assert set(interactors) == {"TextBox_", "ComBut_"}

    # TextBox_: `Variable = 0 : (InputValue > 0)` -- the assignment directive
    # keeps an expression tail.
    text_entries = _interact_entries(interactors["TextBox_"])
    text_assign = next(e["assign"] for e in text_entries if "assign" in e)
    assert text_assign["name"] == "Variable"
    assert isinstance(text_assign["tail"], Compare)
    assert text_assign["tail"].left == VarRef(name="InputValue", state=None, span=text_assign["tail"].left.span)

    # ComBut_: `Variable = False : InVar_ "EnableFlag"` keeps the quoted symbol
    # as its tail, and `Enable_ = True : InVar_ "ToggleBit"` keeps it too.
    button_entries = _interact_entries(interactors["ComBut_"])
    button_assign = next(e["assign"] for e in button_entries if "assign" in e)
    assert button_assign["name"] == "Variable"
    assert button_assign["tail"] == "EnableFlag"
    enable = next(e for e in button_entries if "enable" in e)
    assert enable["enable"] is True
    assert enable["tail"] == "ToggleBit"


def test_fixture_deeply_nested_comments_roundtrip_as_single_comment():
    path = _repo_path("tests", "fixtures", "corpus", "edge_cases", "DeeplyNestedComments.s")
    bp = parser_core_parse_source_text(path.read_text(encoding="utf-8"))
    assert bp.modulecode is not None
    assert bp.modulecode.equations is not None
    equation = bp.modulecode.equations[0]
    comment_items = [x for x in equation.code if isinstance(x, CodeComment)]
    assert [c.text for c in comment_items] == [
        "(* level1 (* level2 (* level3 (* level4 (* level5 *) level4 *) level3 *) level2 *) level1 *)"
    ]


def test_invalid_fixtures_are_rejected():
    _rejects_fixture("invalid", "ModuleCodeWithoutModuleDef.s")
    _rejects_fixture("invalid", "GraphObjectsDoubleLayer.s")
    _rejects_fixture("invalid", "UnterminatedComment.s")
    _rejects_fixture("invalid", "CoordInVarTail.s")
    _rejects_fixture("invalid", "PropertyInVarBareName.s")
