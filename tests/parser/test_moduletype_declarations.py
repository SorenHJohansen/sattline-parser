# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false

"""Module-type declaration parsing through comments and ``PRIVATE_`` markers."""

from ._parser_core_test_support import parser_core_parse_source_text

_MD = "MODULEDEFINITION"


def test_moduletype_declaration_parses_through_comments_and_private() -> None:
    code = f"""
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : {_MD} DateCode_ 1
TYPEDEFINITIONS
    Type1 (* left of equals *) = PRIVATE_ {_MD} DateCode_ 2
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ENDDEF (*type one end*);
    Type2 = {_MD} DateCode_ 3
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ENDDEF (*type two end*);
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*base*);
"""
    bp = parser_core_parse_source_text(code)

    assert [mt.name for mt in bp.moduletype_defs] == ["Type1", "Type2"]
    assert [c.text for c in bp.moduletype_defs[0].description_comments] == ["(* left of equals *)"]
    assert [mt.datecode for mt in bp.moduletype_defs] == [2, 3]


def test_moduletype_declarations_close_moduletype_and_submodule_loops() -> None:
    code = f"""
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : {_MD} DateCode_ 1
TYPEDEFINITIONS
    First = {_MD} DateCode_ 3
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ENDDEF (*first end*);
    Third = {_MD} DateCode_ 5
    SUBMODULES
        Child Invocation (0.0,0.0,0.0,1.0,1.0) : {_MD} DateCode_ 6
        ModuleDef
        ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
        ENDDEF (*child end*);
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ENDDEF (*third end*);
    Fourth (* desc *) = {_MD} DateCode_ 7
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ENDDEF (*fourth end*);
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*base*);
"""
    bp = parser_core_parse_source_text(code)

    assert [mt.name for mt in bp.moduletype_defs] == ["First", "Third", "Fourth"]
    assert [sub.header.name for sub in bp.moduletype_defs[1].submodules] == ["Child"]
    assert [c.text for c in bp.moduletype_defs[2].description_comments] == ["(* desc *)"]


def test_record_declarations_stay_record_definitions() -> None:
    code = f"""
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : {_MD} DateCode_ 1
TYPEDEFINITIONS
    Rec1 = RECORD DateCode_ 2
    A: integer;
    ENDDEF (*rec end*);
TYPEDEFINITIONS
    Type1 = {_MD} DateCode_ 3
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ModuleCode
    EQUATIONBLOCK Eq1 COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
       C = 5;
       A = B;
    ENDDEF (*type end*);
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*base*);
"""
    bp = parser_core_parse_source_text(code)

    assert [dt.name for dt in bp.datatype_defs] == ["Rec1"]
    assert [mt.name for mt in bp.moduletype_defs] == ["Type1"]
