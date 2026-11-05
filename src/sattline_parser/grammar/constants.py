"""Grammar and AST vocabulary for the SattLine parser.

The file holds three kinds of facts:

* ``GRAMMAR_VALUE_*`` spellings. The grammar template inserts them as quoted
  literals, and the transformer compares token types with them.
* ``GRAMMAR_REGEX_*`` fragments. The grammar template inserts them as regex
  bodies. Keyword and boolean fragments are built from the ``GRAMMAR_VALUE_*``
  spellings above, so a spelling is declared once.
* Model vocabulary: tree tags used between transformer stages, property-map
  keys, and token type names.

Every public constant is ``Final`` and exported through ``__all__``. A spelling
keeps the casing the language uses; the resolved grammar applies
case-insensitive matching to every keyword terminal (see
``grammar/keywords.py``).
"""

from typing import Final

#: Documented SattLine numeric limits.
INT_MIN: Final = -2147483648
INT_MAX: Final = 2147483647
REAL_MAX: Final = 1.7014117e38

# ---------------------------------------------------------------------------
# Boolean spellings
# ---------------------------------------------------------------------------

#: The two boolean meanings and the spellings that produce them. ``On`` and
#: ``Off`` are equivalent to ``True`` and ``False``. These tuples are the single
#: source for the boolean regexes, the transformer decode, and the identifier
#: exclusion list.
BOOL_TRUE_SPELLINGS: Final = ("True", "On")
BOOL_FALSE_SPELLINGS: Final = ("False", "Off")
BOOL_SPELLINGS: Final = (*BOOL_TRUE_SPELLINGS, *BOOL_FALSE_SPELLINGS)

# ---------------------------------------------------------------------------
# Tree tags handed between transformer stages
# ---------------------------------------------------------------------------

TREE_TAG_DATATYPE_LIST: Final = "datatype_list"
TREE_TAG_MODULETYPE_LIST: Final = "moduletype_list"
TREE_TAG_VAR_LIST: Final = "var_list"
TREE_TAG_MODULETYPE_PAR_LIST: Final = "moduletype_par_list"
TREE_TAG_MODULEDEF_BLOCK: Final = "moduledef_block"
TREE_TAG_BASE_MODULE_BODY: Final = "base_module_body"
TREE_TAG_MODULE_BODY: Final = "module_body"
TREE_TAG_SUBMODULES: Final = "submodules"
TREE_TAG_MODULETYPE_DEFINITION: Final = "moduletype_definition"

# ---------------------------------------------------------------------------
# Property-map and token keys
# ---------------------------------------------------------------------------

KEY_NAME: Final = "name"
KEY_DOT: Final = "DOT"
KEY_STRING: Final = "STRING"
KEY_SIGNED_INT: Final = "SIGNED_INT"
KEY_SL_DATECODE: Final = "SL_DATECODE"
KEY_PLUS: Final = "PLUS"
KEY_MINUS: Final = "MINUS"
KEY_SEQUENCE_BODY: Final = "sequence_body"
KEY_SEQ_CONTROL_OPS: Final = "seq_control_opt"

#: Keys written into the typed property maps (see ``models/properties.py``).
KEY_COORDS: Final = "coords"
KEY_SEGMENT_POINT: Final = "segment_point"
KEY_POLYGON_TYPE: Final = "polygon_type"
KEY_TAILS: Final = "tails"
KEY_LAYER: Final = "layer"
KEY_COLOURS: Final = "colours"
KEY_TEXT_VARS: Final = "text_vars"
KEY_ENABLE: Final = "enable"
KEY_ENABLE_TAIL: Final = "enable_tail"
KEY_LAYERS: Final = "layers"
KEY_ASSIGNS: Final = "assigns"
KEY_ENABLES: Final = "enables"
KEY_FLAGS: Final = "flags"
KEY_BODY: Final = "body"
KEY_PROCEDURE: Final = "procedure"

# ---------------------------------------------------------------------------
# Grammar keyword spellings
# ---------------------------------------------------------------------------

# Module structure
GRAMMAR_VALUE_ASSIGN_INIT_VALUE: Final = ":="
GRAMMAR_VALUE_CLIPPINGBOUNDS: Final = "ClippingBounds"
GRAMMAR_VALUE_MODULEDEF: Final = "ModuleDef"
GRAMMAR_VALUE_MODULECODE: Final = "ModuleCode"
GRAMMAR_VALUE_SUBMODULES: Final = "SUBMODULES"
GRAMMAR_VALUE_TYPEDEFINITIONS: Final = "TYPEDEFINITIONS"
GRAMMAR_VALUE_RECORD_KW: Final = "RECORD"
GRAMMAR_VALUE_ENDDEF_KW: Final = "ENDDEF"
GRAMMAR_VALUE_MODULEDEFINITION: Final = "MODULEDEFINITION"
GRAMMAR_VALUE_INVOCATION: Final = "Invocation"
GRAMMAR_VALUE_FRAME_MODULE: Final = "Frame_Module"
GRAMMAR_VALUE_MODULEPARAMETERS: Final = "MODULEPARAMETERS"
GRAMMAR_VALUE_LOCALVARIABLES: Final = "LOCALVARIABLES"
GRAMMAR_VALUE_GRAPHOBJECTS: Final = "GraphObjects"
GRAMMAR_VALUE_INTERACTOBJECTS: Final = "InteractObjects"
GRAMMAR_VALUE_DATECODE_PREFIX: Final = "DateCode_"
GRAMMAR_VALUE_GROUPCONN: Final = "GroupConn"
GRAMMAR_VALUE_MODULE_IN_VIEW: Final = "Module_In_View"

# Control flow and operators
GRAMMAR_VALUE_IF: Final = "IF"
GRAMMAR_VALUE_THEN: Final = "THEN"
GRAMMAR_VALUE_ELSE: Final = "ELSE"
GRAMMAR_VALUE_ELSIF: Final = "ELSIF"
GRAMMAR_VALUE_ENDIF: Final = "ENDIF"
GRAMMAR_VALUE_OR: Final = "OR"
GRAMMAR_VALUE_AND: Final = "AND"
GRAMMAR_VALUE_NOT: Final = "NOT"
GRAMMAR_VALUE_LT: Final = "<"
GRAMMAR_VALUE_GT: Final = ">"
GRAMMAR_VALUE_EQ: Final = "=="
GRAMMAR_VALUE_NE: Final = "<>"
GRAMMAR_VALUE_LE: Final = "<="
GRAMMAR_VALUE_GE: Final = ">="
GRAMMAR_VALUE_PLUS: Final = "+"
GRAMMAR_VALUE_MINUS: Final = "-"
GRAMMAR_VALUE_MULTIPLY: Final = "*"
GRAMMAR_VALUE_DIVIDE: Final = "/"

# Sequences and equations
GRAMMAR_VALUE_SEQCONTROL: Final = "SeqControl"
GRAMMAR_VALUE_SEQTIMER: Final = "SeqTimer"
GRAMMAR_VALUE_COORD_KW: Final = "COORD"
GRAMMAR_VALUE_OBJSIZE: Final = "OBJSIZE"
GRAMMAR_VALUE_SEQINITSTEP: Final = "SEQINITSTEP"
GRAMMAR_VALUE_SEQSTEP: Final = "SEQSTEP"
GRAMMAR_VALUE_SEQTRANSITION: Final = "SEQTRANSITION"
GRAMMAR_VALUE_WAIT_FOR: Final = "WAIT_FOR"
GRAMMAR_VALUE_ENTERCODE: Final = "ENTERCODE"
GRAMMAR_VALUE_ACTIVECODE: Final = "ACTIVECODE"
GRAMMAR_VALUE_EXITCODE: Final = "EXITCODE"
GRAMMAR_VALUE_EQUATIONBLOCK: Final = "EQUATIONBLOCK"
GRAMMAR_VALUE_EQUATIONS: Final = "EQUATIONS"
GRAMMAR_VALUE_ENDSEQUENCE: Final = "ENDSEQUENCE"
GRAMMAR_VALUE_ALTERNATIVESEQ: Final = "ALTERNATIVESEQ"
GRAMMAR_VALUE_ALTERNATIVEBRANCH: Final = "ALTERNATIVEBRANCH"
GRAMMAR_VALUE_ENDALTERNATIVE: Final = "ENDALTERNATIVE"
GRAMMAR_VALUE_PARALLELBRANCH: Final = "PARALLELBRANCH"
GRAMMAR_VALUE_PARALLELSEQ: Final = "PARALLELSEQ"
GRAMMAR_VALUE_ENDPARALLEL: Final = "ENDPARALLEL"
GRAMMAR_VALUE_SEQBREAK: Final = "SEQBREAK"
GRAMMAR_VALUE_SEQFORK: Final = "SEQFORK"
GRAMMAR_VALUE_SUBSEQTRANSITION: Final = "SUBSEQTRANSITION"
GRAMMAR_VALUE_ENDSUBSEQTRANSITION: Final = "ENDSUBSEQTRANSITION"
GRAMMAR_VALUE_SUBSEQSTEP: Final = "SUBSEQSTEP"
GRAMMAR_VALUE_ENDSUBSEQSTEP: Final = "ENDSUBSEQSTEP"
GRAMMAR_VALUE_SUBSEQUENCE: Final = "SUBSEQUENCE"
GRAMMAR_VALUE_ENDSUBSEQUENCE: Final = "ENDSUBSEQUENCE"
GRAMMAR_VALUE_SEQUENCE: Final = "SEQUENCE"
GRAMMAR_VALUE_OPENSEQUENCE: Final = "OPENSEQUENCE"
GRAMMAR_VALUE_ENDOPENSEQUENCE: Final = "ENDOPENSEQUENCE"

# Layout and zoom
GRAMMAR_VALUE_TWO_LAYERS: Final = "Two_Layers_"
GRAMMAR_VALUE_LAYERLIMIT: Final = "LayerLimit_"
GRAMMAR_VALUE_LAYER_PREFIX: Final = "Layer_"
GRAMMAR_VALUE_ZOOMLIMITS: Final = "ZoomLimits"
GRAMMAR_VALUE_ZOOMABLE: Final = "Zoomable"
GRAMMAR_VALUE_GRID: Final = "Grid"
GRAMMAR_VALUE_IGNOREMAXMODULE: Final = "IgnoreMaxModule"
GRAMMAR_VALUE_LAYERMODULE: Final = "LayerModule"

# Alignment, graphics objects, and their properties
GRAMMAR_VALUE_LEFTALIGNED: Final = "LeftAligned"
GRAMMAR_VALUE_RIGHTALIGNED: Final = "RightAligned"
GRAMMAR_VALUE_TEXTOBJECT: Final = "TextObject"
GRAMMAR_VALUE_RECTANGLEOBJECT: Final = "RectangleObject"
GRAMMAR_VALUE_LINEOBJECT: Final = "LineObject"
GRAMMAR_VALUE_OVALOBJECT: Final = "OvalObject"
GRAMMAR_VALUE_POLYGONOBJECT: Final = "PolygonObject"
GRAMMAR_VALUE_SPLINE: Final = "Spline"
GRAMMAR_VALUE_POLYLINE: Final = "Polyline"
GRAMMAR_VALUE_CONNECTION: Final = "Connection"
GRAMMAR_VALUE_SEGMENTOBJECT: Final = "SegmentObject"
GRAMMAR_VALUE_COMPOSITEOBJECT: Final = "CompositeObject"
GRAMMAR_VALUE_CONNECTIONNODE: Final = "ConnectionNode"
GRAMMAR_VALUE_ENABLE_PREFIX: Final = "Enable_"
GRAMMAR_VALUE_VARNAME: Final = "VarName"
GRAMMAR_VALUE_RELATIVE: Final = "Relative_"
GRAMMAR_VALUE_ABS: Final = "Abs_"
GRAMMAR_VALUE_INTOBJPICKBUTTON: Final = "IntObjPickButton"
GRAMMAR_VALUE_VALUEFRACTION: Final = "ValueFraction"
GRAMMAR_VALUE_COLOUR0: Final = "Colour0"
GRAMMAR_VALUE_COLOUR1: Final = "Colour1"
GRAMMAR_VALUE_OUTLINECOLOUR: Final = "OutlineColour"
GRAMMAR_VALUE_FILLCOLOUR: Final = "FillColour"
GRAMMAR_VALUE_WIDTH_KEY: Final = "Width_"
GRAMMAR_VALUE_COLOURSTYLE: Final = "ColourStyle"

# Interactors and tails
GRAMMAR_VALUE_INVAR_PREFIX: Final = "InVar_"
GRAMMAR_VALUE_OUTVAR_PREFIX: Final = "OutVar_"
GRAMMAR_VALUE_LITSTRING: Final = "LitString"
GRAMMAR_VALUE_FORMAT_STRING: Final = "Format_String_"
GRAMMAR_VALUE_COMBUT: Final = "ComBut_"
GRAMMAR_VALUE_OPTBUT: Final = "OptBut_"
GRAMMAR_VALUE_PROCEDUREINTERACT: Final = "ProcedureInteract"
GRAMMAR_VALUE_COMBUTPROC: Final = "ComButProc_"
GRAMMAR_VALUE_NEWWINDOW: Final = "NewWindow"
GRAMMAR_VALUE_CHECKBOX: Final = "CheckBox_"
GRAMMAR_VALUE_TEXTBOX: Final = "TextBox_"
GRAMMAR_VALUE_MENUINTERACT: Final = "MenuInteract"
GRAMMAR_VALUE_SIMPLEINTERACT: Final = "SimpleInteract"
GRAMMAR_VALUE_SYMBOLMODULE: Final = "SymbolModule"
GRAMMAR_VALUE_NON_ZOOMABLE: Final = "Non_Zoomable"
GRAMMAR_VALUE_PRIVATE: Final = "PRIVATE_"

# Declarations and states
GRAMMAR_VALUE_GLOBAL_KW: Final = "GLOBAL"
GRAMMAR_VALUE_CONST_KW: Final = "Const"
GRAMMAR_VALUE_STATE_KW: Final = "State"
GRAMMAR_VALUE_OPSAVE_KW: Final = "OpSave"
GRAMMAR_VALUE_SECURE_KW: Final = "Secure"
GRAMMAR_VALUE_DURATION_VALUE: Final = "Duration_Value"
GRAMMAR_VALUE_TIME_VALUE: Final = "Time_Value"
GRAMMAR_VALUE_DEFAULT: Final = "Default"
GRAMMAR_VALUE_NEW: Final = "New"
GRAMMAR_VALUE_OLD: Final = "Old"

# ---------------------------------------------------------------------------
# Grammar regex fragments
# ---------------------------------------------------------------------------

#: The numeric and string literals. They do not spell a keyword, so they are
#: written directly.
GRAMMAR_REGEX_SIGNED_INT: Final = r"/[+-]?\d+/"
GRAMMAR_REGEX_SIGNED_INT_NOTAIL: Final = r"/[+-]?\d+(?![\d.])(?!(?:[ \t\r\n]*:))/"
GRAMMAR_REGEX_REAL: Final = r"/[+-]?(?:\d+\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)/"
GRAMMAR_REGEX_REAL_NOTAIL: Final = r"/[+-]?(?:\d+\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)(?![ \t\r\n]*:)/"
GRAMMAR_REGEX_STRING: Final = r"/\"([^\n\"]|\"\")*\"/"
GRAMMAR_REGEX_STRING_NOTAIL: Final = r"/\"([^\n\"]|\"\")*\"(?![ \t\r\n]*:)/"
GRAMMAR_REGEX_STRING_CRLF: Final = r"/\"([^\"\n]|\"\")*\n/"
GRAMMAR_REGEX_COMMENT_TEXT: Final = r"/(?:[^(*]|\((?!\*)|\*(?!\)))+/"
GRAMMAR_REGEX_SL_DATECODE: Final = r"/\d+/"

#: Keyword fragments built from the spelling constants above.
GRAMMAR_REGEX_IF: Final = rf"/{GRAMMAR_VALUE_IF}\b/"
GRAMMAR_REGEX_THEN: Final = rf"/{GRAMMAR_VALUE_THEN}\b/"
GRAMMAR_REGEX_ELSE: Final = rf"/{GRAMMAR_VALUE_ELSE}\b/"
GRAMMAR_REGEX_ELSIF: Final = rf"/{GRAMMAR_VALUE_ELSIF}\b/"
GRAMMAR_REGEX_ENDIF: Final = rf"/{GRAMMAR_VALUE_ENDIF}\b/"
GRAMMAR_REGEX_AND: Final = rf"/{GRAMMAR_VALUE_AND}\b/"
GRAMMAR_REGEX_OR: Final = rf"/{GRAMMAR_VALUE_OR}\b/"
GRAMMAR_REGEX_NOT: Final = rf"/{GRAMMAR_VALUE_NOT}\b/"
GRAMMAR_REGEX_ENABLE_PREFIX: Final = rf"/{GRAMMAR_VALUE_ENABLE_PREFIX}\b/"
GRAMMAR_REGEX_STATE_SUFFIX: Final = rf"/:\s*(?:{GRAMMAR_VALUE_NEW}|{GRAMMAR_VALUE_OLD})\b/"

#: Boolean fragments built from the boolean spelling tables.
GRAMMAR_REGEX_BOOL: Final = "/" + "|".join(f"{spelling}\\b" for spelling in BOOL_SPELLINGS) + "/"
GRAMMAR_REGEX_BOOL_NOTAIL: Final = "/(?:" + "|".join(BOOL_SPELLINGS) + r")\b(?![ \t\r\n]*:)/"


#: Identifiers are matched case-insensitively so that the keyword exclusion list
#: below excludes ``true``/``ENDDEF`` as well as ``True``/``ENDDEF``; keyword
#: case is folded. The scope wraps the whole pattern because the terminal spans
#: several lines in the grammar template.
#: Identifier characters. Comparison is byte-oriented, and real
#: libraries use CP1252 bytes that are not Unicode letters inside identifiers
#: (``0xA6``, ``0xB8`` and ``0x85`` all occur in identifier text), so the
#: printable CP1252 range is part of the class alongside the letter/mark
#: categories.
def _cp1252_name_characters() -> str:
    characters: list[str] = []
    for byte in range(0x80, 0x100):
        try:
            characters.append(bytes((byte,)).decode("cp1252"))
        except UnicodeDecodeError:  # 0x81/0x8D/0x8F/0x90/0x9D are undefined
            continue
    return "".join(characters)


_NAME_CHAR: Final = r"\p{L}\p{Nl}\p{M}\p{Nd}_'" + _cp1252_name_characters() + r"\uFFFD"
_NAME_EXCLUDED_KEYWORDS: Final = (
    GRAMMAR_VALUE_IF,
    GRAMMAR_VALUE_THEN,
    GRAMMAR_VALUE_ELSE,
    GRAMMAR_VALUE_ELSIF,
    GRAMMAR_VALUE_ENDIF,
    GRAMMAR_VALUE_AND,
    GRAMMAR_VALUE_OR,
    GRAMMAR_VALUE_NOT,
    *BOOL_TRUE_SPELLINGS,
    *BOOL_FALSE_SPELLINGS,
    GRAMMAR_VALUE_SUBSEQSTEP,
)
_NAME_EXCLUDED: Final = "|".join(_NAME_EXCLUDED_KEYWORDS)

GRAMMAR_REGEX_NAME: Final = (
    r"/(?i:'[^']{1,20}'|"
    r"(?!"
    rf"(?:{_NAME_EXCLUDED})"
    rf"(?![{_NAME_CHAR}])"
    r")"
    rf"[{_NAME_CHAR}][{_NAME_CHAR}]{{0,19}}"
    rf"(?![{_NAME_CHAR}]))/"
)

# ---------------------------------------------------------------------------
# Token type names
# ---------------------------------------------------------------------------

TOKEN_VARNAME: Final = "VARNAME"
TOKEN_COMMENT_START: Final = "COMMENT_START"  # nosec B105 - token type name
TOKEN_COMMENT_END: Final = "COMMENT_END"  # nosec B105 - token type name
TOKEN_COMMENT_TEXT: Final = "COMMENT_TEXT"  # nosec B105 - token type name
TOKEN_NAME: Final = "NAME"

COMMENT_TERMINALS: Final = frozenset({TOKEN_COMMENT_START, TOKEN_COMMENT_END, TOKEN_COMMENT_TEXT})

__all__ = sorted(  # pyright: ignore[reportUnsupportedDunderAll]
    name for name in globals() if name.isupper() and not name.startswith("_")
)
