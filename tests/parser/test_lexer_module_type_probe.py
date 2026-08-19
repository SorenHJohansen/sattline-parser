# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportPrivateUsage=false

"""Coverage for the MODULE_TYPE_NAME contextual-lexer probe.

The probe upgrades a ``NAME`` to ``MODULE_TYPE_NAME`` when the identifier is a
module-type definition head (``= MODULEDEFINITION``) in an LALR state that
cannot otherwise close the ``submodules`` or ``moduletype_definition`` loops.
These tests exercise the upgrade through comments and ``PRIVATE_`` markers,
plus the negative path (records stay plain ``NAME``).
"""

import pytest

from sattline_parser.grammar.sattline_lexer import _comment_end, _module_typedecl_after

from ._parser_core_test_support import parser_core_parse_source_text

_MD = "MODULEDEFINITION"


def test_comment_end_balances_nested_comments() -> None:
    assert _comment_end("(* a (* b *) c *)", 0) == len("(* a (* b *) c *)")
    assert _comment_end("(* unclosed", 0) == len("(* unclosed")
    assert _comment_end("(* a *)", 0) == len("(* a *)")


def test_module_typedecl_after_accepts_and_rejects() -> None:
    assert _module_typedecl_after("X = MODULEDEFINITION rest", 2) is True
    assert _module_typedecl_after("X =  PRIVATE_  MODULEDEFINITION rest", 2) is True
    assert _module_typedecl_after("X = RECORD rest", 2) is False
    assert _module_typedecl_after("X = ", 2) is False
    assert _module_typedecl_after("X = MODULE", 2) is False
    assert _module_typedecl_after("", 0) is False


def test_module_typedecl_after_rejects_non_text() -> None:
    with pytest.raises(TypeError, match="_module_typedecl_after"):
        _module_typedecl_after(123, 0)
    with pytest.raises(TypeError, match="_comment_end"):
        _comment_end(123, 0)


def test_module_type_probe_upgrades_through_comments_and_private() -> None:
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
"""
    bp = parser_core_parse_source_text(code)

    assert [mt.name for mt in bp.moduletype_defs] == ["Type1", "Type2"]
    assert [c.text for c in bp.moduletype_defs[0].description_comments] == ["(* left of equals *)"]
    assert [mt.datecode for mt in bp.moduletype_defs] == [2, 3]


def test_module_type_probe_closes_moduletype_and_submodule_loops() -> None:
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
        ENDDEF (*child module end*);
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ENDDEF (*third end*);
    Fourth (* desc *) = {_MD} DateCode_ 7
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ENDDEF (*fourth end*);
"""
    bp = parser_core_parse_source_text(code)

    assert [mt.name for mt in bp.moduletype_defs] == ["First", "Third", "Fourth"]
    assert [sub.header.name for sub in bp.moduletype_defs[1].submodules] == ["Child"]
    assert [c.text for c in bp.moduletype_defs[2].description_comments] == ["(* desc *)"]


def test_module_type_probe_does_not_upgrade_record_heads() -> None:
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
"""
    bp = parser_core_parse_source_text(code)

    assert [dt.name for dt in bp.datatype_defs] == ["Rec1"]
    assert [mt.name for mt in bp.moduletype_defs] == ["Type1"]
