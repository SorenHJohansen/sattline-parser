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

from sattline_parser.source_document import SourceDocument

__all__ = [
    "SEED_MAPPING",
    "PreprocessError",
    "decode_compressed",
    "is_compressed",
    "preprocess_sl_text",
    "preprocess_source",
]

_GENERATED = -1

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
    "#;0": "Digits_",
    "#;1": "NoOf_",
    "#;3": "SetApp_",
    "#;4": "Two_Layers_",
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
    for match in _MARKER_RE.finditer(text):
        start, end = match.start(), match.end()
        if any(start < region_end and region_start < end for _kind, region_start, region_end in regions):
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
            map_parts.append([_GENERATED] * len(placeholder))
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
        for match in reversed(list(_PLACEHOLDER_RE.finditer(decoded))):
            placeholder = match.group(0)
            kind = placeholder[1]
            index = int(placeholder[2:-1])
            entries = self._strings if kind == "S" else self._comments
            if not (0 <= index < len(entries)):
                raise PreprocessError(f"internal error: unknown placeholder {placeholder!r}")
            orig_start, orig_text = entries[index]
            start, end = match.start(), match.end()
            decoded = decoded[:start] + orig_text + decoded[end:]
            char_map = char_map[:start] + [orig_start + i for i in range(len(orig_text))] + char_map[end:]
        if "\x00" in decoded:
            raise PreprocessError("internal error: placeholder not restored during decode")
        return decoded, char_map


# ---------------------------------------------------------------------------
# Edit-aware regex substitution
# ---------------------------------------------------------------------------


def _regex_sub(
    decoded: str,
    char_map: list[int],
    pattern: re.Pattern[str],
    repl: str | Callable[[re.Match[str]], str],
) -> tuple[str, list[int]]:
    """Mirror ``re.sub`` semantics while maintaining the character map.

    Matches are computed against the pre-operation string exactly like
    ``re.sub``; the replacement text is then left-aligned onto the matched
    original region so position mapping stays anchored to real source.
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
        region = char_map[start:end]
        replacement_map: list[int] = []
        for index, _char in enumerate(replacement):
            if index < len(region) and region[index] >= 0:
                replacement_map.append(region[index])
            else:
                replacement_map.append(_GENERATED)
        map_parts.append(replacement_map)
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


def _normalize_compat(registry: _OpaqueRegistry, decoded: str, char_map: list[int]) -> tuple[str, list[int]]:
    """Apply SattLine syntax-variant repairs to already-decoded text.

    These rewrites fix common ABB formatting quirks in decoded source (missing
    terminators, spacing, grammar-incompatible spellings). They are
    compatibility normalizations, not compressed decoding: markers are already
    substituted by :func:`_decode_markers` before this stage runs. Strings and
    comments are still protected placeholders here and are restored afterwards,
    so no repair can touch text inside them.
    """

    def _date_timestamp_sub(m: re.Match[str]) -> str:
        placeholder = m.group(2)
        original = registry.string_text(placeholder)
        if original is not None and _DATE_TIMESTAMP_PATTERN.match(original):
            return f"{m.group(1)}Time_Value {placeholder}"
        return m.group(0)

    def _ensure_modulecode(m: re.Match[str]) -> str:
        last_enddef = decoded.rfind("ENDDEF", 0, m.start())
        last_modulecode = decoded.rfind("ModuleCode", 0, m.start())
        if last_modulecode > last_enddef:
            return m.group(0)
        return "ModuleCode " + m.group(0)

    # Normalize common ABB formatting quirks
    decoded, char_map = _regex_sub(decoded, char_map, _ENDDEF_TRAILING_SEMI_RE, "ENDDEF")
    decoded, char_map = _regex_sub(decoded, char_map, _SEMI_BEFORE_ASSIGN_RE, " :=")
    decoded, char_map = _regex_sub(decoded, char_map, _ENDIF_SEMI_COMMA_RE, "ENDIF,")
    decoded, char_map = _regex_sub(decoded, char_map, _ENDIF_SEMI_PAREN_RE, "ENDIF)")
    decoded, char_map = _regex_sub(decoded, char_map, _EMPTY_ASSIGN_RE, ":= Default;")
    decoded, char_map = _regex_sub(decoded, char_map, _GRAPHOBJECTS_INTERACT_RE, "InteractObjects")
    decoded, char_map = _regex_sub(decoded, char_map, _DURATION_STR_RE, r"\1Duration_Value \2")
    decoded, char_map = _regex_sub(decoded, char_map, _TIME_STR_RE, r"\1Time_Value \2")
    decoded, char_map = _regex_sub(decoded, char_map, _DATE_TIMESTAMP_RE, _date_timestamp_sub)
    decoded, char_map = _regex_sub(decoded, char_map, _EXECUTE_LOCAL_ENDDEF_RE, r"\1; ENDDEF")
    decoded, char_map = _regex_sub(decoded, char_map, _EXECUTE_STATE_IF_RE, r"\1; IF")
    # Ensure IF statements terminate with ';' (but not inside expressions)
    decoded, char_map = _regex_sub(decoded, char_map, _ENDIF_NO_TERM_RE, "ENDIF;")
    # Drop empty GraphObjects sections before ENDDEF
    decoded, char_map = _regex_sub(decoded, char_map, _GRAPHOBJECTS_ENDDEF_RE, "ENDDEF")
    # Ensure variable groups end with ';' before ENDDEF
    decoded, char_map = _regex_sub(decoded, char_map, _TYPE_ENDDEF_RE, r"\1 ; ENDDEF")
    # Normalize Enable_ tails to use InVar_ for grammar compatibility
    decoded, char_map = _regex_sub(decoded, char_map, _ENABLE_OUTVAR_RE, r"\1 InVar_")
    # Avoid BOOL tokenizing identifiers like TrueVar
    decoded, char_map = _regex_sub(decoded, char_map, _TRUEVAR_RE, "TTrueVar")
    # Inject missing ModuleCode before EQUATIONBLOCK when none exists in the same module
    decoded, char_map = _regex_sub(decoded, char_map, _EQUATIONBLOCK_RE, _ensure_modulecode)
    # Fill empty trailing function arguments (e.g., "Func(a, )")
    decoded, char_map = _regex_sub(decoded, char_map, _EMPTY_TRAILING_ARG_RE, r"\1(\2, 0)")
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
