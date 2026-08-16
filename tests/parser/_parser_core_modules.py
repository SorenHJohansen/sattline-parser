# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_modules_mixin_helpers_flatten_nested_module_trees_and_meta_spans():
    meta = SimpleNamespace(line=12, column=4, start_pos=100, end_pos=120)
    nested_tree = Tree(
        parser_const.TREE_TAG_MODULE_BODY,
        ["beta", Tree(parser_const.TREE_TAG_BASE_MODULE_BODY, ["gamma"])],
    )

    assert meta_span(meta) == SourceSpan(start=100, end=120, line=12, column=4)
    assert meta_span(SimpleNamespace(line=None, column=4)) is None
    assert meta_span(SimpleNamespace(line=12, column=4, start_pos=1, end_pos=1)) == SourceSpan(
        start=1, end=1, line=12, column=4
    )
    assert _is_tree(nested_tree) is True
    assert _is_tree("not-a-tree") is False
    assert list(flatten_items(["alpha", ["delta"], nested_tree])) == ["alpha", "delta", "beta", "gamma"]


def test_modules_mixin_module_header_collects_argument_metadata():
    mixin = _ModulesHarness()

    header = mixin.module_header(
        SimpleNamespace(line=5, column=2, start_pos=20, end_pos=30),
        [
            "Motor",
            {
                parser_const.TREE_TAG_INVOKE_COORD: (1, 2, 3, 4, 5),
                parser_const.KEY_TAILS: ["PosX"],
            },
            Tree(
                parser_const.TREE_TAG_ARGUMENTS,
                [
                    7,
                    {
                        parser_const.TREE_TAG_ENABLE: False,
                        parser_const.KEY_TAIL: "EnableVar",
                    },
                    {
                        parser_const.KEY_ASSIGN: {
                            parser_const.KEY_NAME: "Module_In_View",
                            parser_const.KEY_VALUE: True,
                            parser_const.KEY_TAIL: "Allow.RecpSupParameters",
                        },
                    },
                    {parser_const.GRAMMAR_VALUE_ZOOMLIMITS: (0.5, 2.0)},
                    {parser_const.GRAMMAR_VALUE_ZOOMABLE: True},
                    parser_const.GRAMMAR_VALUE_IGNOREMAXMODULE,
                ],
            ),
        ],
    )

    assert header.name == "Motor"
    assert header.declaration_span == SourceSpan(start=20, end=30, line=5, column=2)
    assert header.invoke_coord == (1.0, 2.0, 3.0, 4.0, 5.0)
    assert header.invoke_coord_tails == ["PosX", "Allow.RecpSupParameters"]
    assert header.layer_info == "7"
    assert header.enable is False
    assert header.enable_tail == "EnableVar"
    assert header.zoom_limits == (0.5, 2.0)
    assert header.zoomable is True
    assert header.invocation_arguments == (parser_const.GRAMMAR_VALUE_IGNOREMAXMODULE,)

    tuple_header = mixin.module_header(
        SimpleNamespace(line=6, column=4),
        [
            "Valve",
            (6, 7, 8, 9, 10),
            Tree(parser_const.TREE_TAG_ARGUMENTS, ["FreeArg"]),
        ],
    )

    assert tuple_header.invoke_coord == (6.0, 7.0, 8.0, 9.0, 10.0)
    assert tuple_header.invocation_arguments == ("FreeArg",)

    with pytest.raises(ValueError, match="module_header missing invoke_coord"):
        mixin.module_header(SimpleNamespace(line=1, column=1), ["BrokenHeader"])


def test_modules_mixin_coordinate_helpers_preserve_pairs_tails_and_clipping_tree():
    mixin = _ModulesHarness(["PanelResize"])

    coords = mixin.coordinates([1, 2, "ignored"])
    pair = mixin.origo_size_pair(
        [
            coords,
            {
                parser_const.KEY_COORDS: (3, 4),
                parser_const.KEY_TAILS: ["PanelScale"],
            },
        ]
    )
    invoke = mixin.invoke_coord([1, 2, 3, 4, 5, "ignored"])
    clipping = mixin.coord_clippingbounds([coords])

    assert coords == {parser_const.KEY_COORDS: (1.0, 2.0), parser_const.KEY_TAILS: ["PanelResize"]}
    assert pair == {
        parser_const.KEY_COORDS: ((1.0, 2.0), (3.0, 4.0)),
        parser_const.KEY_TAILS: ["PanelResize", "PanelScale"],
    }
    assert invoke == {
        parser_const.TREE_TAG_INVOKE_COORD: (1.0, 2.0, 3.0, 4.0, 5.0),
        parser_const.KEY_TAILS: ["PanelResize"],
    }
    assert mixin.origo_size_pair([(1.0, 2.0), Tree(parser_const.TREE_TAG_COORDINATES, [3.0, 4.0])]) == {
        parser_const.KEY_COORDS: ((1.0, 2.0), (3.0, 4.0)),
        parser_const.KEY_TAILS: None,
    }
    assert mixin.coord_invar_tail([Token("COMMA", ","), "WidthSource"]) == "WidthSource"
    assert isinstance(clipping, Tree)
    assert clipping.data == parser_const.GRAMMAR_VALUE_CLIPPINGBOUNDS

    with pytest.raises(ValueError, match="coordinates missing REAL values"):
        mixin.coordinates([1])
    with pytest.raises(ValueError, match="origo_size_pair expected 2 coordinate pairs"):
        mixin.origo_size_pair([(1.0, 2.0)])
    with pytest.raises(ValueError, match="invoke_coord expected 5 REALs"):
        mixin.invoke_coord([1.0, 2.0, 3.0, 4.0])


@pytest.mark.parametrize(
    ("frame_marker", "expected_type"),
    [(False, SingleModule), (True, FrameModule)],
)
def test_modules_mixin_invocation_new_module_collects_decls_and_frame_marker(frame_marker, expected_type):
    mixin = _ModulesHarness()
    header = _module_header("Child")
    module_param = Variable(name="Param", datatype="integer")
    local_var = Variable(name="Local", datatype="integer")
    child = ModuleTypeInstance(header=_module_header("Nested"), moduletype_name="NestedType")
    mapping = ParameterMapping(
        target=VarRef("Target"),
        source_type=parser_const.KEY_VALUE,
        is_duration=False,
        is_source_global=False,
        source_literal=1,
    )
    items: list[Any] = [
        header,
        101,
        Tree(parser_const.GRAMMAR_VALUE_MODULEPARAMETERS, [module_param]),
        Tree(parser_const.GRAMMAR_VALUE_LOCALVARIABLES, [local_var]),
        Tree(parser_const.TREE_TAG_SUBMODULES, [child]),
        Tree(parser_const.TREE_TAG_MODULETYPE_PAR_LIST, [mapping]),
        ModuleDef(),
        {"groupconn": VarRef("ScanGroup"), "global": False},
    ]
    if frame_marker:
        items.append(True)

    result = mixin.invocation_new_module(items)

    assert isinstance(result, expected_type)
    assert result.header.groupconn == VarRef("ScanGroup")
    assert result.header.groupconn_global is False
    assert result.datecode == 101
    assert result.submodules == [child]
    if isinstance(result, SingleModule):
        assert result.moduleparameters == [module_param]
        assert result.localvariables == [local_var]
        assert result.parametermappings == [mapping]

    nested_result = mixin.invocation_new_module(
        [
            header,
            101,
            Tree(parser_const.TREE_TAG_SUBMODULES, [[child]]),
            ModuleDef(),
            ModuleCode(),
        ]
    )

    assert [cast(ModuleTypeInstance, sub).moduletype_name for sub in nested_result.submodules] == ["NestedType"]


def test_modules_mixin_base_picture_module_collects_nested_children_and_scan_group():
    mixin = _ModulesHarness()
    header = _module_header("BasePicture")
    datatype = DataType(name="Payload", description=None, datecode=100)
    moduletype = ModuleTypeDef(name="PumpType", datecode=200)
    local_var = Variable(name="Counter", datatype="integer")
    child = ModuleTypeInstance(header=_module_header("Nested"), moduletype_name="NestedType")
    moduledef = ModuleDef()

    result = mixin.base_picture_module(
        [
            header,
            Tree(
                parser_const.TREE_TAG_BASE_MODULE_BODY,
                cast(
                    Any,
                    [
                        Tree(parser_const.TREE_TAG_DATATYPE_LIST, [datatype]),
                        Tree(parser_const.TREE_TAG_MODULETYPE_LIST, [moduletype]),
                        Tree(parser_const.GRAMMAR_VALUE_LOCALVARIABLES, [local_var]),
                        Tree(parser_const.TREE_TAG_SUBMODULES, [[child]]),
                        moduledef,
                        {"groupconn": VarRef("ScanRoot"), "global": True},
                    ],
                ),
            ),
        ]
    )

    assert isinstance(result, BasePicture)
    assert result.datatype_defs == [datatype]
    assert result.moduletype_defs == [moduletype]
    assert result.localvariables == [local_var]
    assert result.submodules == [child]
    assert result.moduledef is moduledef
    assert header.groupconn == VarRef("ScanRoot")
    assert header.groupconn_global is True

    direct_items_result = mixin.base_picture_module([_module_header("BaseDirect"), datatype, moduletype])

    assert direct_items_result.datatype_defs == [datatype]
    assert direct_items_result.moduletype_defs == [moduletype]

    with pytest.raises(ValueError, match="No items in base_picture_module"):
        mixin.base_picture_module([])


def test_modules_mixin_variable_group_and_mapping_helpers_preserve_modifiers_and_state_suffixes():
    mixin = _ModulesHarness()
    parsed_name = mixin.variable_name(
        SimpleNamespace(line=9, column=3, start_pos=90, end_pos=100),
        [
            Token(parser_const.KEY_NAME, "Pump"),
            Token(parser_const.KEY_DOT, "."),
            Token(parser_const.KEY_NAME, "State"),
            Token(parser_const.TOKEN_OLD, ":OLD"),
        ],
    )
    mapping = mixin.moduletype_par_transfer(
        SimpleNamespace(line=9, column=3, start_pos=90, end_pos=100),
        [
            parsed_name,
            True,
            parser_const.GRAMMAR_VALUE_DURATION_VALUE,
            VarRef("SourceVar"),
        ],
    )
    variables = mixin.variable_group(
        [
            ("Alpha", "desc", SourceSpan(start=4, end=5, line=4, column=1)),
            True,
            "integer",
            parser_const.GRAMMAR_VALUE_CONST_KW,
            parser_const.GRAMMAR_VALUE_STATE_KW,
            parser_const.GRAMMAR_VALUE_OPSAVE_KW,
            parser_const.GRAMMAR_VALUE_SECURE_KW,
            ({parser_const.GRAMMAR_VALUE_TIME_VALUE: "T#5S"}, True),
        ]
    )
    list_tree = mixin.variable_list([variables])
    params_tree = mixin.moduleparameters([list_tree])
    locals_tree = mixin.localvariables([list_tree])
    scan_group = mixin.scan_group([True, parsed_name])

    assert parsed_name == VarRef("Pump.State", state="old", span=SourceSpan(start=90, end=100, line=9, column=3))
    assert mapping.target == VarRef("Pump.State", state="old", span=SourceSpan(start=90, end=100, line=9, column=3))
    assert mapping.source == VarRef("SourceVar")
    assert mapping.source_type == parser_const.TREE_TAG_VARIABLE_NAME
    assert mapping.is_duration is True
    assert mapping.is_source_global is True
    assert len(variables) == 1
    assert variables[0].global_var is True
    assert variables[0].const is True
    assert variables[0].state is True
    assert variables[0].opsave is True
    assert variables[0].secure is True
    assert variables[0].init_value == {parser_const.GRAMMAR_VALUE_TIME_VALUE: "T#5S"}
    assert variables[0].init_is_duration is True
    assert params_tree.data == parser_const.GRAMMAR_VALUE_MODULEPARAMETERS
    assert locals_tree.data == parser_const.GRAMMAR_VALUE_LOCALVARIABLES
    assert scan_group == {"groupconn": parsed_name, "global": True}

    string_state_name = mixin.variable_name(
        SimpleNamespace(line=10, column=5, start_pos=50, end_pos=60),
        ["Pump", ".", "State", "new"],
    )

    assert string_state_name == VarRef("Pump.State", state="new", span=SourceSpan(start=50, end=60, line=10, column=5))

    suffix_state_name = mixin.variable_name(
        SimpleNamespace(line=11, column=3, start_pos=70, end_pos=80),
        [
            Token(parser_const.KEY_NAME, "Pump"),
            Token(parser_const.KEY_DOT, "."),
            Token(parser_const.KEY_NAME, "State"),
            Token("STATE_SUFFIX", ":Old"),
        ],
    )
    assert suffix_state_name == VarRef("Pump.State", state="old", span=SourceSpan(start=70, end=80, line=11, column=3))
