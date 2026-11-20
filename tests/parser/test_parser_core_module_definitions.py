# pyright: reportAttributeAccessIssue=false, reportPrivateUsage=false, reportUnknownMemberType=false
from types import SimpleNamespace

import pytest
from lark import Token, Tree
from lark.tree import Meta

from sattline_parser import parse_source_text as parser_core_parse_source_text
from sattline_parser.grammar import constants as parser_const
from sattline_parser.models.ast_model import (
    FrameModule,
    GraphObject,
    InteractObject,
    MappingSource,
    ModuleCode,
    ModuleDef,
    ModuleTypeInstance,
    ParameterMapping,
    SingleModule,
    SourceSpan,
    Variable,
)
from sattline_parser.models.clauses import (
    ClippingClause,
    EnableClause,
    ModuleArguments,
    ModuleInViewClause,
    ModuleMarker,
    ZoomLimits,
)
from sattline_parser.models.expressions import VarRef
from sattline_parser.models.tails import VarTail
from sattline_parser.transformer._module_shared import GLOBAL_KEYWORD, CoordTail, GroupConnInfo, InterimCoords
from sattline_parser.transformer._payloads import Grid, ModuleOptions, TwoLayers, Zoomable
from sattline_parser.transformer._tokens_mixin import DURATION_VALUE_SENTINEL

from ._parser_core_test_support import _module_header, _ModulesHarness


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

    with pytest.raises(ValueError, match="has no name"):
        mixin.moduletype_definition(SimpleNamespace(line=1, column=1), [100])


def test_modules_mixin_reads_one_moduledef_and_modulecode():
    mixin = _ModulesHarness()
    first_def = ModuleDef()
    first_code = ModuleCode()

    single = mixin.invocation_new_module([True, _module_header("Frm"), 101, first_def, first_code])
    assert isinstance(single, FrameModule)
    assert single.moduledef is first_def
    assert single.modulecode is first_code

    moduletype = mixin.moduletype_definition(
        SimpleNamespace(line=1, column=1, start_pos=0, end_pos=1),
        ["PumpType", 400, first_def],
    )
    assert moduletype.moduledef is first_def
    assert moduletype.modulecode is None


def test_a_second_module_block_in_one_body_is_rejected():
    """The grammar allows one block; a transformer regression must fail loudly."""
    mixin = _ModulesHarness()
    module_def = ModuleDef()
    module_code = ModuleCode()

    with pytest.raises(ValueError, match="more than one ModuleDef"):
        mixin.invocation_new_module([True, _module_header("Frm"), module_def, ModuleDef()])
    with pytest.raises(ValueError, match="more than one ModuleCode"):
        mixin.invocation_new_module([True, _module_header("Frm"), module_code, ModuleCode()])


def test_parse_source_text_reads_the_module_layout_and_code():
    bp = parser_core_parse_source_text(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   A: integer := 0;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "EQUATIONBLOCK First COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "   A = 1;\n"
        "ENDDEF (*BasePicture*);\n"
    )

    assert bp.moduledef is not None
    assert bp.modulecode is not None
    assert bp.moduledef.clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))
    assert [eq.name for eq in (bp.modulecode.equationblocks or [])] == ["First"]


def test_modules_mixin_wrapper_rules_and_invocation_errors():
    mixin = _ModulesHarness()
    header = _module_header("Pump")
    parameter_tree = Tree(
        parser_const.TREE_TAG_MODULETYPE_PAR_LIST,
        [
            ParameterMapping(
                target=VarRef("Target"),
                source_type=MappingSource.VARIABLE,
                is_source_global=False,
                is_duration=False,
                source=VarRef("Source"),
            )
        ],
    )

    assert mixin.module_body(["a"]).data == parser_const.TREE_TAG_MODULE_BODY
    assert mixin.base_module_body(["b"]).data == parser_const.TREE_TAG_BASE_MODULE_BODY
    assert mixin.IGNOREMAXMODULE(Token("IGNOREMAXMODULE", "IgnoreMaxModule")) == ModuleMarker(
        parser_const.GRAMMAR_VALUE_IGNOREMAXMODULE
    )
    assert mixin.LAYERMODULE(Token("LAYERMODULE", "LayerModule")) == ModuleMarker(
        parser_const.GRAMMAR_VALUE_LAYERMODULE
    )
    assert mixin.argument([Token("COMMA", ","), "value"]) == "value"
    assert mixin.argument([Token("COMMA", ",")]) is None
    assert mixin.arguments(Meta(), [Token("COMMA", ","), 1, ModuleMarker("SymbolModule")]) == ModuleArguments(
        layer=1, markers=(ModuleMarker("SymbolModule"),)
    )
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
    assert mixin.opt_var_init([None, (5, True)]) == (5, True)
    assert mixin.opt_var_init([None, {parser_const.GRAMMAR_VALUE_TIME_VALUE: "12:00"}]) == (
        {parser_const.GRAMMAR_VALUE_TIME_VALUE: "12:00"},
        False,
    )
    assert mixin.opt_var_init([None, 5]) == (5, False)
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
            GLOBAL_KEYWORD,
            DURATION_VALUE_SENTINEL,
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
    assert int_literal_transfer.source_type == MappingSource.VALUE

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
    mixin = _ModulesHarness()
    graph = GraphObject(type="TextObject", properties={})
    interact = InteractObject(type="Button_", properties={})
    tail = VarTail("in", "TailA")

    assert mixin.origo_coord([1, 2, 3]) == [1, 2, 3]
    assert mixin.size([4, 5]) == [4, 5]
    assert mixin.clippingbounds(
        Meta(), [InterimCoords(coords=((0.0, 0.0), (1.0, 1.0)), tails=[tail])]
    ) == ClippingClause(((0.0, 0.0), (1.0, 1.0)), (tail,))
    assert mixin.zoomlimits(Meta(), [0.5, 2.0]) == ZoomLimits(0.5, 2.0)
    with pytest.raises(ValueError, match="zoomlimits expected two REAL values"):
        mixin.zoomlimits(Meta(), [0.5])
    with pytest.raises(ValueError, match="clippingbounds expected a payload"):
        mixin.clippingbounds(Meta(), [])
    assert mixin.ZOOMABLE(None) == Zoomable()
    assert mixin.grid([Token("JUNK", ","), 0.5, 1.5]) == Grid(1.5)
    assert mixin.two_layers([Token("JUNK", ":"), 3.0]) == TwoLayers(3.0)
    # A singular module option written twice is ambiguous, not last-wins.
    with pytest.raises(ValueError, match="Grid"):
        mixin.moduledef_opts([Grid(0.5), Grid(0.75)])

    moduledef = mixin.moduledef(
        Meta(),
        [
            ClippingClause(((0.0, 0.0), (1.0, 1.0)), (tail,)),
            [graph],
            [interact],
            ModuleOptions(zoom_limits=ZoomLimits(0.5, 2.0), zoomable=True, grid=0.75, layer_limit=3.0),
        ],
    )

    assert moduledef.clipping_bounds == ((0.0, 0.0), (1.0, 1.0))
    assert moduledef.clipping_tails == (tail,)
    assert moduledef.graph_objects == [graph]
    assert moduledef.interact_objects == [interact]
    assert moduledef.zoom_limits == (0.5, 2.0)
    assert moduledef.zoomable is True
    assert moduledef.grid == 0.75
    assert moduledef.layer_limit == 3.0

    # Module options arriving through the real grammar (moduledef_opts /
    # moduledef_option) must reach the ModuleDef, including Two_Layers_ and
    # bare-float grid values.
    option = mixin.moduledef_option([Zoomable(), Grid(0.75)])
    assert option == ModuleOptions(zoomable=True, grid=0.75)
    assert mixin.moduledef_option([0.5]) == ModuleOptions(grid=0.5)
    opts = mixin.moduledef_opts([option, TwoLayers(3.0)])
    assert opts == ModuleOptions(zoomable=True, grid=0.75, layer_limit=3.0)
    options_moduledef = mixin.moduledef(Meta(), [opts])
    assert options_moduledef.zoomable is True
    assert options_moduledef.grid == 0.75
    assert options_moduledef.layer_limit == 3.0

    with pytest.raises(ValueError, match="coord_invar_tail expected"):
        mixin.coord_invar_tail(Meta(), [Token("JUNK", ",")])
    with pytest.raises(ValueError, match="grid expected a numeric value"):
        mixin.grid(["bad"])
    with pytest.raises(ValueError, match="grid expected at least one numeric value"):
        mixin.grid([Token("JUNK", ",")])


def test_modules_mixin_layout_rejects_malformed_payloads():
    mixin = _ModulesHarness()
    pair = mixin.origo_size_pair(["ignored", InterimCoords(coords=(1.0, 2.0)), InterimCoords(coords=(3.0, 4.0))])
    assert pair == InterimCoords(coords=((1.0, 2.0), (3.0, 4.0)))

    assert mixin.coord_invar_tail(Meta(), [Token("OUTVAR_PREFIX", "OutVar_"), "Bound"]) == CoordTail(
        VarTail("out", "Bound")
    )
    with pytest.raises(ValueError, match="expected a literal after InVar_/OutVar_"):
        mixin.coord_invar_tail(Meta(), [Token("INVAR_PREFIX", "InVar_"), object()])
    with pytest.raises(ValueError, match="coord_clippingbounds expected clip values"):
        mixin.coord_clippingbounds([])
    with pytest.raises(ValueError, match="clip_value_tailed expected a REAL value"):
        mixin.clip_value_tailed([])
    with pytest.raises(ValueError, match="clip_value_plain expected a REAL value"):
        mixin.clip_value_plain([])
    with pytest.raises(ValueError, match="clip_value expected a clip value payload"):
        mixin.clip_value([])
    with pytest.raises(ValueError, match="two_layers expected a numeric layer value"):
        mixin.two_layers([])


def test_variable_modifier_scan_stops_at_an_unknown_bare_string():
    from sattline_parser.transformer._module_assembly_mixin import _scan_variable_modifiers  # noqa: PLC0415

    flags, order, index = _scan_variable_modifiers(["NotAModifier"], 0)

    assert not any(flags.values())
    assert order == ()
    assert index == 0


def test_a_bare_time_value_keeps_no_keyword_text() -> None:
    mixin = _ModulesHarness()

    assert mixin.time_value([Token("TIME_VALUE", "Time_Value")]) == {parser_const.GRAMMAR_VALUE_TIME_VALUE: None}
    assert mixin.time_value([Token("TIME_VALUE", "Time_Value"), "1h"]) == {parser_const.GRAMMAR_VALUE_TIME_VALUE: "1h"}


def test_a_bare_duration_value_initializer_keeps_the_marker() -> None:
    mixin = _ModulesHarness()

    variables = mixin.variable_group(
        [
            ("D", None, None),
            "duration",
            (None, True),
        ]
    )

    assert variables[0].init_value is None
    assert variables[0].init_is_duration is True


def test_a_quoted_duration_value_literal_is_not_the_keyword() -> None:
    mixin = _ModulesHarness()

    mapping = mixin.moduletype_par_transfer(
        SimpleNamespace(line=2, column=1, start_pos=10, end_pos=20),
        [VarRef("Target"), "Duration_Value"],
    )

    assert mapping.is_duration is False
    assert mapping.source_literal == "Duration_Value"
    assert mapping.source is None


def test_repeated_singular_header_arguments_are_rejected() -> None:
    mixin = _ModulesHarness()
    meta = SimpleNamespace(line=2, column=1, start_pos=10, end_pos=20)

    cases = [
        (1, 2, "Layer_"),
        (EnableClause(True), EnableClause(False), "Enable_"),
        (ModuleInViewClause(True), ModuleInViewClause(False), "Module_In_View"),
        (ZoomLimits(1.0, 2.0), ZoomLimits(3.0, 4.0), "ZoomLimits"),
    ]
    for first, second, label in cases:
        with pytest.raises(ValueError, match=label):
            mixin.arguments(meta, [first, second])


def test_a_frame_module_keeps_its_parameter_mappings() -> None:
    mixin = _ModulesHarness()
    mapping = ParameterMapping(
        target=VarRef("Target"),
        source_type=MappingSource.VALUE,
        is_source_global=False,
        is_duration=False,
        source_literal=1,
    )
    parameter_tree = Tree(parser_const.TREE_TAG_MODULETYPE_PAR_LIST, [mapping])

    frame = mixin.invocation_new_module([True, _module_header("Frame"), ModuleDef(), parameter_tree])

    assert isinstance(frame, FrameModule)
    assert frame.parametermappings == [mapping]


def test_repeated_singular_module_options_are_rejected() -> None:
    mixin = _ModulesHarness()

    with pytest.raises(ValueError, match="ZoomLimits"):
        mixin.moduledef_opts([ZoomLimits(1.0, 2.0), ZoomLimits(3.0, 4.0)])
    with pytest.raises(ValueError, match="Two_Layers_"):
        mixin.moduledef_opts([TwoLayers(1.0), TwoLayers(2.0)])
    # A repeated marker is idempotent, not ambiguous.
    assert mixin.moduledef_opts([Zoomable(), Zoomable()]) == ModuleOptions(zoomable=True)


def test_an_empty_argument_list_carries_no_span() -> None:
    picture = parser_core_parse_source_text(
        '"SyntaxVersion"\n"OriginalFileDate"\n"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\nClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\nENDDEF (*BasePicture*);\n"
    )

    assert picture.header.arguments.span is None
    assert picture.header.declaration_span is not None
