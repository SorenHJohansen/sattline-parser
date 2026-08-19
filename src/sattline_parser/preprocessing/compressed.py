"""Helpers for decoding compressed SattLine text before parsing.

The decoder is *lexically aware*: string literals and structural
``(* ... *)`` comments are protected (replaced by opaque placeholders) before
any syntax-level transformation runs, so syntax-looking text inside strings or
comments can never be rewritten accidentally.

The decoder also builds a per-character map from the decoded (normalized) text
back to the original source, so the parser can report AST spans and diagnostics
against the original source (:class:`sattline_parser.source_document.SourceDocument`).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import partial

from sattline_parser.source_document import GENERATED, SourceDocument

__all__ = [
    "SEED_MAPPING",
    "CompatTransform",
    "NormalizationKind",
    "PreprocessError",
    "decode_compressed",
    "is_compressed",
    "preprocess_sl_text",
    "preprocess_source",
]

# Seed mappings from sample files (kept explicit for traceability).
SEED_MAPPING: dict[str, str] = {
    "#6?": "Invocation",
    "#6=": "IgnoreMaxModule",
    "#8=": ":",
    "#71": "MODULEDEFINITION",
    "#81": "DateCode_",
    "#78": "TYPEDEFINITIONS",
    "#72": "RECORD",
    "#85": "ENDDEF",
    "#7:": "OpSave",
    "#7:;": "OpSave;",
    "#7;;": ";",
    "#01": "(",
    "#8?": "=",
    "#8:": "=>",
    "#8;": ":=",
    "#1<": "False",
    "#1<;": "False;",
    "#1>": "False",
    "#1>;": "False;",
    "#1=": "True",
    "#1=;": "True;",
    "#1;;": "True;",
    "#1;": "True",
    "#79": "SUBMODULES",
    "#73": "MODULEPARAMETERS",
    "#7<": "LOCALVARIABLES",
    "#74": "GLOBAL",
    "#80": "State",
    "#80;": "State;",
    "#17": "Old",
    "#17;": "Old;",
    "#18": "Old",
    "#18;": "Old;",
    "#87": "Frame_Module",
    "#6<": "LayerModule",
    "#6>": "ModuleDef",
    "#65": "ClippingBounds",
    "#66": "Dim_",
    "#40": "InteractObjects",
    "#41": "SimpleInteract",
    "#42": "MenuInteract",
    "#::": "TextBox_",
    "#4?": "GraphObjects",
    "#56": "TextObject",
    "#70": "",
    "#52": "RectangleObject",
    "#50": "LineObject",
    "#51": "OvalObject",
    "#53": "SegmentObject",
    "#54": "PolygonObject",
    "#55": "Spline",
    "#57": "Polyline",
    "#58": "LeftAligned",
    "#5<": "OutlineColour",
    "#5;": "FillColour",
    "#5:": "RightAligned",
    "#59": "CenterAligned",
    "#5=": "ColourStyle",
    "#5?": "VarName",
    "#5>": "Width_",
    "#95": "ProcedureInteract",
    "#61": "Colour0",
    "#62": "Colour1",
    "#63": "ZoomLimits",
    "#6:": "Zoomable",
    "#68": "Connection",
    "#69": "ConnectionNode",
    "#43": "SelectVariable",
    "#84": "ModuleCode",
    "#86": "GroupConn",
    "#77": "Secure",
    "#77;": "Secure;",
    "#20": "EQUATIONBLOCK",
    "#22": "SEQUENCE",
    "#23": "ENDSEQUENCE",
    "#88": "COORD",
    "#89": "OBJSIZE",
    "#26": "SEQINITSTEP",
    "#27": "SEQSTEP",
    "#28": "ENTERCODE",
    "#29": "ACTIVECODE",
    "#30": "SEQTRANSITION",
    "#31": "WAIT_FOR",
    "#34": "ALTERNATIVESEQ",
    "#35": "ALTERNATIVEBRANCH",
    "#36": "ENDALTERNATIVE",
    "#2:": "EXITCODE",
    "#94;": "Default;",
    "#94": "Default",
    "#7;": "Const",
    "#76": "PRIVATE_",
    "#;5": "Layer_",
    "#;7": "Int_Value",
    "#;6": "Bool_Value",
    "#64": "Enable_",
    "#3>": "InVar_",
    "#3?": "OutVar_",
    "#3<": "SEQFORK",
    "#3=": "SEQBREAK",
    "#47": "Variable",
    "#48": "OpMin",
    "#49": "OpMax",
    "#4:": "OpStep",
    "#4=": "ToggleAction",
    "#4;": "SetAction",
    "#4<": "ResetAction",
    "#60": "ValueFraction",
    "#9>": "Event_Text_",
    "#9?": "Event_Tag_",
    "#9=": "Value_Changed",
    "#9<": "Enable_",
    "#9;": "Time_Value",
    "#9:": "Duration_Value",
    "#96": "LitString",
    "#:0": "Event_Severity_",
    "#:1": "Event_Class_",
    "#:6": "ComBut_",
    "#:7": "ComButProc_",
    "#:8": "OptBut_",
    "#:>": "Value_",
    "#:9": "CheckBox_",
    "#:3": "Format_String_",
    "#:5": "Key_",
    "#:4": "Grid",
    "#:?": "Decimal_",
    "#:;": "Visible_",
    "#:<": "Abs_",
    "#:=": "Abs_",
    "#;0": "Digits_",
    "#;1": "NoOf_",
    "#;3": "SetApp_",
    "#;4": "Two_Layers_",
    "#;8": "Real_Value",
    "#;2": "TextObject",
    "#;>": "Zoomable",
    "#;?": "LayerLimit_",
    "#;:": "Alt_Text",
    "#;9": "String_Value",
    "#;=": "Cancel_Variable",
    "#;;": "Enable_Delay",
    "#;<": "OK_Variable",
    "#16": "NOT",
    "#14": "AND",
    "#0?": "IF",
    "#11": "ELSIF",
    "#10": "THEN",
    "#15": "OR",
    "#12": "ELSE",
    "#13;": "ENDIF;",
    "#13": "ENDIF",
    "#05": ">",
    "#04": "<",
    "#07": ">=",
    "#06": "<=",
    "#08": "==",
    "#09": "<>",
    "#<0": "SnglSgn",
    "#<1": "SnglSgnEna",
    "#<2": "Purpose_",
    "#<4": "SgnrCom",
    "#<5": "CommentChng",
    "#<6": "CommentMand",
    "#<7": "Signer1_",
    "#<8": "Signer1Name_",
    "#<9": "DblSgn",
    "#<:": "DblSgnEna",
    "#<;": "CansCom",
    "#<<": "SgnCans",
    "#<=": "Signer2_",
    "#<>": "Signer2Name_",
}

_MARKER_RE = re.compile(r"#[0-9A-Za-z;:=><?]+")
_WHITESPACE_RE = re.compile(r"\s+")
_ENDDEF_TRAILING_SEMI_RE = re.compile(r"\bENDDEF\b\s*;")
_SEMI_BEFORE_ASSIGN_RE = re.compile(r";\s*:=")
_ENDIF_SEMI_COMMA_RE = re.compile(r"ENDIF;\s*,")
_ENDIF_SEMI_PAREN_RE = re.compile(r"ENDIF;\s*\)")
_EMPTY_ASSIGN_RE = re.compile(r":=\s*;")
_GRAPHOBJECTS_INTERACT_RE = re.compile(r"\bGraphObjects\b\s*:\s*InteractObjects\b")
# String literals are protected placeholders by the time these run.
_STRING_PLACEHOLDER = r"(\x00S\d+\x00)"
_DURATION_STR_RE = re.compile(r"(\bduration\b(?:\s+OpSave)?\s*:=\s*)" + _STRING_PLACEHOLDER, re.IGNORECASE)
_TIME_STR_RE = re.compile(r"(\btime\b(?:\s+OpSave)?\s*:=\s*)" + _STRING_PLACEHOLDER, re.IGNORECASE)
_DATE_TIMESTAMP_RE = re.compile(r"(=>\s*)" + _STRING_PLACEHOLDER)
_DATE_TIMESTAMP_PATTERN = re.compile(r'"\d{4}-\d{2}-\d{2}-\d{2}:\d{2}:\d{2}\.\d{3}"')
_EXECUTE_LOCAL_ENDDEF_RE = re.compile(r"(ExecuteLocalOld\s*=\s*ExecuteLocal:Old)\s+ENDDEF")
_EXECUTE_STATE_IF_RE = re.compile(r"(ExecuteState:Old)\s+IF\b")
_ENDIF_NO_TERM_RE = re.compile(r"\bENDIF\b(?!\s*[;,\)])")
_GRAPHOBJECTS_ENDDEF_RE = re.compile(r"\bGraphObjects\b\s*:\s*ENDDEF\b")
_TYPE_ENDDEF_RE = re.compile(r"\b(integer|real|boolean|string)\b\s+ENDDEF\b", re.IGNORECASE)
_ENABLE_OUTVAR_RE = re.compile(r"(Enable_\s*=\s*\w+\s*:)\s*OutVar_")
_TRUEVAR_RE = re.compile(r"\bTrueVar\b")
_EQUATIONBLOCK_RE = re.compile(r"\bEQUATIONBLOCK\b")
_EMPTY_TRAILING_ARG_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\(([^)]*?),\s*\)")
_PLACEHOLDER_RE = re.compile(r"\x00[SC]\d+\x00")


class PreprocessError(ValueError):
    """Raised when compressed SattLine source cannot be decoded safely.

    Distinct from Lark parse errors: this signals malformed compressed input
    (for example an unknown ``#marker``) rather than a syntax error in the
    decoded program.
    """


class NormalizationKind(StrEnum):
    """How a compatibility-normalization step touches the decoded program.

    The distinction matters because repairs are not all cosmetic: some inject
    or replace actual syntax that changes the represented program, and
    consumers deserve to know which is which.
    """

    SYNTAX_REPAIR = "syntax_repair"
    SEMANTIC_REPAIR = "semantic_repair"
    GRAMMAR_COMPAT = "grammar_compat"


type CompatReplacer = Callable[[_OpaqueRegistry, str, re.Match[str]], str]


@dataclass(frozen=True)
class CompatTransform:
    """A single explicitly categorized compatibility-normalization step.

    ``replacement`` is either a ``re.sub``-style template string or a callable
    ``(decoded, match) -> str`` that computes the replacement from the current
    decoded text. ``kind`` classifies the step:

    * ``SYNTAX_REPAIR`` -- adjusts punctuation and terminators so structure
      already present in the text parses; no new program meaning is introduced.
    * ``SEMANTIC_REPAIR`` -- injects or replaces actual syntax/values (default
      values, missing keywords, value wrappers), changing the represented
      program.
    * ``GRAMMAR_COMPAT`` -- renames tokens to grammar-accepted spellings to
      avoid tokenizer/grammar conflicts.
    """

    name: str
    kind: NormalizationKind
    pattern: re.Pattern[str]
    replacement: str | CompatReplacer
    description: str


#: Ordered compatibility-normalization steps applied by :func:`_normalize_compat`.
#: Order matters: earlier steps must run before later ones observe the text.
#: Each step is explicitly categorized and documented so semantic repairs are
#: never confused with cosmetic cleanup.
_COMPAT_TRANSFORMS: tuple[CompatTransform, ...] = (
    CompatTransform(
        name="enddef_trailing_semi",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_ENDDEF_TRAILING_SEMI_RE,
        replacement="ENDDEF",
        description="Drop a stray ';' after ENDDEF.",
    ),
    CompatTransform(
        name="semi_before_assign",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_SEMI_BEFORE_ASSIGN_RE,
        replacement=" :=",
        description="Remove a spurious ';' immediately before ':='.",
    ),
    CompatTransform(
        name="endif_semi_comma",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_ENDIF_SEMI_COMMA_RE,
        replacement="ENDIF,",
        description="Remove the ';' between ENDIF and a following ','.",
    ),
    CompatTransform(
        name="endif_semi_paren",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_ENDIF_SEMI_PAREN_RE,
        replacement="ENDIF)",
        description="Remove the ';' between ENDIF and a following ')'.",
    ),
    CompatTransform(
        name="empty_assign_default",
        kind=NormalizationKind.SEMANTIC_REPAIR,
        pattern=_EMPTY_ASSIGN_RE,
        replacement=":= Default;",
        description="Inject 'Default' as the value of an empty assignment (':= ;').",
    ),
    CompatTransform(
        name="graphobjects_interact_prefix",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_GRAPHOBJECTS_INTERACT_RE,
        replacement="InteractObjects",
        description="Drop the invalid 'GraphObjects :' prefix before InteractObjects.",
    ),
    CompatTransform(
        name="duration_str_value",
        kind=NormalizationKind.SEMANTIC_REPAIR,
        pattern=_DURATION_STR_RE,
        replacement=r"\1Duration_Value \2",
        description="Wrap duration string assignments in the Duration_Value keyword.",
    ),
    CompatTransform(
        name="time_str_value",
        kind=NormalizationKind.SEMANTIC_REPAIR,
        pattern=_TIME_STR_RE,
        replacement=r"\1Time_Value \2",
        description="Wrap time string assignments in the Time_Value keyword.",
    ),
    CompatTransform(
        name="date_timestamp_value",
        kind=NormalizationKind.SEMANTIC_REPAIR,
        pattern=_DATE_TIMESTAMP_RE,
        replacement=lambda registry, decoded, m: _date_timestamp_sub(registry, decoded, m),
        description="Wrap date-timestamp strings after '=>' in Time_Value.",
    ),
    CompatTransform(
        name="execute_local_enddef",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_EXECUTE_LOCAL_ENDDEF_RE,
        replacement=r"\1; ENDDEF",
        description="Terminate ExecuteLocalOld assignments with ';' before ENDDEF.",
    ),
    CompatTransform(
        name="execute_state_if",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_EXECUTE_STATE_IF_RE,
        replacement=r"\1; IF",
        description="Terminate ExecuteState assignments with ';' before IF.",
    ),
    CompatTransform(
        name="endif_no_terminator",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_ENDIF_NO_TERM_RE,
        replacement="ENDIF;",
        description="Append ';' to an unterminated ENDIF outside expressions.",
    ),
    CompatTransform(
        name="graphobjects_enddef_empty",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_GRAPHOBJECTS_ENDDEF_RE,
        replacement="ENDDEF",
        description="Drop an empty GraphObjects section before ENDDEF.",
    ),
    CompatTransform(
        name="type_enddef_terminator",
        kind=NormalizationKind.SYNTAX_REPAIR,
        pattern=_TYPE_ENDDEF_RE,
        replacement=r"\1 ; ENDDEF",
        description="Insert ';' between a datatype keyword and ENDDEF.",
    ),
    CompatTransform(
        name="enable_outvar_invar",
        kind=NormalizationKind.GRAMMAR_COMPAT,
        pattern=_ENABLE_OUTVAR_RE,
        replacement=r"\1 InVar_",
        description="Rewrite Enable_ OutVar_ tails to the grammar-accepted InVar_ spelling.",
    ),
    CompatTransform(
        name="truevar_prefix",
        kind=NormalizationKind.GRAMMAR_COMPAT,
        pattern=_TRUEVAR_RE,
        replacement="TTrueVar",
        description="Prefix TrueVar identifiers with 'T' so BOOL tokenization cannot shadow them.",
    ),
    CompatTransform(
        name="equationblock_modulecode",
        kind=NormalizationKind.SEMANTIC_REPAIR,
        pattern=_EQUATIONBLOCK_RE,
        replacement=lambda registry, decoded, m: _ensure_modulecode(registry, decoded, m),
        description="Inject a missing ModuleCode keyword before EQUATIONBLOCK.",
    ),
    CompatTransform(
        name="empty_trailing_arg",
        kind=NormalizationKind.SEMANTIC_REPAIR,
        pattern=_EMPTY_TRAILING_ARG_RE,
        replacement=r"\1(\2, 0)",
        description="Fill an empty trailing function argument with 0 (e.g. 'Func(a, )' -> 'Func(a, 0)').",
    ),
)


def _markers_outside_opaque_regions(text: str) -> list[str]:
    """Return ``#marker`` matches that lie entirely outside strings/comments.

    Detection must agree with the decoder (:func:`_decode_with_map`), which
    protects string literals and ``(* ... *)`` comments before any rewrite. A
    marker that overlaps an opaque region (for example a ``#``-sequence inside
    a string literal) is never decoded and must therefore not count toward the
    compressed heuristic -- otherwise plain source containing such text would
    be misclassified as compressed and preprocessed.
    """
    regions = _scan_opaque_regions(text)
    markers: list[str] = []
    region_index = 0
    region_count = len(regions)
    for match in _MARKER_RE.finditer(text):
        start, end = match.start(), match.end()
        while region_index < region_count and regions[region_index][2] <= start:
            region_index += 1
        if region_index < region_count and start < regions[region_index][2] and regions[region_index][1] < end:
            continue
        markers.append(match.group(0))
    return markers


def is_compressed(text: str) -> bool:
    """Heuristic detector for compressed SattLine format.

    Only markers outside string literals and ``(* ... *)`` comments are
    counted, mirroring the decoder's opaque-region protection so plain source
    containing ``#...``-looking text inside strings or comments is never
    misclassified as compressed.
    """
    markers = _markers_outside_opaque_regions(text)
    if not markers:
        return False
    compact_len = max(len(_WHITESPACE_RE.sub("", text)), 1)
    marker_char_ratio = len("".join(markers)) / compact_len
    marker_count = len(markers)
    keyword_hits = sum(
        1
        for kw in (
            "MODULEDEFINITION",
            "TYPEDEFINITIONS",
            "MODULEPARAMETERS",
            "EQUATIONBLOCK",
        )
        if kw in text
    )
    return marker_count >= 50 or marker_char_ratio >= 0.02 or (marker_count >= 10 and keyword_hits == 0)


# ---------------------------------------------------------------------------
# Lexically-aware protection of string literals and comments
# ---------------------------------------------------------------------------


def _scan_opaque_regions(text: str) -> list[tuple[str, int, int]]:
    """Return ``(kind, start, end)`` for every string ('S') and comment ('C').

    The scanner understands nested ``(* ... *)`` comments, doubled ``""``
    quote escapes, and does not treat text inside a string as a comment (or
    vice versa).
    """
    regions: list[tuple[str, int, int]] = []
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("(*", index):
            depth = 1
            cursor = index + 2
            while cursor < length and depth > 0:
                if text.startswith("(*", cursor):
                    depth += 1
                    cursor += 2
                elif text.startswith("*)", cursor):
                    depth -= 1
                    cursor += 2
                else:
                    cursor += 1
            regions.append(("C", index, cursor))
            index = cursor
        elif text[index] == '"':
            cursor = index + 1
            while cursor < length:
                if text[cursor] == '"':
                    if cursor + 1 < length and text[cursor + 1] == '"':
                        cursor += 2
                        continue
                    cursor += 1
                    break
                cursor += 1
            regions.append(("S", index, cursor))
            index = cursor
        else:
            index += 1
    return regions


class _OpaqueRegistry:
    """Holds protected string/comment regions so they can be restored later."""

    def __init__(self, text: str) -> None:
        self._strings: list[tuple[int, str]] = []
        self._comments: list[tuple[int, str]] = []
        self._regions: list[tuple[str, int, int, int]] = []
        for kind, start, end in _scan_opaque_regions(text):
            entry = (start, text[start:end])
            if kind == "S":
                index = len(self._strings)
                self._strings.append(entry)
            else:
                index = len(self._comments)
                self._comments.append(entry)
            self._regions.append((kind, index, start, end))

    def protect(self, text: str) -> tuple[str, list[int]]:
        parts: list[str] = []
        map_parts: list[list[int]] = []
        last = 0
        for kind, index, start, end in self._regions:
            if start > last:
                parts.append(text[last:start])
                map_parts.append(list(range(last, start)))
            placeholder = f"\x00{kind}{index}\x00"
            parts.append(placeholder)
            map_parts.append([GENERATED] * len(placeholder))
            last = end
        if last < len(text):
            parts.append(text[last:])
            map_parts.append(list(range(last, len(text))))
        decoded = "".join(parts)
        char_map: list[int] = []
        for part in map_parts:
            char_map.extend(part)
        if len(char_map) != len(decoded):  # pragma: no cover - invariant by construction
            raise PreprocessError("internal error: opaque protection map mismatch")  # pragma: no cover
        return decoded, char_map

    def string_text(self, placeholder: str) -> str | None:
        return self._lookup_text(placeholder, "S")

    def _lookup_text(self, placeholder: str, kind: str) -> str | None:
        if len(placeholder) < 4 or placeholder[1] != kind:
            return None
        try:
            index = int(placeholder[2:-1])
        except (ValueError, IndexError):
            return None
        entries = self._strings if kind == "S" else self._comments
        if 0 <= index < len(entries):
            return entries[index][1]
        return None

    def restore(self, decoded: str, char_map: list[int]) -> tuple[str, list[int]]:
        parts: list[str] = []
        map_parts: list[list[int]] = []
        last = 0
        for match in _PLACEHOLDER_RE.finditer(decoded):
            placeholder = match.group(0)
            kind = placeholder[1]
            index = int(placeholder[2:-1])
            entries = self._strings if kind == "S" else self._comments
            if not (0 <= index < len(entries)):
                raise PreprocessError(f"internal error: unknown placeholder {placeholder!r}")
            orig_start, orig_text = entries[index]
            start, end = match.start(), match.end()
            if start > last:
                parts.append(decoded[last:start])
                map_parts.append(char_map[last:start])
            parts.append(orig_text)
            map_parts.append([orig_start + i for i in range(len(orig_text))])
            last = end
        if last < len(decoded):
            parts.append(decoded[last:])
            map_parts.append(char_map[last:])
        restored = "".join(parts)
        restored_map: list[int] = []
        for part in map_parts:
            restored_map.extend(part)
        if "\x00" in restored:
            raise PreprocessError("internal error: placeholder not restored during decode")
        if len(restored_map) != len(restored):  # pragma: no cover - invariant by construction
            raise PreprocessError("internal error: placeholder restore map mismatch")  # pragma: no cover
        return restored, restored_map


# ---------------------------------------------------------------------------
# Edit-aware regex substitution
# ---------------------------------------------------------------------------


def _align_replacement(replacement: str, region: str, region_map: list[int]) -> list[int]:
    """Map each replacement character to a source offset by LCS alignment.

    The replacement is aligned to the matched *region* (the original text the
    regex consumed) using their longest common subsequence. A replacement
    character is given a real source mapping only when it genuinely corresponds
    to a character that survives from the region; every other character --
    inserted, renamed, or rewritten text -- is marked :data:`GENERATED`. This
    guarantees a generated character never claims a real source position merely
    because it occupies the same positional index as the replaced source.
    """
    if not replacement:
        return []
    rows = len(replacement)
    cols = len(region)
    table = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        rchar = replacement[i]
        for j in range(cols - 1, -1, -1):
            if rchar == region[j]:
                table[i][j] = table[i + 1][j + 1] + 1
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])
    result: list[int] = []
    i = 0
    j = 0
    while i < rows:
        if j < cols and replacement[i] == region[j] and table[i][j] == table[i + 1][j + 1] + 1:
            result.append(region_map[j])
            i += 1
            j += 1
        elif j < cols and table[i][j + 1] >= table[i + 1][j]:
            j += 1
        else:
            result.append(GENERATED)
            i += 1
    return result


def _regex_sub(
    decoded: str,
    char_map: list[int],
    pattern: re.Pattern[str],
    repl: str | Callable[[re.Match[str]], str],
) -> tuple[str, list[int]]:
    """Mirror ``re.sub`` semantics while maintaining the character map.

    Matches are computed against the pre-operation string exactly like
    ``re.sub``; the replacement text is then aligned to the matched original
    region by :func:`_align_replacement` (longest common subsequence), so only
    characters that genuinely survive from the source get a real mapping.
    """
    parts: list[str] = []
    map_parts: list[list[int]] = []
    last = 0
    for match in pattern.finditer(decoded):
        start, end = match.start(), match.end()
        if start > last:
            parts.append(decoded[last:start])
            map_parts.append(char_map[last:start])
        replacement = match.expand(repl) if isinstance(repl, str) else repl(match)
        parts.append(replacement)
        map_parts.append(_align_replacement(replacement, decoded[start:end], char_map[start:end]))
        last = end
    if last < len(decoded):
        parts.append(decoded[last:])
        map_parts.append(char_map[last:])
    new_decoded = "".join(parts)
    new_map: list[int] = []
    for part in map_parts:
        new_map.extend(part)
    if len(new_map) != len(new_decoded):  # pragma: no cover - invariant by construction
        raise PreprocessError("internal error: decoded text / map length mismatch")  # pragma: no cover
    return new_decoded, new_map


def _decode_markers(text: str, mapping: dict[str, str]) -> tuple[_OpaqueRegistry, str, list[int]]:
    """Replace ``#markers`` with their mapped text, keeping strings/comments protected.

    Returns ``(registry, decoded, char_map)``: the decoded text still holds
    opaque placeholders for strings and comments. Those placeholders must
    survive :func:`_normalize_compat` untouched and are restored by
    :func:`_OpaqueRegistry.restore` at the end of the pipeline.
    """
    registry = _OpaqueRegistry(text)
    decoded, char_map = registry.protect(text)

    def _subst(m: re.Match[str]) -> str:
        tok = m.group(0)
        if tok.startswith("#01") and len(tok) > 3:
            return "(" + tok[3:]
        if tok == "#0<":
            return "*"
        if tok.startswith("#0<") and len(tok) > 3:
            return "* " + tok[3:]
        value = mapping.get(tok)
        if value is None:
            raise PreprocessError(f"Unknown compressed marker {tok!r} at character offset {m.start()}")
        return value

    decoded, char_map = _regex_sub(decoded, char_map, _MARKER_RE, _subst)
    return registry, decoded, char_map


def _date_timestamp_sub(registry: _OpaqueRegistry, _decoded: str, m: re.Match[str]) -> str:
    placeholder = m.group(2)
    original = registry.string_text(placeholder)
    if original is not None and _DATE_TIMESTAMP_PATTERN.match(original):
        return f"{m.group(1)}Time_Value {placeholder}"
    return m.group(0)


def _ensure_modulecode(_registry: _OpaqueRegistry, decoded: str, m: re.Match[str]) -> str:
    last_enddef = decoded.rfind("ENDDEF", 0, m.start())
    last_modulecode = decoded.rfind("ModuleCode", 0, m.start())
    if last_modulecode > last_enddef:
        return m.group(0)
    return "ModuleCode " + m.group(0)


def _normalize_compat(registry: _OpaqueRegistry, decoded: str, char_map: list[int]) -> tuple[str, list[int]]:
    """Apply the categorized SattLine syntax-variant repairs to decoded text.

    The rewrites are the explicitly categorized and documented steps in
    :data:`_COMPAT_TRANSFORMS`; each fixes a common ABB formatting quirk or
    grammar-incompatible spelling in decoded source (missing terminators,
    spacing, incompatible spellings, or injected default syntax). They are
    compatibility normalizations, not compressed decoding: markers are already
    substituted by :func:`_decode_markers` before this stage runs. Strings and
    comments are still protected placeholders here and are restored afterwards,
    so no repair can touch text inside them.
    """
    for transform in _COMPAT_TRANSFORMS:
        replacement = transform.replacement
        if callable(replacement):
            repl: str | Callable[[re.Match[str]], str] = partial(replacement, registry, decoded)
        else:
            repl = replacement
        decoded, char_map = _regex_sub(decoded, char_map, transform.pattern, repl)
    return decoded, char_map


def _decode_with_map(text: str, mapping: dict[str, str]) -> tuple[str, list[int]]:
    """Decode *text* with *mapping*, returning (decoded, char_map).

    Compressed decoding (:func:`_decode_markers`) and SattLine syntax-variant
    normalization (:func:`_normalize_compat`) are separate stages; string
    literals and ``(* ... *)`` comments stay protected through both and are
    restored last so provenance mapping is preserved.
    """
    registry, decoded, char_map = _decode_markers(text, mapping)
    decoded, char_map = _normalize_compat(registry, decoded, char_map)
    return registry.restore(decoded, char_map)


def decode_compressed(text: str, mapping: dict[str, str]) -> str:
    """Decode ``#markers`` using *mapping*.

    String literals and ``(* ... *)`` comments are never rewritten. Unknown
    markers raise :class:`PreprocessError` instead of being silently destroyed.
    """
    decoded, _char_map = _decode_with_map(text, mapping)
    return decoded


def preprocess_sl_text(text: str) -> tuple[str, dict[str, str]]:
    """Decode compressed text using the seed mapping (no file output).

    Returns ``(decoded_text, marker_mapping)``. The returned mapping is the
    marker substitution table; it is **not** a position map. Use
    :func:`preprocess_source` to obtain original-source provenance.
    """
    mapping = dict(SEED_MAPPING)
    decoded = decode_compressed(text, mapping)
    return decoded, mapping


def preprocess_source(text: str) -> SourceDocument:
    """Return a :class:`SourceDocument` with full original-source provenance.

    Plain text is returned as an identity document (no normalization). For
    compressed text the returned document carries the decoded text and the
    per-character map back to the original source.
    """
    if not is_compressed(text):
        return SourceDocument.identity(text)
    mapping = dict(SEED_MAPPING)
    decoded, char_map = _decode_with_map(text, mapping)
    return SourceDocument(text, decoded, tuple(char_map))
