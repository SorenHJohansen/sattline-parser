# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_modules_mixin_definition_trees_keep_only_supported_children():
    mixin = _ModulesHarness()
    record_field = Variable(name="Field", datatype="integer")
    record = mixin.record(
        SimpleNamespace(line=8, column=2, start_pos=80, end_pos=90),
        [
            "Payload",
            "desc",
            300,
            Tree(parser_const.TREE_TAG_VAR_LIST, [record_field]),
        ],
    )
    moduletype = mixin.moduletype_definition(
        SimpleNamespace(line=3, column=1, start_pos=30, end_pos=40),
        [
            "PumpType",
            400,
            Tree(parser_const.GRAMMAR_VALUE_MODULEPARAMETERS, [Variable(name="In", datatype="integer")]),
            Tree(parser_const.GRAMMAR_VALUE_LOCALVARIABLES, [Variable(name="Tmp", datatype="integer")]),
            Tree(
                parser_const.TREE_TAG_SUBMODULES,
                [ModuleTypeInstance(header=_module_header("Nested"), moduletype_name="NestedType")],
            ),
            ModuleDef(),
            GroupConnInfo(VarRef("ScanType"), True),
        ],
    )
    datatype_tree = mixin.datatype_typedefinitions([record, Tree("wrapper", [record])])
    moduletype_tree = mixin.moduletype_definitions(
        [moduletype, Tree(parser_const.TREE_TAG_MODULETYPE_DEFINITION, [moduletype])]
    )
    submodules = mixin.submodules(["ignored", [moduletype.submodules[0]], _module_header("not-a-module")])
    invocation_tail = mixin.invocation_tail([moduletype_tree, Tree(parser_const.TREE_TAG_MODULETYPE_PAR_LIST, [])])

    assert record.name == "Payload"
    assert record.declaration_span == SourceSpan(start=80, end=90, line=8, column=2)
    assert record.var_list == [record_field]
    assert moduletype.groupconn == VarRef("ScanType")
    assert moduletype.groupconn_global is True
    assert datatype_tree.data == parser_const.TREE_TAG_DATATYPE_LIST
    assert datatype_tree.children == [record, record]
    assert moduletype_tree.data == parser_const.TREE_TAG_MODULETYPE_LIST
    assert moduletype_tree.children == [moduletype, moduletype]
    assert submodules.data == parser_const.TREE_TAG_SUBMODULES
    assert submodules.children == [moduletype.submodules[0]]
    assert invocation_tail is not None
    assert invocation_tail.data == parser_const.TREE_TAG_MODULETYPE_PAR_LIST

    direct_nested = mixin.moduletype_definition(
        SimpleNamespace(line=4, column=2),
        [
            "MixerType",
            401,
            Tree(
                parser_const.TREE_TAG_SUBMODULES,
                [[ModuleTypeInstance(header=_module_header("Leaf"), moduletype_name="LeafType")]],
            ),
        ],
    )

    assert [sub.moduletype_name for sub in direct_nested.submodules] == ["LeafType"]

    with pytest.raises(Exception, match="Name cannot be none"):
        mixin.moduletype_definition(SimpleNamespace(line=1, column=1), [100])


def test_modules_mixin_preserves_all_moduledef_and_modulecode_blocks():
    mixin = _ModulesHarness()
    first_def = ModuleDef()
    second_def = ModuleDef()
    first_code = ModuleCode()
    second_code = ModuleCode()

    single = mixin.invocation_new_module(
        [True, _module_header("Frm"), 101, first_def, first_code, second_def, second_code]
    )
    assert isinstance(single, FrameModule)
    assert single.moduledefs == [first_def, second_def]
    assert single.modulecodes == [first_code, second_code]
    assert single.moduledef is second_def
    assert single.modulecode is second_code

    moduletype = mixin.moduletype_definition(
        SimpleNamespace(line=1, column=1, start_pos=0, end_pos=1),
        ["PumpType", 400, first_def, second_def],
    )
    assert moduletype.moduledefs == [first_def, second_def]
    assert moduletype.moduledef is second_def
    assert moduletype.modulecodes == []
    assert moduletype.modulecode is None


def test_parse_source_text_preserves_all_moduledef_blocks_in_source_order():
    # Regression: legacy coded files repeat one "ModuleDef ... ModuleCode ...
    # ENDDEF" block per layer inside a single module body. Only the last block
    # used to survive; now every block is retained in source order.
    bp = parser_core_parse_source_text(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   A: integer := 0;\n"
        "   B: integer := 0;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "EQUATIONBLOCK First COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "   A = 1;\n"
        "ENDDEF\n"
        "ModuleDef\n"
        "ClippingBounds = ( -2.0 , -2.0 ) ( 2.0 , 2.0 )\n"
        "ModuleCode\n"
        "EQUATIONBLOCK Second COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "   B = 2;\n"
        "ENDDEF (*BasePicture*);\n"
    )

    assert len(bp.moduledefs) == 2
    assert len(bp.modulecodes) == 2
    assert bp.moduledefs[0].clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))
    assert bp.moduledefs[1].clipping_bounds == ((-2.0, -2.0), (2.0, 2.0))
    assert [eq.name for mc in bp.modulecodes for eq in (mc.equations or [])] == ["First", "Second"]
    assert bp.moduledef is bp.moduledefs[-1]
    assert bp.modulecode is bp.modulecodes[-1]


def test_modules_mixin_wrapper_rules_and_invocation_errors():
    mixin = _ModulesHarness()
    header = _module_header("Pump")
    parameter_tree = Tree(
        parser_const.TREE_TAG_MODULETYPE_PAR_LIST,
        [
            ParameterMapping(
                target=VarRef("Target"),
                source_type=parser_const.TREE_TAG_VARIABLE_NAME,
                is_source_global=False,
                is_duration=False,
                source=VarRef("Source"),
            )
        ],
    )

    assert mixin.module_body(["a"]).data == parser_const.TREE_TAG_MODULE_BODY
    assert mixin.base_module_body(["b"]).data == parser_const.TREE_TAG_BASE_MODULE_BODY
    assert mixin.IGNOREMAXMODULE(None) == parser_const.GRAMMAR_VALUE_IGNOREMAXMODULE
    assert mixin.LAYERMODULE(None) == parser_const.GRAMMAR_VALUE_LAYERMODULE
    assert mixin.argument([Token("COMMA", ","), "value"]) == "value"
    assert mixin.argument([Token("COMMA", ",")]) is None
    assert mixin.arguments([Token("COMMA", ","), 1, "two"]).children == [1, "two"]
    assert mixin.frame_module([]) is True
    assert mixin.invocation_module_type([header, "PumpType", parameter_tree]).moduletype_name == "PumpType"
    assert isinstance(mixin.invocation_new_module([True, header, 101, ModuleDef(), ModuleCode()]), FrameModule)
    assert isinstance(
        mixin.invocation_new_module(
            [
                header,
                101,
                Tree(parser_const.GRAMMAR_VALUE_MODULEPARAMETERS, [Variable(name="In", datatype="integer")]),
                Tree(parser_const.GRAMMAR_VALUE_LOCALVARIABLES, [Variable(name="Tmp", datatype="integer")]),
                parameter_tree,
                ModuleDef(),
                ModuleCode(),
            ]
        ),
        SingleModule,
    )

    with pytest.raises(ValueError, match="Missing module header"):
        mixin.invocation_new_module([101])
    with pytest.raises(ValueError, match="Missing module header"):
        mixin.invocation_module_type(["PumpType"])
    with pytest.raises(ValueError, match="Missing module type name"):
        mixin.invocation_module_type([header])


def test_modules_mixin_transfer_and_variable_helpers_cover_fallback_branches():
    mixin = _ModulesHarness()

    assert mixin.opt_var_init([]) is None
    assert mixin.opt_var_init([parser_const.GRAMMAR_VALUE_DURATION_VALUE, 5]) == (5, True)
    assert mixin.time_value(["T#10S"]) == {parser_const.GRAMMAR_VALUE_TIME_VALUE: "T#10S"}
    assert mixin.variable_list([[Variable(name="A", datatype="integer")], None]).data == parser_const.TREE_TAG_VAR_LIST
    assert (
        mixin.moduleparameters([Tree(parser_const.TREE_TAG_VAR_LIST, [Variable(name="A", datatype="integer")])]).data
        == parser_const.GRAMMAR_VALUE_MODULEPARAMETERS
    )
    assert (
        mixin.localvariables([Tree(parser_const.TREE_TAG_VAR_LIST, [Variable(name="B", datatype="integer")])]).data
        == parser_const.GRAMMAR_VALUE_LOCALVARIABLES
    )
    assert mixin.submodules(["ignored", [_module_header("Nope")]]).children == []

    duration_transfer = mixin.moduletype_par_transfer(
        SimpleNamespace(line=3, column=1, start_pos=30, end_pos=31),
        [
            VarRef("Target"),
            True,
            parser_const.GRAMMAR_VALUE_DURATION_VALUE,
            {parser_const.GRAMMAR_VALUE_TIME_VALUE: "T#5S"},
        ],
    )

    assert duration_transfer.is_source_global is True
    assert duration_transfer.is_duration is True
    assert duration_transfer.source_literal == {parser_const.GRAMMAR_VALUE_TIME_VALUE: "T#5S"}
    assert duration_transfer.span == SourceSpan(start=30, end=31, line=3, column=1)
    with pytest.raises(ValueError, match="unexpected source"):
        mixin.moduletype_par_transfer(SimpleNamespace(line=4, column=1), [VarRef("Target"), object()])
    with pytest.raises(ValueError, match="target must be a VarRef"):
        mixin.moduletype_par_transfer(SimpleNamespace(line=5, column=1), ["TargetLiteral", "SourceLiteral"])
    with pytest.raises(ValueError, match="target must be a VarRef"):
        mixin.moduletype_par_transfer(SimpleNamespace(line=6, column=1), [123, "SourceLiteral"])
    assert mixin.moduletype_par_list([duration_transfer]).data == parser_const.TREE_TAG_MODULETYPE_PAR_LIST

    int_literal_transfer = mixin.moduletype_par_transfer(
        SimpleNamespace(line=2, column=1, start_pos=20, end_pos=21),
        [VarRef("Target"), 42],
    )
    assert int_literal_transfer.source_literal == 42
    assert int_literal_transfer.source_type == parser_const.KEY_VALUE

    assert mixin.variable_group([]) == []
    literal_init_variables = mixin.variable_group(
        [("Beta", None, SourceSpan(start=2, end=3, line=2, column=2)), "integer", 7]
    )
    assert literal_init_variables[0].init_value == 7
    assert literal_init_variables[0].init_is_duration is False

    with pytest.raises(ValueError, match="moduletype_par_transfer received empty items"):
        mixin.moduletype_par_transfer(SimpleNamespace(line=1, column=1), [])
    with pytest.raises(ValueError, match="moduletype_par_transfer missing target variable_name"):
        mixin.moduletype_par_transfer(SimpleNamespace(line=1, column=1), [None])
    with pytest.raises(ValueError, match="Expected datatype NAME in variable_group"):
        mixin.variable_group([("Alpha", None, SourceSpan(start=1, end=2, line=1, column=1)), 123])
    with pytest.raises(ValueError, match="record is missing datatype name"):
        mixin.record(SimpleNamespace(line=1, column=1), [100])


def test_modules_mixin_layout_helpers_cover_moduledef_and_numeric_errors():
    mixin = _ModulesHarness(["CoordTail"])
    graph = GraphObject(type="TextObject", properties={})
    interact = InteractObject(type="Button_", properties={})

    assert mixin.origo_coord([1, 2, 3]) == [1, 2, 3]
    assert mixin.size([4, 5]) == [4, 5]
    assert mixin.clippingbounds([InterimCoords(coords=((0.0, 0.0), (1.0, 1.0)), tails=["TailA"])]) == {
        parser_const.GRAMMAR_VALUE_CLIPPINGBOUNDS: ((0.0, 0.0), (1.0, 1.0)),
        parser_const.KEY_TAILS: ["TailA"],
    }
    assert mixin.clippingbounds([((0.0, 0.0), (1.0, 1.0))]) == {
        parser_const.GRAMMAR_VALUE_CLIPPINGBOUNDS: ((0.0, 0.0), (1.0, 1.0))
    }
    assert mixin.seq_layers(["LayerA"]) == {parser_const.KEY_SEQ_LAYERS: "LayerA"}
    assert mixin.zoomlimits([0.5, 2.0]) == {parser_const.GRAMMAR_VALUE_ZOOMLIMITS: (0.5, 2.0)}
    with pytest.raises(ValueError, match="zoomlimits expected two REAL values"):
        mixin.zoomlimits([0.5])
    with pytest.raises(ValueError, match="clippingbounds expected a payload"):
        mixin.clippingbounds([])
    assert mixin.ZOOMABLE(None) == {parser_const.GRAMMAR_VALUE_ZOOMABLE: True}
    assert mixin.grid([Token("JUNK", ","), 0.5, 1.5]) == 1.5
    assert mixin.moduledef_opts_seq(
        [{parser_const.GRAMMAR_VALUE_GRID: 0.5}, {parser_const.KEY_SEQ_LAYERS: "LayerA"}]
    ).children == [{parser_const.GRAMMAR_VALUE_GRID: 0.5, parser_const.KEY_SEQ_LAYERS: "LayerA"}]

    moduledef = mixin.moduledef(
        [
            {parser_const.GRAMMAR_VALUE_CLIPPINGBOUNDS: ((0.0, 0.0), (1.0, 1.0)), parser_const.KEY_TAILS: ["TailA"]},
            [graph],
            [interact],
            {parser_const.GRAMMAR_VALUE_ZOOMLIMITS: (0.5, 2.0)},
            {parser_const.GRAMMAR_VALUE_ZOOMABLE: True},
            {parser_const.GRAMMAR_VALUE_GRID: 0.75},
            {parser_const.KEY_SEQ_LAYERS: {"top": 1.0}},
        ]
    )

    assert moduledef.clipping_bounds == ((0.0, 0.0), (1.0, 1.0))
    assert moduledef.properties[parser_const.KEY_TAILS] == ["TailA"]
    assert moduledef.graph_objects == [graph]
    assert moduledef.interact_objects == [interact]
    assert moduledef.zoom_limits == (0.5, 2.0)
    assert moduledef.zoomable is True
    assert moduledef.grid == 0.75
    assert moduledef.seq_layers == {"top": 1.0}

    tuple_moduledef = mixin.moduledef([((2.0, 2.0), (3.0, 3.0))])
    assert tuple_moduledef.clipping_bounds == ((2.0, 2.0), (3.0, 3.0))

    # Module options arriving through the real grammar (moduledef_opts /
    # moduledef_option) must reach the ModuleDef, including Two_Layers_ and
    # bare-float grid values.
    option = mixin.moduledef_option([{parser_const.GRAMMAR_VALUE_ZOOMABLE: True}, 0.75])
    assert option == {parser_const.GRAMMAR_VALUE_ZOOMABLE: True, parser_const.GRAMMAR_VALUE_GRID: 0.75}
    opts = mixin.moduledef_opts([option, {parser_const.GRAMMAR_VALUE_TWO_LAYERS: 3.0}])
    assert opts[parser_const.GRAMMAR_VALUE_TWO_LAYERS] == 3.0
    options_moduledef = mixin.moduledef([opts])
    assert options_moduledef.zoomable is True
    assert options_moduledef.grid == 0.75
    assert options_moduledef.seq_layers == 3.0

    with pytest.raises(ValueError, match="coord_invar_tail expected"):
        mixin.coord_invar_tail([Token("JUNK", ",")])
    with pytest.raises(ValueError, match="grid expected a numeric value"):
        mixin.grid(["bad"])
    with pytest.raises(ValueError, match="grid expected at least one numeric value"):
        mixin.grid([Token("JUNK", ",")])
