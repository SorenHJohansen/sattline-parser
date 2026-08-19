# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_graphics_interact_mixin_builds_graph_objects_and_lists():
    mixin = _GraphicsHarness(coord_tails=["CoordTail"], extra_tails=["ExtraTail"])
    coords = ((1.0, 2.0), (3.0, 4.0))

    text_object = mixin.text_object(
        [
            Tree(parser_const.TREE_TAG_TEXT_CONTENT, ["Caption"]),
            Token(parser_const.TOKEN_VARNAME, "TextVar"),
            InterimCoords(coords=coords, tails=["PayloadTail"]),
        ]
    )

    assert text_object.type == parser_const.GRAMMAR_VALUE_TEXTOBJECT
    assert text_object.properties[parser_const.KEY_COORDS] == coords
    assert text_object.properties[parser_const.KEY_TAILS] == ["CoordTail", "PayloadTail", "ExtraTail"]
    assert text_object.properties["text_vars"] == ["Caption"]

    skipped_empty_text = mixin.text_object(
        [
            "Caption",
            "",
            Token(parser_const.TOKEN_VARNAME, "FallbackTextVar"),
            InterimCoords(coords=coords),
        ]
    )

    assert skipped_empty_text.properties["text_vars"] == ["Caption"]
    assert mixin.text_content(["Visible text"]) == "Visible text"

    with pytest.raises(ValueError, match="_extract_text_from_node expected"):
        mixin.text_object([0, Token(parser_const.TOKEN_VARNAME, "Broken")])

    for method_name, expected_type, keeps_coords in (
        ("rectangle_object", parser_const.GRAMMAR_VALUE_RECTANGLEOBJECT, True),
        ("line_object", parser_const.GRAMMAR_VALUE_LINEOBJECT, True),
        ("oval_object", parser_const.GRAMMAR_VALUE_OVALOBJECT, True),
        ("polygon_object", parser_const.GRAMMAR_VALUE_POLYGONOBJECT, False),
        ("segment_object", parser_const.GRAMMAR_VALUE_SEGMENTOBJECT, True),
        ("composite_object", parser_const.GRAMMAR_VALUE_COMPOSITEOBJECT, False),
    ):
        graph_object = getattr(mixin, method_name)([InterimCoords(coords=coords)])
        assert graph_object.type == expected_type
        if keeps_coords:
            assert graph_object.properties[parser_const.KEY_COORDS] == coords
        assert graph_object.properties[parser_const.KEY_TAILS] == ["CoordTail", "ExtraTail"]

    wrapped = mixin.graph_object([text_object, 7])
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
        mixin.graph_object(["bad"])
    with pytest.raises(ValueError, match="text_content expected a str"):
        mixin.text_content([1, 2])


def test_interact_simple_item_extracts_type_from_grammar_tree():
    # The real grammar yields interact_type_simple as a Tree wrapping the type
    # token; the type must be extracted, never defaulted to "Interact".
    mixin = _GraphicsHarness(coord_tails=[], extra_tails=[])
    simple = mixin.interact_simple_item(
        [
            Tree("interact_type_simple", [Token("COMBUT", "ComBut_")]),
            ((0.0, 0.0), (1.0, 1.0)),
            Tree(parser_const.TREE_TAG_INTERACT_BODY_SEQ, ["body"]),
        ]
    )
    assert simple.type == "ComBut_"
    with pytest.raises(ValueError, match="interact_simple_item expected an interactor type"):
        mixin.interact_simple_item([((0.0, 0.0), (1.0, 1.0))])


def test_interact_flag_captures_plain_string_name():
    # NAME terminals arrive as plain strings after token coercion; the name
    # must land in "name", not in "tail".
    mixin = _GraphicsHarness(coord_tails=[], extra_tails=[])
    assert mixin.interact_flag(["Int_Value"]) == {
        parser_const.KEY_NAME: "Int_Value",
        parser_const.KEY_EXTRA: None,
        parser_const.KEY_TAIL: None,
    }


def test_common_properties_preserves_layer_enable_and_colour_content():
    mixin = _GraphicsHarness(coord_tails=[], extra_tails=[])
    merged = mixin.common_properties(
        [
            Tree("comment", [Token("COMMENT_START", "(*")]),
            7,
            {parser_const.TREE_TAG_ENABLE: False, parser_const.KEY_TAIL: "Enabled"},
            Tree("outline_colour", [Token("OUTLINECOLOUR", "OutlineColour")]),
        ]
    )
    assert merged["layer"] == 7
    assert merged[parser_const.TREE_TAG_ENABLE] is False
    assert merged["colours"] == [Tree("outline_colour", [Token("OUTLINECOLOUR", "OutlineColour")])]

    obj = mixin.rectangle_object(
        [
            InterimCoords(coords=((0.0, 0.0), (1.0, 1.0))),
            merged,
        ]
    )
    assert obj.properties["layer"] == 7
    assert obj.properties[parser_const.TREE_TAG_ENABLE] is False
    assert obj.properties["colours"] == merged["colours"]


def test_combutproc_item_preserves_assignments_flags_enables_layers_and_colours():
    mixin = _GraphicsHarness(coord_tails=[], extra_tails=[])
    item = mixin.combutproc_item(
        [
            ((0.0, 0.0), (1.0, 1.0)),
            mixin.combutproc_tail([3]),
            mixin.combutproc_tail([{parser_const.KEY_ASSIGN: {"name": "Variable", "value": 0}}]),
            mixin.combutproc_tail([{parser_const.TREE_TAG_ENABLE: True, parser_const.KEY_TAIL: "En"}]),
            mixin.combutproc_tail([{parser_const.KEY_NAME: "Abs_", parser_const.KEY_EXTRA: None}]),
            mixin.combutproc_tail([Tree("outline_colour", [Token("OUTLINECOLOUR", "OutlineColour")])]),
        ]
    )
    assert item.properties["layers"] == [3]
    assert item.properties["assigns"] == [{parser_const.KEY_ASSIGN: {"name": "Variable", "value": 0}}]
    assert item.properties["enables"] == [{parser_const.TREE_TAG_ENABLE: True, parser_const.KEY_TAIL: "En"}]
    assert item.properties["flags"] == [{parser_const.KEY_NAME: "Abs_", parser_const.KEY_EXTRA: None}]
    assert item.properties["colours"] == [Tree("outline_colour", [Token("OUTLINECOLOUR", "OutlineColour")])]

    with pytest.raises(ValueError, match="combutproc_tail expected a tail item"):
        mixin.combutproc_tail([])


def test_procedure_call_keeps_name_out_of_args():
    mixin = _GraphicsHarness(coord_tails=[], extra_tails=[])
    assert mixin.procedure_call([42])[parser_const.KEY_PROCEDURE_CALL] == {
        parser_const.KEY_NAME: None,
        parser_const.KEY_ARGS: [42],
    }


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
    assert "Int_Value" in body_text and "Abs_" in body_text and "Digits_" in body_text

    proc_item = interactors["ComButProc_"]
    assert proc_item.properties.get("assigns") is not None
    assert "Variable" in repr(proc_item.properties["assigns"])


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
    mixin = _GraphicsHarness(coord_tails=["CoordTail"], extra_tails=["TailVar"])
    coords = ((0.0, 0.0), (1.0, 1.0))
    proc_dict = mixin.procedure_call([Token("NAME", "ToggleWindow"), "arg1", 2])
    assert proc_dict[parser_const.KEY_PROCEDURE_CALL][parser_const.KEY_NAME] == "ToggleWindow"
    # A plain-string name (the real NAME->str coercion) must land in name, not args.
    plain_name_dict = mixin.procedure_call(["OpenValve", "argA"])
    assert plain_name_dict == {
        parser_const.KEY_PROCEDURE_CALL: {parser_const.KEY_NAME: "OpenValve", parser_const.KEY_ARGS: ["argA"]}
    }
    combut = mixin.combutproc_item(
        [
            coords,
            proc_dict,
            [{parser_const.KEY_PROCEDURE_CALL: {parser_const.KEY_NAME: "OtherProc", parser_const.KEY_ARGS: []}}],
        ]
    )
    simple = mixin.interact_simple_item(
        [
            Token("INTERACT", "Button_"),
            coords,
            Tree(parser_const.TREE_TAG_INTERACT_BODY_SEQ, ["body-a"]),
            ["body-b"],
            {parser_const.KEY_TAIL: "EnableVar"},
        ]
    )

    assert proc_dict == {
        parser_const.KEY_PROCEDURE_CALL: {
            parser_const.KEY_NAME: "ToggleWindow",
            parser_const.KEY_ARGS: ["arg1", 2],
        }
    }
    assert combut.type == parser_const.GRAMMAR_VALUE_COMBUTPROC
    assert combut.properties[parser_const.KEY_COORDS] == [coords]
    assert combut.properties[parser_const.KEY_PROCEDURE] == {
        parser_const.KEY_NAME: "OtherProc",
        parser_const.KEY_ARGS: [],
    }
    assert combut.properties[parser_const.KEY_TAILS] == ["CoordTail", "TailVar"]
    assert simple.type == "Button_"
    assert simple.properties[parser_const.KEY_COORDS] == [coords]
    assert simple.properties[parser_const.KEY_BODY] == ["body-a", "body-b"]
    assert simple.properties[parser_const.KEY_TAILS] == ["CoordTail", "TailVar", "EnableVar"]

    assert mixin.invar([Token("JUNK", "="), "VarRef"]) == "VarRef"
    assert mixin.enable([False, {parser_const.KEY_TAIL: "EnableExpr"}]) == {
        parser_const.TREE_TAG_ENABLE: False,
        parser_const.KEY_TAIL: {parser_const.KEY_TAIL: "EnableExpr"},
    }
    assert mixin.enable_expression([Token("JUNK", "="), "Expr"]) == "Expr"
    assert mixin.interact_assign_variable_tailed(["Setpoint", 5, {parser_const.KEY_TAIL: "OutVar"}]) == {
        parser_const.KEY_NAME: "Setpoint",
        parser_const.KEY_VALUE: 5,
        parser_const.KEY_TAIL: {parser_const.KEY_TAIL: "OutVar"},
    }
    assert mixin.interact_assign_variable_plain(["Setpoint", 5]) == {
        parser_const.KEY_NAME: "Setpoint",
        parser_const.KEY_VALUE: 5,
        parser_const.KEY_TAIL: None,
    }
    assert mixin.interact_assign_variable([{parser_const.KEY_NAME: "Setpoint", parser_const.KEY_VALUE: 5}]) == {
        parser_const.KEY_ASSIGN: {parser_const.KEY_NAME: "Setpoint", parser_const.KEY_VALUE: 5}
    }
    assert mixin.interact_flag(
        [
            Token(parser_const.KEY_NAME, "Abs_"),
            Token(parser_const.KEY_STRING, "label"),
            {parser_const.KEY_TAIL: "InVar"},
        ]
    ) == {
        parser_const.KEY_NAME: "Abs_",
        parser_const.KEY_EXTRA: "label",
        parser_const.KEY_TAIL: {parser_const.KEY_TAIL: "InVar"},
    }
    assert mixin.interact_value_line([1, 2, 3]) == [1, 2, 3]
    assert mixin.layer_info([Token("JUNK", ":"), 4]) == 4
    assert mixin.seq_control_opt(["SEQ_CONTROL", "SEQTIMER"]).data == parser_const.KEY_SEQ_CONTROL_OPS
    assert mixin.codeblock_coord([Token("LPAR", "("), 1, 2]) == (1.0, 2.0)
    assert mixin.objsizedef([Token("LPAR", "("), 3, 4]) == (3.0, 4.0)
    assert mixin.two_layers([Token("JUNK", ":"), 3.0]) == {parser_const.GRAMMAR_VALUE_TWO_LAYERS: 3.0}
    with pytest.raises(ValueError, match="two_layers expected a numeric"):
        mixin.two_layers(["bad"])

    with pytest.raises(ValueError, match="invar expected"):
        mixin.invar([Token("JUNK", "=")])
    with pytest.raises(ValueError, match="enable_expression expected"):
        mixin.enable_expression([Token("JUNK", "=")])
    with pytest.raises(ValueError, match="interact_assign_variable expected"):
        mixin.interact_assign_variable(["bad"])
    with pytest.raises(ValueError, match="layer_info expected"):
        mixin.layer_info(["bad"])
    with pytest.raises(ValueError, match="codeblock_coord expected 2 coordinate values"):
        mixin.codeblock_coord([1])
    with pytest.raises(ValueError, match="objsizedef expected 2 size values"):
        mixin.objsizedef([1])
