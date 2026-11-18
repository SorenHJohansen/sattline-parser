# pyright: reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Branch coverage for the whole-file formatter's less common shapes."""

from __future__ import annotations

import pytest

from sattline_parser.api import parse_source_text
from sattline_parser.ast import (
    Alignment,
    AssignClause,
    BasePicture,
    ClippingClause,
    CodeComment,
    ColourSpec,
    EnableClause,
    Equation,
    FlagClause,
    GraphObject,
    InteractObject,
    LitStringTail,
    MappingSource,
    ModuleArguments,
    ModuleCode,
    ModuleDef,
    ModuleHeader,
    ModuleInViewClause,
    ModuleMarker,
    ParameterMapping,
    PickButton,
    ProcedureCall,
    ScaleSelector,
    Sequence,
    TailedClause,
    Variable,
    VarRef,
    VarTail,
    ZoomLimits,
)
from sattline_parser.formatting import UnsupportedFormattingError, format_module, format_source
from sattline_parser.formatting import source as fmt

_MIN = """"Syntax version 2.23"
"Original file date: ---"
"Program date: ---, name: T"
BasePicture Invocation ( 0.0, 0.0, 0.0, 1.0, 1.0 ) : MODULEDEFINITION DateCode_ 1
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""


def _picture() -> BasePicture:
    return parse_source_text(_MIN, log_failures=False)


def test_printer_emits_blank_lines() -> None:
    printer = fmt._Printer()

    printer.emit(0, "")
    printer.emit_block(0, "\nsecond")

    assert printer.render() == "\n\nsecond\n"


def test_a_picture_without_header_info_uses_the_placeholder_header() -> None:
    picture = _picture()
    picture.header_info = None
    picture.moduledef = None
    picture.modulecode = None

    text = format_source(picture)

    assert text.startswith('" Syntax version 2.23"')


def test_a_duration_init_value_that_is_not_text_is_rendered_verbatim() -> None:
    assert fmt._init_value_text(_variable(init_value=5, init_is_duration=True)) == "5"


def test_a_time_payload_without_text_is_the_keyword_alone() -> None:
    assert fmt._init_value_text(_variable(init_value={"Time_Value": None})) == "Time_Value"


def test_a_multi_key_time_payload_raises() -> None:
    with pytest.raises(UnsupportedFormattingError, match="multi-key"):
        fmt._init_value_text(_variable(init_value={"A": "1", "B": "2"}))


def test_a_layer_limit_is_written_as_two_layers() -> None:
    assert "Two_Layers_ LayerLimit_ = 3.0" in format_module(ModuleDef(layer_limit=3.0))


def test_an_empty_equation_is_written_as_a_bare_header() -> None:
    module = ModuleDef()
    code = ModuleCode(equationblocks=[Equation(name=None, position=None, size=None, code=[])])

    text = _render(module, code)

    assert "EQUATIONBLOCK :\n" in text
    # An invented ``(* empty *)`` became a real comment node on reparse.
    assert "(* empty *)" not in text


def test_a_comment_in_a_sequence_body_is_written_once() -> None:
    module = ModuleDef()
    code = ModuleCode(
        sequences=[
            Sequence(
                name=None,
                type="SEQUENCE",
                position=(0.0, 0.0),
                size=(1.0, 1.0),
                code=[CodeComment("(* note *)")],
            )
        ]
    )

    text = _render(module, code)

    assert "(* note *)" in text


def test_header_arguments_are_all_written() -> None:
    header = ModuleHeader(
        name="Unit",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        arguments=ModuleArguments(
            layer=2,
            enable=EnableClause(enabled=True),
            module_in_view=ModuleInViewClause(in_view=False, tail=VarTail("in", "Flag")),
            zoom_limits=ZoomLimits(minimum=1.0, maximum=4.0),
            zoomable=True,
            markers=(ModuleMarker("SymbolModule"),),
            assigns=(AssignClause(name="Gain", value=2),),
        ),
    )
    picture = _picture()
    picture.header = header
    picture.moduledef = None
    picture.modulecode = None

    text = format_source(picture)

    assert "Layer_ = 2" in text
    assert "Enable_ = True" in text
    assert 'Module_In_View = False : InVar_ "Flag"' in text
    assert "ZoomLimits = 1.0 4.0" in text
    assert "Zoomable" in text
    assert "SymbolModule" in text
    assert "Gain = 2" in text


def test_graph_object_shapes_are_written() -> None:
    module = ModuleDef(
        graph_objects=[
            GraphObject("CompositeObject", {"layer": 3}),
            GraphObject("CompositeObject", {}),
            GraphObject("ConnectionNode", {}),
            GraphObject("ConnectionNode", {"coords": (1.0, 2.0)}),
            GraphObject("SegmentObject", {"coords": (0.0, 0.0), "segment_point": (1.0, 1.0)}),
        ]
    )

    text = format_module(module)

    assert "CompositeObject Layer_ = 3" in text
    assert "ConnectionNode ( 1.0 , 2.0 )" in text
    assert "SegmentObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 )" in text


def test_a_colour_width_is_written() -> None:
    colour = ColourSpec(
        kind="outline",
        width=TailedClause(key="Width_", value=2),
        assignments=(TailedClause(key="Colour0", value=-3),),
        style=TailedClause(key="ColourStyle", value=1.0),
    )

    assert fmt._colour_text(colour) == "OutlineColour : Width_ = 2 Colour0 = -3 ColourStyle = 1.0"


def test_every_interactor_body_entry_shape_is_written() -> None:
    interact = InteractObject(
        "ComBut_",
        {
            "coords": [(0.0, 0.0)],
            "body": [
                2,
                CodeComment("(* note *)"),
                Alignment("center"),
                PickButton("Target", VarRef("TargetRef")),
                PickButton("Other", None),
                TailedClause("Width_", 3),
                ScaleSelector("relative"),
                VarTail("out", "Result"),
            ],
        },
    )
    module = ModuleDef(interact_objects=[interact])

    text = format_module(module)

    assert "ComBut_ ( 0.0 , 0.0 )" in text
    assert "Layer_ = 2" in text
    assert "CenterAligned" in text
    assert 'IntObjPickButton = "Target" VarName' in text
    assert "Width_ = 3" in text
    assert "Relative_" in text
    assert ' : OutVar_ "Result"' in text


def test_the_flat_interactor_clause_lists_are_written() -> None:
    interact = InteractObject(
        "ComButProc_",
        {
            "coords": [(0.0, 0.0)],
            "procedure": ProcedureCall("ToggleWindow"),
            "layers": [1],
            "assigns": [AssignClause("Variable", 0.0)],
            "enables": [EnableClause(enabled=False)],
            "flags": [FlagClause("Visible_")],
            "colours": [ColourSpec(kind="fill", width=None, assignments=(), style=None)],
        },
    )

    text = format_module(ModuleDef(interact_objects=[interact]))

    assert "ComButProc_ ( 0.0 , 0.0 ) ToggleWindow" in text
    assert "Layer_ = 1" in text
    assert "Visible_" in text
    assert "FillColour :" in text
    assert "Variable =" in text


def test_a_procedure_tail_argument_keeps_its_colon() -> None:
    procedure = ProcedureCall("Call", (VarTail("in", "Arg"),))

    assert fmt._procedure_text(procedure) == 'Call : InVar_ "Arg"'


def test_coordinate_helpers_reject_unknown_shapes() -> None:
    with pytest.raises(UnsupportedFormattingError, match="coordinate shape"):
        fmt._tailed_coords_text((1.0,), (), 0)
    with pytest.raises(UnsupportedFormattingError, match="coordinate number"):
        fmt._as_float("nope")
    assert fmt._is_pair(1) is False


def test_a_single_coordinate_pair_is_written_as_one_pair() -> None:
    assert fmt._tailed_coords_text((1.0, 2.0), (), 0) == "( 1.0 , 2.0 )"


def test_a_bare_connection_node_is_written_without_coordinates() -> None:
    assert fmt._connection_node_text(GraphObject("ConnectionNode", {})) == "ConnectionNode"


def test_a_litstring_bound_tail_is_written_as_the_marker_and_text() -> None:
    tail = VarTail("in", LitStringTail("LitString", "Text"))

    assert fmt._tail_text(tail, parenthesised=False) == ' : InVar_ LitString "Text"'


def test_value_and_expression_text_cover_every_leaf() -> None:
    assert fmt._value_or_expression_text(VarRef("X")) == "X"
    assert fmt._value_text(None) == "0"
    assert fmt._value_text(7) == "7"
    assert fmt._value_text(1.5) == "1.5"
    assert fmt._value_text(object()) != ""


def _variable(*, init_value: object = None, init_is_duration: bool = False):
    return Variable(
        name="V",
        datatype="integer",
        init_value=init_value,  # pyright: ignore[reportArgumentType]
        init_is_duration=init_is_duration,
    )


def _render(module: ModuleDef, code: ModuleCode) -> str:
    picture = _picture()
    picture.moduledef = module
    picture.modulecode = code
    return format_source(picture)


def test_a_bare_litstring_tail_is_written() -> None:
    assert fmt._tail_text(LitStringTail("LitString", "Text"), parenthesised=False) == ' : LitString "Text"'


def test_a_procedure_expression_argument_is_written() -> None:
    procedure = ProcedureCall("Call", (VarRef("X"),))

    assert fmt._procedure_text(procedure) == "Call : (X)"


def test_a_clipping_clause_without_corner_groups_raises() -> None:
    module = ModuleDef(clipping=ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (VarTail("in", "ClipX"),)))

    with pytest.raises(UnsupportedFormattingError, match="clipping tails"):
        format_module(module)


def test_a_mapping_without_a_source_raises() -> None:
    mapping = ParameterMapping(
        target=VarRef("P"),
        source_type=MappingSource.VALUE,
        is_duration=False,
        is_source_global=False,
    )

    with pytest.raises(UnsupportedFormattingError, match="no source literal"):
        fmt._mapping_text(mapping)


def test_an_interactor_tail_without_an_owning_clause_raises() -> None:
    interact = InteractObject("ComBut_", {"coords": [], "body": [], "tails": [VarTail("in", "X")]})

    with pytest.raises(UnsupportedFormattingError, match="not attached"):
        format_module(ModuleDef(interact_objects=[interact]))


def test_an_interactor_whose_orders_disagree_raises() -> None:
    first = VarTail("in", "First")
    second = VarTail("in", "Second")
    interact = InteractObject(
        "ComButProc_",
        {
            "assigns": [
                AssignClause("A", 0, tail=first),
                AssignClause("B", 0, tail=second),
            ],
            "tails": [second, first],
        },
    )

    with pytest.raises(UnsupportedFormattingError, match="order"):
        format_module(ModuleDef(interact_objects=[interact]))


def test_tailed_coordinates_reject_an_unknown_shape() -> None:
    with pytest.raises(UnsupportedFormattingError, match="coordinate shape"):
        fmt._tailed_coords_text("nope", (), 0)


def test_a_graph_object_tail_without_an_owning_clause_raises() -> None:
    graph_object = GraphObject(
        "RectangleObject",
        {"coords": ((0.0, 0.0), (1.0, 1.0)), "tails": [VarTail("in", "X")]},
    )

    with pytest.raises(UnsupportedFormattingError, match="not attached"):
        format_module(ModuleDef(graph_objects=[graph_object]))


def test_graph_and_interact_coordinate_tails_are_written_after_their_values() -> None:
    tail = VarTail("in", "Anchor")
    graph_object = GraphObject(
        "RectangleObject",
        {
            "coords": ((0.0, 0.0), (1.0, 1.0)),
            "coord_tails": ((), (), (), (tail,)),
            "tails": [tail],
        },
    )
    interact = InteractObject(
        "TextBox_",
        {
            "coords": [(0.0, 0.0)],
            "coord_tails": ((), (tail,)),
            "tails": [tail],
            "body": [],
        },
    )

    text = format_module(ModuleDef(graph_objects=[graph_object], interact_objects=[interact]))

    assert 'RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 : InVar_ "Anchor" )' in text
    assert 'TextBox_ ( 0.0 , 0.0 : InVar_ "Anchor" )' in text


def test_a_header_with_a_partially_grouped_tail_raises() -> None:
    tail = VarTail("in", "PosX")
    picture = _picture()
    picture.header.invoke_coord_tails = [tail]
    picture.header.coordinate_tails = ((), (), (), (), ())
    picture.moduledef = None
    picture.modulecode = None

    with pytest.raises(UnsupportedFormattingError, match="coordinate tails"):
        format_source(picture)


def test_a_clipping_clause_with_a_partially_grouped_tail_raises() -> None:
    tail = VarTail("in", "ClipX")

    with pytest.raises(UnsupportedFormattingError, match="clipping tails"):
        format_module(
            ModuleDef(clipping=ClippingClause(((-1.0, -1.0), (1.0, 1.0)), (tail,), corner_tails=((), (), (), ())))
        )


def test_more_than_two_header_description_comments_raise() -> None:
    picture = _picture()
    picture.header.description_comments = [
        CodeComment("(* one *)"),
        CodeComment("(* two *)"),
        CodeComment("(* three *)"),
    ]

    with pytest.raises(UnsupportedFormattingError, match="one comment position"):
        format_source(picture)
