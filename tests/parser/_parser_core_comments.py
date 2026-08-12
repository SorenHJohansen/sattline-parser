# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_code_comment_dataclass_exposes_full_text_and_inner_content():
    comment = CodeComment(text="(* outer (* nested *) text *)", span=SourceSpan(line=3, column=5))

    assert comment.content == " outer (* nested *) text "
    assert str(comment) == "(* outer (* nested *) text *)"
    assert comment.span == SourceSpan(line=3, column=5)
    assert CodeComment("plain").content == "plain"


def test_module_header_captures_description_comments():
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture (* before invoke *) Invocation (* after invoke *) (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""
    bp = parser_core_parse_source_text(code)

    assert [c.text for c in bp.header.description_comments] == [
        "(* before invoke *)",
        "(* after invoke *)",
    ]
    assert bp.header.description_comments[0].content == " before invoke "


def test_base_picture_and_modules_capture_end_comments():
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
SUBMODULES
    Child Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 2
    ModuleDef
    ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ENDDEF (*child end*);
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*root end*);
"""
    bp = parser_core_parse_source_text(code)

    assert [c.text for c in bp.trailing_comments] == ["(*root end*)"]
    child = bp.submodules[0]
    assert isinstance(child, SingleModule)
    assert [c.text for c in child.trailing_comments] == ["(*child end*)"]


def test_record_and_moduletype_definition_capture_role_comments():
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
    TYPEDEFINITIONS
    Rec1 = RECORD DateCode_ 2
        A: integer;
        (* variable list comment *)
    ENDDEF (*rec end*);
TYPEDEFINITIONS
    Type1 (* type desc *) = MODULEDEFINITION DateCode_ 3
        ModuleDef
        ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
        ENDDEF (*type end*);
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""
    bp = parser_core_parse_source_text(code)

    record = bp.datatype_defs[0]
    assert [c.text for c in record.trailing_comments] == ["(*rec end*)"]

    moduletype = bp.moduletype_defs[0]
    assert [c.text for c in moduletype.description_comments] == ["(* type desc *)"]
    assert [c.text for c in moduletype.trailing_comments] == ["(*type end*)"]


def test_modulecode_keeps_top_level_code_comments_and_inline_equation_comments():
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
    ModuleCode
    (* top comment *)
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        A = 1;
        (* inline equation comment *)
ENDDEF (*BasePicture*);
"""
    bp = parser_core_parse_source_text(code)

    assert bp.modulecode is not None
    assert [c.text for c in bp.modulecode.comments] == ["(* top comment *)"]

    equation = bp.modulecode.equations[0] if bp.modulecode.equations else None
    assert equation is not None
    comment_items = [x for x in equation.code if isinstance(x, CodeComment)]
    assert [c.text for c in comment_items] == ["(* inline equation comment *)"]


def test_comments_at_discard_sites_do_not_corrupt_ast():
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
(* header line comment *)
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
(* moduledef comment *)
ENDDEF (* end comment *);
"""
    bp = parser_core_parse_source_text(code)

    assert bp.program_name is None
    assert bp.moduledef is not None
    assert bp.moduledef.clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))
    assert [c.text for c in bp.trailing_comments] == ["(* end comment *)"]


def test_nested_comments_roundtrip_as_single_code_comment():
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
    (* outer (* nested *) comment *)
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        A = 1;
ENDDEF (*BasePicture*);
"""
    bp = parser_core_parse_source_text(code)

    assert bp.modulecode is not None
    assert [c.text for c in bp.modulecode.comments] == ["(* outer (* nested *) comment *)"]
    assert bp.modulecode.comments[0].content == " outer (* nested *) comment "


def test_comment_stmt_in_equation_block_is_treated_as_null_statement():
    code = """
"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
    X: integer := 0;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        (* comment as statement *);
        X = 1;
ENDDEF (*BasePicture*);
"""
    bp = parser_core_parse_source_text(code)

    assert bp.modulecode is not None
    equation = bp.modulecode.equations[0]
    comment_items = [x for x in equation.code if isinstance(x, CodeComment)]
    assert [c.text for c in comment_items] == ["(* comment as statement *)"]
