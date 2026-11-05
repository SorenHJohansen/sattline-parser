# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false, reportTypedDictNotRequiredAccess=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_graphics_interact_mixin_keeps_graph_object_enable_tail():
    mixin = _GraphicsHarness()
    tail = VarTail("in", "Flag")
    graph_object = mixin.rectangle_object(
        [
            InterimCoords(coords=((0.0, 0.0), (1.0, 1.0))),
            CommonProperties(enable=EnableClause(True, tail)),
        ]
    )

    assert graph_object.properties[parser_const.KEY_ENABLE] is True
    assert graph_object.properties[parser_const.KEY_ENABLE_TAIL] == tail


def test_graphics_interact_mixin_builds_graph_objects_and_lists():
    mixin = _GraphicsHarness()
    coords = ((1.0, 2.0), (3.0, 4.0))
    coord_tail = VarTail("in", "CoordTail")
    payload_tail = VarTail("out", "PayloadTail")

    text_object = mixin.text_object(
        [
            TextContent("Caption"),
            Token(parser_const.TOKEN_VARNAME, "TextVar"),
            InterimCoords(coords=coords, tails=[coord_tail, payload_tail]),
        ]
    )

    assert text_object.type == parser_const.GRAMMAR_VALUE_TEXTOBJECT
    assert text_object.properties[parser_const.KEY_COORDS] == coords
    assert text_object.properties[parser_const.KEY_TAILS] == [coord_tail, payload_tail]
    assert text_object.properties["text_vars"] == [VarRef("Caption")]

    skipped_empty_text = mixin.text_object(
        [
            TextContent("Caption"),
            TextContent(""),
            Token(parser_const.TOKEN_VARNAME, "FallbackTextVar"),
            InterimCoords(coords=coords),
        ]
    )

    assert skipped_empty_text.properties["text_vars"] == [VarRef("Caption")]
    assert mixin.text_content(Meta(), ["Visible text"]) == TextContent("Visible text")

    with pytest.raises(ValueError, match="expected a TextContent"):
        mixin.text_object([0, Token(parser_const.TOKEN_VARNAME, "Broken")])

    for method_name, expected_type, keeps_coords in (
        ("rectangle_object", parser_const.GRAMMAR_VALUE_RECTANGLEOBJECT, True),
        ("line_object", parser_const.GRAMMAR_VALUE_LINEOBJECT, True),
        ("oval_object", parser_const.GRAMMAR_VALUE_OVALOBJECT, True),
        ("polygon_object", parser_const.GRAMMAR_VALUE_POLYGONOBJECT, False),
        ("segment_object", parser_const.GRAMMAR_VALUE_SEGMENTOBJECT, True),
    ):
        graph_object = getattr(mixin, method_name)([InterimCoords(coords=coords, tails=[coord_tail])])
        assert graph_object.type == expected_type
        if keeps_coords:
            assert graph_object.properties[parser_const.KEY_COORDS] == coords
        assert graph_object.properties[parser_const.KEY_TAILS] == [coord_tail]

    # The composite marker takes only the layer clause.
    composite = mixin.composite_object([7])
    assert composite.type == parser_const.GRAMMAR_VALUE_COMPOSITEOBJECT
    assert composite.properties == {"layer": 7}
    assert mixin.composite_object([]).properties == {}

    wrapped = mixin.graph_object(Meta(), [text_object, 7])
    interact_child = InteractObject(type="Button_", properties={})

    assert wrapped.properties["layer"] == 7
    assert mixin.graph_objects([text_object, "ignored", GraphObject(type="Rect", properties={})]) == [
        text_object,
        GraphObject(type="Rect", properties={}),
    ]
    assert mixin.interact_objects([interact_child, Tree("wrapper", [interact_child, "ignored"])]) == [
        interact_child,
        interact_child,
    ]

    with pytest.raises(ValueError, match="graph_object expected a GraphObject"):
        mixin.graph_object(Meta(), ["bad"])
    with pytest.raises(ValueError, match="text_content expected a str"):
        mixin.text_content(Meta(), [1, 2])


def test_graph_objects_propagates_section_level_layer_to_objects():
    mixin = _GraphicsHarness()
    rect = mixin.rectangle_object([InterimCoords(coords=((0.0, 0.0), (1.0, 1.0)))])
    text = mixin.text_object(["Caption"])
    explicit = mixin.rectangle_object([InterimCoords(coords=((0.0, 0.0), (1.0, 1.0))), CommonProperties(layer=9)])

    # A section-level Layer_ = 2 applies to every object lacking an explicit one.
    result = mixin.graph_objects([2, rect, text, explicit])
    assert result == [rect, text, explicit]
    assert rect.properties["layer"] == 2
    assert text.properties["layer"] == 2
    assert explicit.properties["layer"] == 9

    # Without a section layer, objects are untouched.
    fresh_rect = mixin.rectangle_object([InterimCoords(coords=((0.0, 0.0), (1.0, 1.0)))])
    untouched = mixin.graph_objects([fresh_rect, "ignored"])
    assert untouched == [fresh_rect]
    assert "layer" not in fresh_rect.properties


def test_graph_object_layer_is_per_object_not_section_level():
    # The real parser rejects a section-level layer clause. A layer belongs to
    # the object that declares it, so there is nothing to propagate.
    bp = parser_core_parse_source_text(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "GraphObjects :\n"
        "   RectangleObject ( -1.0 , 1.0 ) ( 1.0 , -1.0 )\n"
        "      Layer_ = 2\n"
        "   TextObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )\n"
        '      "DisplayValue"\n'
        "      Layer_ = 3\n"
        "ENDDEF (*BasePicture*);\n"
    )
    assert bp.moduledef is not None
    assert [go.properties.get("layer") for go in bp.moduledef.graph_objects] == [2, 3]


def test_graphobjects_section_layer_clause_is_rejected():
    with pytest.raises(UnexpectedInput):
        parser_core_parse_source_text(
            '"SyntaxVersion"\n'
            '"OriginalFileDate"\n'
            '"ProgramDate"\n'
            "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
            "ModuleDef\n"
            "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            "GraphObjects : Layer_ = 2\n"
            "   RectangleObject ( -1.0 , 1.0 ) ( 1.0 , -1.0 )\n"
            "ENDDEF (*BasePicture*);\n"
        )


def _composite_source(graph_body: str) -> str:
    return (
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "GraphObjects :\n"
        f"{graph_body}\n"
        "ENDDEF (*BasePicture*);\n"
    )


def test_composite_marker_takes_only_the_layer_clause():
    """Reads `CompositeObject [Layer_ = <int>]` and nothing else."""
    bare = parser_core_parse_source_text(_composite_source("   CompositeObject"))
    assert bare.moduledef is not None
    assert bare.moduledef.graph_objects[0].properties == {}

    layered = parser_core_parse_source_text(_composite_source("   CompositeObject Layer_ = 2"))
    assert layered.moduledef is not None
    assert layered.moduledef.graph_objects[0].properties == {"layer": 2}

    commented = parser_core_parse_source_text(_composite_source("   CompositeObject (* note *) Layer_ = 3"))
    assert commented.moduledef is not None
    assert commented.moduledef.graph_objects[0].properties == {"layer": 3}


def test_composite_marker_rejects_other_object_properties():
    for body in (
        "   CompositeObject Enable_ = True",
        "   CompositeObject OutlineColour : Colour0 = 2",
    ):
        with pytest.raises(UnexpectedInput):
            parser_core_parse_source_text(_composite_source(body))


def test_graphics_property_readers_accept_on_off():
    """`On`/`Off` are equivalent to `True`/`False` in a property reader."""
    on = parser_core_parse_source_text(
        _composite_source("   RectangleObject ( -1.0 , 1.0 ) ( 1.0 , -1.0 ) Enable_ = On")
    )
    off = parser_core_parse_source_text(
        _composite_source("   RectangleObject ( -1.0 , 1.0 ) ( 1.0 , -1.0 ) Enable_ = Off")
    )

    assert on.moduledef is not None
    assert on.moduledef.graph_objects[0].properties[parser_const.KEY_ENABLE] is True
    assert off.moduledef is not None
    assert off.moduledef.graph_objects[0].properties[parser_const.KEY_ENABLE] is False


def test_graph_object_handles_standalone_and_attached_connection_nodes():
    mixin = _GraphicsHarness()

    bare_object = mixin.connection_node_bare([])
    assert bare_object.type == parser_const.GRAMMAR_VALUE_CONNECTIONNODE
    assert bare_object.properties == {}

    positioned = mixin.connection_node([Token("LPAR", "("), 0.25, Token("COMMA", ","), 0.25])
    assert positioned.type == parser_const.GRAMMAR_VALUE_CONNECTIONNODE
    assert positioned.properties[parser_const.KEY_COORDS] == (0.25, 0.25)

    with pytest.raises(ValueError, match="connection_node expected two REAL coordinates"):
        mixin.connection_node([0.25])

    merged = mixin.common_properties(
        [
            3,
            GraphObject(parser_const.GRAMMAR_VALUE_CONNECTIONNODE),
            EnableClause(False, VarTail("in", "Enabled")),
            ColourSpec("outline"),
        ]
    )
    assert merged == CommonProperties(
        layer=3, enable=EnableClause(False, VarTail("in", "Enabled")), colours=(ColourSpec("outline"),)
    )
    assert merged.layer == 3


def test_interact_simple_item_extracts_type_from_grammar_tree():
    # The real grammar yields interact_type_simple as the type name; the type
    # must be extracted, never defaulted to "Interact".
    mixin = _GraphicsHarness()
    simple = mixin.interact_simple_item(
        Meta(),
        [
            "ComBut_",
            InterimCoords(coords=((0.0, 0.0), (1.0, 1.0))),
            [EnableClause(True)],
        ],
    )
    assert simple.type == "ComBut_"
    with pytest.raises(ValueError, match="interact_simple_item expected an interactor type"):
        mixin.interact_simple_item(Meta(), [InterimCoords(coords=((0.0, 0.0), (1.0, 1.0)))])
    with pytest.raises(ValueError, match="interact_type_simple expected an interactor token"):
        mixin.interact_type_simple([])
    assert mixin.interact_type_simple([Token("COMBUT", "ComBut_")]) == "ComBut_"


def test_interact_scale_selector_maps_relative_and_abs():
    mixin = _GraphicsHarness()
    assert mixin.interact_scale_selector(Meta(), [Token("RELATIVE_KW", "Relative_")]) == ScaleSelector("relative")
    assert mixin.interact_scale_selector(Meta(), [Token("ABS_KW", "Abs_")]) == ScaleSelector("abs")
    with pytest.raises(ValueError, match="interact_scale_selector expected"):
        mixin.interact_scale_selector(Meta(), [Token("NAME", "Other")])


def test_interact_alignment_and_body_rules_return_typed_payloads():
    mixin = _GraphicsHarness()

    assert mixin.alignment(Meta(), [Token("LEFTALIGNED", "LeftAligned")]) == Alignment("left")
    assert mixin.alignment(Meta(), [Token("RIGHTALIGNED", "RightAligned")]) == Alignment("right")
    with pytest.raises(ValueError, match="alignment expected"):
        mixin.alignment(Meta(), [Token("NAME", "Middle")])
    with pytest.raises(ValueError, match="alignment expected"):
        mixin.alignment(Meta(), [])

    clause = EnableClause(True, None)
    assert mixin.interact_body([clause]) is clause
    with pytest.raises(ValueError, match="interact_body expected"):
        mixin.interact_body([])

    comment = Tree(
        "comments",
        [Tree("comment", [Token("COMMENT_START", "(*"), Token("COMMENT_TEXT", " note "), Token("COMMENT_END", "*)")])],
    )
    body = mixin.interact_body_seq([clause, comment])

    assert body[0] is clause
    assert isinstance(body[1], CodeComment)
    assert body[1].text == "(* note *)"


def test_interact_pick_button_models_literal_and_reference():
    """`IntObjPickButton "=" STRING [VarName]`; VarName is a postfix marker."""
    mixin = _GraphicsHarness()

    literal = mixin.interact_pick_button(Meta(), [Token("INTOBJPICKBUTTON_KW", "IntObjPickButton"), "Pick me"])
    assert literal == PickButton("Pick me")

    reference = mixin.interact_pick_button(
        Meta(), [Token("INTOBJPICKBUTTON_KW", "IntObjPickButton"), "PickVar", Token("VARNAME", "VarName")]
    )
    assert reference == PickButton("PickVar", reference=VarRef("PickVar"))

    with pytest.raises(ValueError, match="interact_pick_button expected"):
        mixin.interact_pick_button(Meta(), [Token("INTOBJPICKBUTTON_KW", "IntObjPickButton")])


def test_interactor_body_accepts_pick_button_and_scale_selector():
    bp = parser_core_parse_source_text(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "InteractObjects :\n"
        "   TextBox_ ( -0.8 , 0.9 ) ( 0.8 , 0.7 )\n"
        "      Int_Value\n"
        '      IntObjPickButton = "Pick me"\n'
        '      IntObjPickButton = "PickVar" VarName\n'
        "      RightAligned Relative_\n"
        "ENDDEF (*BasePicture*);\n"
    )

    assert bp.moduledef is not None
    payloads = _body_payloads(bp.moduledef.interact_objects[0])
    assert PickButton("Pick me") in payloads
    assert PickButton("PickVar", reference=VarRef("PickVar")) in payloads
    assert ScaleSelector("relative") in payloads


def test_interact_flag_captures_plain_string_name():
    # NAME terminals arrive as plain strings after token coercion; the name
    # must land in "name", not in "tail".
    mixin = _GraphicsHarness()
    assert mixin.interact_flag(Meta(), ["Int_Value"]) == FlagClause("Int_Value")
    assert mixin.interact_flag(Meta(), [Token("TEXTOBJECT", "TextObject")]) == FlagClause("TextObject")


def test_common_properties_preserves_layer_enable_and_colour_content():
    mixin = _GraphicsHarness()
    colour = ColourSpec("outline")
    enable = EnableClause(False, VarTail("in", "Enabled"))
    merged = mixin.common_properties(
        [
            Tree("comment", [Token("COMMENT_START", "(*")]),
            7,
            enable,
            colour,
        ]
    )
    assert merged == CommonProperties(layer=7, enable=enable, colours=(colour,))

    obj = mixin.rectangle_object(
        [
            InterimCoords(coords=((0.0, 0.0), (1.0, 1.0))),
            merged,
        ]
    )
    assert obj.properties["layer"] == 7
    assert obj.properties[parser_const.KEY_ENABLE] is False
    assert obj.properties["colours"] == [colour]


def test_combutproc_item_preserves_assignments_flags_enables_layers_and_colours():
    mixin = _GraphicsHarness()
    assign = AssignClause("Variable", 0, VarTail("out", "AssignTail"))
    enable = EnableClause(True, VarTail("in", "En"))
    flag = FlagClause("Abs_")
    colour = ColourSpec("outline", assignments=(TailedClause("Colour0", 2),))
    item = mixin.combutproc_item(
        Meta(),
        [
            InterimCoords(coords=((0.0, 0.0), (1.0, 1.0))),
            mixin.combutproc_tail([3]),
            mixin.combutproc_tail([assign]),
            mixin.combutproc_tail([enable]),
            mixin.combutproc_tail([flag]),
            mixin.combutproc_tail([colour]),
        ],
    )
    assert item.properties["layers"] == [3]
    assert item.properties["assigns"] == [assign]
    assert item.properties["enables"] == [enable]
    assert item.properties["flags"] == [flag]
    assert item.properties["colours"] == [colour]
    assert item.properties["tails"] == [VarTail("out", "AssignTail"), VarTail("in", "En")]

    with pytest.raises(ValueError, match="combutproc_tail expected a tail item"):
        mixin.combutproc_tail([])


def test_procedure_call_keeps_name_out_of_args():
    mixin = _GraphicsHarness()
    assert mixin.procedure_call(Meta(), ["OpenValve", 42]) == ProcedureCall("OpenValve", (42,))
    assert mixin.procedure_args([1, Token("COMMA", ","), VarTail("in", "Arg")]) == [1, VarTail("in", "Arg")]
    with pytest.raises(ValueError, match="procedure_call missing name"):
        mixin.procedure_call(Meta(), [42])


def test_tailed_clause_handlers_build_typed_plain_and_tailed_clauses():
    mixin = _GraphicsHarness()
    tail = VarTail("in", "T")
    width = TailedClause(parser_const.GRAMMAR_VALUE_WIDTH_KEY, 2, tail)
    style = TailedClause(parser_const.GRAMMAR_VALUE_COLOURSTYLE, 1.5, tail)
    colour0 = TailedClause(parser_const.GRAMMAR_VALUE_COLOUR0, 1, tail)
    colour1 = TailedClause(parser_const.GRAMMAR_VALUE_COLOUR1, 3)

    assert mixin.format_string_tailed(
        Meta(), [Token("FORMATSTRING", parser_const.GRAMMAR_VALUE_FORMAT_STRING), "%d", tail]
    ) == TailedClause(parser_const.GRAMMAR_VALUE_FORMAT_STRING, "%d", tail)
    assert mixin.format_string_plain(
        Meta(), [Token("FORMATSTRING", parser_const.GRAMMAR_VALUE_FORMAT_STRING), 5]
    ) == TailedClause(parser_const.GRAMMAR_VALUE_FORMAT_STRING, 5)
    assert mixin.format_string([TailedClause(parser_const.GRAMMAR_VALUE_FORMAT_STRING, 5)]) == TailedClause(
        parser_const.GRAMMAR_VALUE_FORMAT_STRING, 5
    )
    assert mixin.value_fraction_tailed(
        Meta(), [Token("VALUEFRACTION", parser_const.GRAMMAR_VALUE_VALUEFRACTION), 2, tail]
    ) == (TailedClause(parser_const.GRAMMAR_VALUE_VALUEFRACTION, 2, tail))
    assert mixin.value_fraction_plain(
        Meta(), [Token("VALUEFRACTION", parser_const.GRAMMAR_VALUE_VALUEFRACTION), 2]
    ) == (TailedClause(parser_const.GRAMMAR_VALUE_VALUEFRACTION, 2))
    assert mixin.value_fraction([TailedClause(parser_const.GRAMMAR_VALUE_VALUEFRACTION, 2)]) == TailedClause(
        parser_const.GRAMMAR_VALUE_VALUEFRACTION, 2
    )
    assert mixin.width_tailed(Meta(), [Token("WIDTH_KEY", parser_const.GRAMMAR_VALUE_WIDTH_KEY), 2, tail]) == width
    assert mixin.width_plain(Meta(), [Token("WIDTH_KEY", parser_const.GRAMMAR_VALUE_WIDTH_KEY), 2]) == TailedClause(
        parser_const.GRAMMAR_VALUE_WIDTH_KEY, 2
    )
    assert mixin.width([width]) == width
    assert (
        mixin.assign_colour_tailed(Meta(), [Token("COLOUR0", parser_const.GRAMMAR_VALUE_COLOUR0), 1, tail]) == colour0
    )
    assert mixin.assign_colour_plain(Meta(), [Token("COLOUR0", parser_const.GRAMMAR_VALUE_COLOUR0), 1]) == TailedClause(
        parser_const.GRAMMAR_VALUE_COLOUR0, 1
    )
    assert mixin.assign_colour([colour0]) == colour0
    assert (
        mixin.colour_style_tailed(Meta(), [Token("COLOURSTYLE", parser_const.GRAMMAR_VALUE_COLOURSTYLE), 1.5, tail])
        == style
    )
    assert mixin.colour_style_plain(Meta(), [Token("COLOURSTYLE", parser_const.GRAMMAR_VALUE_COLOURSTYLE), 1.5]) == (
        TailedClause(parser_const.GRAMMAR_VALUE_COLOURSTYLE, 1.5)
    )
    assert mixin.colour_style([style]) == style
    assert mixin.colour_assignments([colour0, Token("JUNK", ","), colour1]) == (colour0, colour1)
    assert mixin.outline_colour(Meta(), [width, (colour0, colour1), style]) == ColourSpec(
        "outline", width=width, assignments=(colour0, colour1), style=style
    )
    assert mixin.fill_colour(Meta(), [(colour0,)]) == ColourSpec("fill", assignments=(colour0,))
    assert mixin.color_properties([ColourSpec("fill")]) == ColourSpec("fill")

    with pytest.raises(ValueError, match="tailed clause expected a keyword and a value"):
        mixin._tailed_clause([Token("JUNK", ",")])
    with pytest.raises(ValueError, match="expected a tailed clause"):
        mixin.format_string([])
    with pytest.raises(ValueError, match="color_properties expected a colour block"):
        mixin.color_properties([])


def _body_payloads(interactor: object) -> list[object]:
    """Return one interactor's typed body entries."""
    properties = getattr(interactor, "properties", {})
    return list(cast("dict[str, Any]", properties).get("body") or ())


def test_interact_widgets_fixture_preserves_types_names_and_assignments():
    # End-to-end regression: parsing InteractWidgets.s must not silently drop
    # interactor types, flag names, or assignment lines.
    source = _repo_path("tests", "fixtures", "corpus", "valid", "InteractWidgets.s").read_text(encoding="utf-8")
    bp = parser_core_parse_source_text(source)
    assert bp.moduledef is not None
    interactors = {io.type: io for io in bp.moduledef.interact_objects}

    assert set(interactors) == {"TextBox_", "ComBut_", "ComButProc_"}
    text_box = interactors["TextBox_"]
    body_text = " ".join(repr(item) for item in cast(list[Any], text_box.properties.get("body", [])))
    assert "Int_Value" in body_text and "Digits_" in body_text
    # ``Abs_``/``Relative_`` are modelled as a distinct scale-mode selector now.
    assert ScaleSelector("abs") in _body_payloads(text_box)
    assert ScaleSelector("abs") in _body_payloads(interactors["ComBut_"])

    proc_item = interactors["ComButProc_"]
    assert proc_item.properties.get("assigns") is not None
    assert "Variable" in repr(proc_item.properties["assigns"])


def test_interact_body_is_typed_and_keeps_alignment_and_comments():
    code = (
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "InteractObjects :\n"
        "    TextBox_ ( 0.0 , 0.0 ) ( 1.0 , 1.0 )\n"
        "        (* body comment *)\n"
        "        RightAligned\n"
        '        IntObjPickButton = "PickVar" VarName\n'
        "ENDDEF (*BasePicture*);\n"
    )
    bp = parser_core_parse_source_text(code)
    assert bp.moduledef is not None

    body = bp.moduledef.interact_objects[0].properties.get(parser_const.KEY_BODY)
    assert body is not None
    assert any(isinstance(entry, Alignment) and entry.value == "right" for entry in body)
    assert any(isinstance(entry, CodeComment) and "body comment" in entry.text for entry in body)
    assert any(isinstance(entry, PickButton) and entry.value == "PickVar" for entry in body)
    assert not any(isinstance(entry, Tree) for entry in body)


def test_interact_body_entries_are_typed_payloads():
    source = _repo_path("tests", "fixtures", "corpus", "valid", "InteractWidgets.s").read_text(encoding="utf-8")
    bp = parser_core_parse_source_text(source)
    assert bp.moduledef is not None

    bodies = [item.properties.get(parser_const.KEY_BODY) for item in bp.moduledef.interact_objects]
    non_empty = [body for body in bodies if body is not None]
    assert non_empty
    for body in non_empty:
        assert all(not isinstance(entry, Tree) for entry in body)


def test_moduledef_options_fixture_preserves_grid_zoom_and_layers():
    source = (
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ZoomLimits = 0.5 2.0\n"
        "Zoomable\n"
        "Grid = 10.0\n"
        "Two_Layers_ LayerLimit_ = 3.0\n"
        "ENDDEF (*BasePicture*);\n"
    )
    bp = parser_core_parse_source_text(source)
    assert bp.moduledef is not None
    assert bp.moduledef.zoom_limits == (0.5, 2.0)
    assert bp.moduledef.zoomable is True
    assert bp.moduledef.grid == 10.0
    assert bp.moduledef.seq_layers == 3.0


def test_graphics_interact_mixin_cover_interact_helpers_and_validation_errors():
    mixin = _GraphicsHarness()
    coords = ((0.0, 0.0), (1.0, 1.0))
    coord_tail = VarTail("in", "CoordTail")
    proc = mixin.procedure_call(Meta(), [Token("NAME", "ToggleWindow"), "arg1", 2])
    assert proc.name == "ToggleWindow"
    # A plain-string name (the real NAME->str coercion) must land in name, not args.
    assert mixin.procedure_call(Meta(), ["OpenValve", "argA"]) == ProcedureCall("OpenValve", ("argA",))
    combut = mixin.combutproc_item(
        Meta(),
        [
            InterimCoords(coords=coords, tails=[coord_tail]),
            proc,
            ProcedureCall("OtherProc"),
        ],
    )
    enable_body = EnableClause(True, VarTail("in", "EnableVar"))
    simple = mixin.interact_simple_item(
        Meta(),
        [
            "Button_",
            InterimCoords(coords=coords),
            [enable_body],
        ],
    )

    assert combut.type == parser_const.GRAMMAR_VALUE_COMBUTPROC
    assert combut.properties[parser_const.KEY_COORDS] == [coords]
    assert combut.properties[parser_const.KEY_PROCEDURE] == ProcedureCall("OtherProc")
    assert combut.properties[parser_const.KEY_TAILS] == [coord_tail]
    assert simple.type == "Button_"
    assert simple.properties[parser_const.KEY_COORDS] == [coords]
    assert simple.properties[parser_const.KEY_BODY] == [enable_body]
    assert simple.properties[parser_const.KEY_TAILS] == [VarTail("in", "EnableVar")]

    without_body = mixin.interact_simple_item(Meta(), ["Button_", InterimCoords(coords=coords)])
    assert without_body.properties[parser_const.KEY_BODY] is None

    assert mixin.enable(Meta(), [False, VarTail("in", "EnableExpr")]) == EnableClause(
        False, VarTail("in", "EnableExpr")
    )
    assert mixin.enable_combut(Meta(), [False, Compare(VarRef("Flag"), "==", 1)]) == EnableClause(
        False, Compare(VarRef("Flag"), "==", 1)
    )
    assert mixin.enable_expression([Token("JUNK", "="), "Expr"]) == "Expr"
    assert mixin.module_in_view(Meta(), [True, VarTail("out", "Visible")]) == ModuleInViewClause(
        True, VarTail("out", "Visible")
    )
    assert mixin.interact_assign_variable_tailed(Meta(), ["Setpoint", 5, VarTail("out", "OutVar")]) == AssignClause(
        "Setpoint", 5, VarTail("out", "OutVar")
    )
    assert mixin.interact_assign_variable_plain(Meta(), ["Setpoint", 5]) == AssignClause("Setpoint", 5)
    assert mixin.interact_assign_variable([AssignClause("Setpoint", 5)]) == AssignClause("Setpoint", 5)
    assert mixin.interact_flag(
        Meta(),
        [
            Token(parser_const.KEY_NAME, "Abs_"),
            Token(parser_const.KEY_STRING, "label"),
            VarTail("in", "InVar"),
        ],
    ) == FlagClause("Abs_", "label", VarTail("in", "InVar"))
    assert mixin.interact_value_line([1]) == 1
    assert mixin.layer_info([Token("JUNK", ":"), 4]) == 4
    assert mixin.seq_control_opt(["SEQ_CONTROL", "SEQTIMER"]).data == parser_const.KEY_SEQ_CONTROL_OPS
    assert mixin.codeblock_coord([Token("LPAR", "("), 1, 2]) == (1.0, 2.0)
    assert mixin.objsizedef([Token("LPAR", "("), 3, 4]) == (3.0, 4.0)

    with pytest.raises(ValueError, match="enable_expression expected"):
        mixin.enable_expression([Token("JUNK", "=")])
    with pytest.raises(ValueError, match="interact_assign_variable expected"):
        mixin.interact_assign_variable(["bad"])
    with pytest.raises(ValueError, match="interact assignment expected a name and a value"):
        mixin.interact_assign_variable_plain(Meta(), [])
    with pytest.raises(ValueError, match="interact_flag expected a flag name"):
        mixin.interact_flag(Meta(), [])
    with pytest.raises(ValueError, match="interact_value_line expected a value"):
        mixin.interact_value_line([])
    with pytest.raises(ValueError, match="layer_info expected"):
        mixin.layer_info(["bad"])
    with pytest.raises(ValueError, match="codeblock_coord expected 2 coordinate values"):
        mixin.codeblock_coord([1])
    with pytest.raises(ValueError, match="objsizedef expected 2 size values"):
        mixin.objsizedef([1])
