"""Source spans and bound names on modelled payloads."""

from __future__ import annotations

from sattline_parser import parse_source_text, walk
from sattline_parser.models.ast_model import InteractObject, SourceSpan
from sattline_parser.models.clauses import (
    Alignment,
    AssignClause,
    ClippingClause,
    ColourSpec,
    EnableClause,
    FlagClause,
    ModuleArguments,
    ModuleInViewClause,
    ModuleMarker,
    PickButton,
    ProcedureCall,
    ScaleSelector,
    TailedClause,
    ZoomLimits,
)
from sattline_parser.models.tails import LitStringTail, VarTail

_CODE = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0 : InVar_ "PosX",0.0,0.0,1.0,1.0 Module_In_View = True : OutVar_ "Visible" IgnoreMaxModule ZoomLimits = 0.5 2.0) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
    PosX: integer := 0;
    PanelResize: integer := 0;
    EnableFlag: boolean := False;
ModuleDef
    ClippingBounds = ( -1.0 , -1.0 : InVar_ "PanelResize" ) ( 1.0 , 1.0 )
    GraphObjects :
        RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 )
            Enable_ = True : InVar_ "FlagSym"
            OutlineColour :
                Width_ = 2 : OutVar_ "WidthVar"
    InteractObjects :
        TextBox_ ( 0.0 , 0.0 ) ( 1.0 , 1.0 )
            (* body note *)
            RightAligned
            Enable_ = True : InVar_ "EnableFlag"
            Custom_Flag
            Color_Value = 0 : InVar_ "EnableFlag"
            Format_String_ = "Fmt" : InVar_ LitString "FmtSym"
            IntObjPickButton = "PickVar" VarName
            Relative_
            Value = 0 : InVar_ 2
        ComButProc_ ( 0.0 , 0.0 ) ( 1.0 , 1.0 )
            ToggleWindow 1
ENDDEF (*BasePicture*);
"""


def _nodes(picture: object, node_type: type[object]) -> list[object]:
    return [event.node for event in walk(picture) if isinstance(event.node, node_type)]


def test_every_modelled_payload_carries_a_source_span() -> None:
    picture = parse_source_text(_CODE)
    module_def = picture.moduledef
    assert module_def is not None
    assert module_def.span is not None
    assert module_def.clipping is not None
    assert module_def.clipping.span is not None
    assert picture.header.arguments.span is not None
    assert picture.header.arguments.module_in_view is not None
    assert picture.header.arguments.module_in_view.tail == VarTail("out", "Visible")

    assert picture.header.invoke_coord_tails
    assert all(isinstance(tail, VarTail) and tail.span is not None for tail in picture.header.invoke_coord_tails)
    assert module_def.clipping_tails
    assert all(isinstance(tail, VarTail) and tail.span is not None for tail in module_def.clipping_tails)

    checked: tuple[type[object], ...] = (
        InteractObject,
        Alignment,
        ClippingClause,
        EnableClause,
        AssignClause,
        FlagClause,
        TailedClause,
        ColourSpec,
        ModuleArguments,
        ModuleInViewClause,
        ModuleMarker,
        PickButton,
        ScaleSelector,
        ProcedureCall,
        LitStringTail,
        ZoomLimits,
    )
    for node_type in checked:
        nodes = _nodes(picture, node_type)
        assert nodes, node_type.__name__
        assert all(getattr(node, "span", None) is not None for node in nodes), node_type.__name__

    buttons = [node for node in _nodes(picture, PickButton) if isinstance(node, PickButton)]
    assert buttons
    assert any(button.reference is not None and button.reference.span is not None for button in buttons)


def test_bound_tail_name_covers_name_symbol_and_literal_values() -> None:
    assert VarTail("in", "PosX").bound_name == "PosX"
    assert VarTail("out", LitStringTail("LitString", "Sym")).bound_name == "Sym"
    assert VarTail("in", 3).bound_name is None
    assert VarTail("in", True).bound_name is None
    assert VarTail("in", 2.5).bound_name is None


def test_payload_spans_do_not_participate_in_equality() -> None:
    span = SourceSpan(start=1, end=2, line=1, column=1)

    assert VarTail("in", "PosX", span) == VarTail("in", "PosX")
    assert LitStringTail("LitString", "Sym", span) == LitStringTail("LitString", "Sym")
    assert EnableClause(True, None, span) == EnableClause(True)
    assert Alignment("right", span) == Alignment("right")
