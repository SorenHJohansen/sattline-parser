# pyright: reportMissingParameterType=false, reportPrivateUsage=false, reportUnknownParameterType=false
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lark import Token, Tree
from lark.tree import Meta

from sattline_parser import parse_source_text
from sattline_parser.grammar import constants as parser_const
from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    FrameModule,
    MappingSource,
    ModuleCode,
    ModuleDef,
    ModuleTypeDef,
    ModuleTypeInstance,
    ParameterMapping,
    SingleModule,
    SourceSpan,
    Variable,
)
from sattline_parser.models.clauses import (
    AssignClause,
    EnableClause,
    ModuleArguments,
    ModuleInViewClause,
    ModuleMarker,
    ZoomLimits,
)
from sattline_parser.models.expressions import VarRef
from sattline_parser.models.tails import VarTail
from sattline_parser.transformer._module_shared import (
    GLOBAL_KEYWORD,
    CoordTail,
    GroupConnInfo,
    InterimCoords,
    flatten_items,
    meta_span,
)
from sattline_parser.transformer._payloads import ClipValue, CoordinateClipping, Zoomable
from sattline_parser.transformer.sl_transformer import _is_tree

from ._parser_core_test_support import _module_header, _ModulesHarness


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
            InterimCoords(coords=(1, 2, 3, 4, 5), tails=[VarTail("in", "PosX")]),
            ModuleArguments(
                layer=7,
                enable=EnableClause(False, VarTail("in", "EnableVar")),
                module_in_view=ModuleInViewClause(True, VarTail("out", "Allow.RecpSupParameters")),
                zoom_limits=ZoomLimits(0.5, 2.0),
                zoomable=True,
                markers=(ModuleMarker(parser_const.GRAMMAR_VALUE_IGNOREMAXMODULE),),
                assigns=(AssignClause("Param1", 5, VarTail("in", "AssignTail")),),
            ),
        ],
    )

    assert header.name == "Motor"
    assert header.declaration_span == SourceSpan(start=20, end=30, line=5, column=2)
    assert header.invoke_coord == (1.0, 2.0, 3.0, 4.0, 5.0)
    assert header.invoke_coord_tails == [VarTail("in", "PosX")]
    assert header.arguments.module_in_view == ModuleInViewClause(True, VarTail("out", "Allow.RecpSupParameters"))
    assert header.arguments.assigns == (AssignClause("Param1", 5, VarTail("in", "AssignTail")),)
    assert header.layer_info == 7
    assert header.enable is False
    assert header.enable_tail == VarTail("in", "EnableVar")
    assert header.zoom_limits == (0.5, 2.0)
    assert header.zoomable is True
    assert header.invocation_arguments == (parser_const.GRAMMAR_VALUE_IGNOREMAXMODULE,)

    tuple_header = mixin.module_header(
        SimpleNamespace(line=6, column=4),
        [
            "Valve",
            InterimCoords(coords=(6, 7, 8, 9, 10)),
            ModuleArguments(markers=(ModuleMarker("FreeArg"),)),
        ],
    )

    assert tuple_header.invoke_coord == (6.0, 7.0, 8.0, 9.0, 10.0)
    assert tuple_header.invocation_arguments == ("FreeArg",)

    with pytest.raises(ValueError, match="module_header missing invoke_coord"):
        mixin.module_header(SimpleNamespace(line=1, column=1), ["BrokenHeader"])


def test_modules_mixin_arguments_collect_every_typed_argument_kind():
    mixin = _ModulesHarness()
    args = mixin.arguments(
        Meta(),
        [
            Token("JUNK", ","),
            3,
            EnableClause(True, VarTail("in", "E")),
            ModuleInViewClause(False, VarTail("out", "V")),
            ZoomLimits(1.0, 2.0),
            Zoomable(),
            ModuleMarker("SymbolModule"),
            AssignClause("Field", 1, VarTail("in", "A")),
        ],
    )

    assert args == ModuleArguments(
        layer=3,
        enable=EnableClause(True, VarTail("in", "E")),
        module_in_view=ModuleInViewClause(False, VarTail("out", "V")),
        zoom_limits=ZoomLimits(1.0, 2.0),
        zoomable=True,
        markers=(ModuleMarker("SymbolModule"),),
        assigns=(AssignClause("Field", 1, VarTail("in", "A")),),
    )


def test_modules_mixin_coordinate_helpers_preserve_pairs_tails_and_clipping_tree():
    mixin = _ModulesHarness()
    coord_tail = CoordTail(VarTail("in", "PanelResize"))

    coords = mixin.coordinates([1, 2, coord_tail])
    pair = mixin.origo_size_pair(
        [
            coords,
            InterimCoords(coords=(3, 4), tails=[VarTail("in", "PanelScale")]),
        ]
    )
    invoke = mixin.invoke_coord([1, 2, 3, 4, 5, coord_tail])
    clipping = mixin.coord_clippingbounds([CoordinateClipping((ClipValue(1.0),))])

    assert coords == InterimCoords(
        coords=(1.0, 2.0),
        tails=[VarTail("in", "PanelResize")],
        coord_tails=((), (VarTail("in", "PanelResize"),)),
    )
    assert pair == InterimCoords(
        coords=((1.0, 2.0), (3.0, 4.0)),
        tails=[VarTail("in", "PanelResize"), VarTail("in", "PanelScale")],
    )
    assert invoke == InterimCoords(
        coords=(1.0, 2.0, 3.0, 4.0, 5.0),
        tails=[VarTail("in", "PanelResize")],
        coord_tails=((), (), (), (), (VarTail("in", "PanelResize"),)),
    )
    assert mixin.origo_size_pair([InterimCoords(coords=(1.0, 2.0)), InterimCoords(coords=(3.0, 4.0))]) == (
        InterimCoords(coords=((1.0, 2.0), (3.0, 4.0)), tails=None)
    )
    assert mixin.coord_invar_tail(Meta(), [Token("COMMA", ","), "WidthSource"]) == CoordTail("WidthSource")
    assert clipping == CoordinateClipping((ClipValue(1.0),))

    assert mixin.coordinates([1, 2, 3]).coord_tails == ((), ())

    with pytest.raises(ValueError, match="coordinates missing REAL values"):
        mixin.coordinates([1])
    with pytest.raises(ValueError, match="origo_size_pair expected 2 coordinate pairs"):
        mixin.origo_size_pair([InterimCoords(coords=(1.0, 2.0))])
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
        source_type=MappingSource.VALUE,
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
        GroupConnInfo(VarRef("ScanGroup"), False),
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
                        GroupConnInfo(VarRef("ScanRoot"), True),
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
            Token("STATE_SUFFIX", ":OLD"),
        ],
    )
    mapping = mixin.moduletype_par_transfer(
        SimpleNamespace(line=9, column=3, start_pos=90, end_pos=100),
        [
            parsed_name,
            GLOBAL_KEYWORD,
            parser_const.GRAMMAR_VALUE_DURATION_VALUE,
            VarRef("SourceVar"),
        ],
    )
    variables = mixin.variable_group(
        [
            ("Alpha", "desc", SourceSpan(start=4, end=5, line=4, column=1)),
            GLOBAL_KEYWORD,
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
    scan_group = mixin.scan_group([GLOBAL_KEYWORD, parsed_name])

    assert parsed_name == VarRef("Pump.State", state="old", span=SourceSpan(start=90, end=100, line=9, column=3))
    assert mapping.target == VarRef("Pump.State", state="old", span=SourceSpan(start=90, end=100, line=9, column=3))
    assert mapping.source == VarRef("SourceVar")
    assert mapping.source_type is MappingSource.VARIABLE
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
    assert scan_group == GroupConnInfo(parsed_name, True)

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


def test_a_falsy_parameter_mapping_literal_is_kept() -> None:
    source = """\"Syntax version\"
\"Original file date: ---\"
\"Program date: ---, name: T\"
BasePicture Invocation ( 0.0,0.0,0.0,1.0,1.0 ) : MODULEDEFINITION DateCode_ 1
TYPEDEFINITIONS
   MT = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      P: integer;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*MT*);
SUBMODULES
   A Invocation ( 0.0,0.0,0.0,1.0,1.0 ) : MT ( P => False, P => True, P => 0, P => \"\");
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""

    picture = parse_source_text(source, log_failures=False)

    instance = picture.submodules[0]
    assert isinstance(instance, ModuleTypeInstance)
    assert [mapping.source_literal for mapping in instance.parametermappings] == [False, True, 0, ""]
    assert not any(mapping.is_source_global for mapping in instance.parametermappings)
