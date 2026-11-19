"""Helpers for decoding compressed SattLine text before parsing.

The decoder is *lexically aware*: string literals, quoted identifiers, and
structural ``(* ... *)`` comments are copied through untouched, and marker
substitution runs only on the text between them, so syntax-looking text inside
a string or comment can never be rewritten accidentally. The region boundaries
are carried out of band, so no placeholder is spliced into the text: a source
that happens to contain a sequence resembling an internal marker is ordinary
text and cannot change the result.

The decoder also builds a per-character map from the decoded (normalized) text
back to the original source, so the parser can report AST spans and diagnostics
against the original source (:class:`sattline_parser.source_document.SourceDocument`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import cast

import regex

from sattline_parser.grammar import constants as const
from sattline_parser.source_document import GENERATED, SourceDocument

__all__ = [
    "SCANNER_TOKENS",
    "PreprocessError",
    "decode_compressed",
    "is_compressed",
    "preprocess_sl_text",
    "preprocess_source",
]

#: SattLine scanner token table: compact code (``#`` + two chars from the
#: ASCII run ``0`` to ``?``) -> source spelling. The scanner ordinal ``n`` is
#: encoded as ``'#' + chr(48 + n // 16) + chr(48 + n % 16)``; entries are checked
#: against the compressed/uncompressed full-grammar pair. The table covers
#: keywords and operators only; literal source text is emitted unencoded by the
#: compressor.
_TOKEN_DATA_PATH = Path(__file__).with_name("scanner_tokens.json")
_TOKEN_DATA: dict[str, str] = {
    row["code"]: row["text"]
    for row in cast("list[dict[str, str]]", json.loads(_TOKEN_DATA_PATH.read_text(encoding="utf-8")))
}

#: Read-only view of the token table: decoding must be a pure function, so no
#: caller may mutate the mapping that every later decode reads.
SCANNER_TOKENS: Mapping[str, str] = MappingProxyType(_TOKEN_DATA)

#: A compact marker: ``#`` plus exactly two characters from the ASCII run
#: ``0`` to ``?``. The scanner ordinal is encoded in that run, so a shorter or
#: letter-bearing ``#`` sequence is ordinary text, not a marker.
_MARKER_RE = re.compile(r"#[0-?]{2}")
_WHITESPACE_RE = re.compile(r"\s+")
#: The pipeline's one line-terminator definition. CRLF, LF, and a lone CR each
#: end a line, in the header scan, the compressed-source scanner, the coded
#: decoder, ``line_col``, and :func:`render_ide_text` alike.
_LINE_BREAK_RE = re.compile(r"[\r\n]")


def _header_compression_flag(text: str) -> str | None:
    """Return the ``C``/``N`` compression flag from the first-line header, or ``None``.

    SattLine files begin with a quoted header line like::

        "Syntax version 2.23, date: 2026-08-26-11:48:22.200 C"

    where the final character before the closing quote is ``C`` (compressed)
    or ``N`` (normal). The first line ends at CRLF, LF, or a lone CR, the same
    line breaks the rest of the pipeline uses.
    """
    line_break = _LINE_BREAK_RE.search(text)
    first_line = text[: line_break.start()].strip() if line_break is not None else text.strip()
    if first_line.startswith('"') and first_line.endswith('"'):
        body = first_line[1:-1].rstrip()
        if body and body[-1] in ("C", "N"):
            return body[-1]
    return None


class PreprocessError(ValueError):
    """Raised when compressed SattLine source cannot be decoded safely.

    Distinct from Lark parse errors: this signals malformed compressed input
    (for example an unknown ``#marker``) rather than a syntax error in the
    decoded program.
    """


def _markers_outside_opaque_regions(text: str) -> list[str]:
    """Return ``#marker`` matches that lie entirely outside strings/comments.

    Detection must agree with the decoder (:func:`_decode_with_map`), which
    skips string literals, quoted identifiers, and ``(* ... *)`` comments
    before any rewrite. A marker that overlaps an opaque region (for example a
    ``#``-sequence inside a string literal) is never decoded and must therefore
    not count toward the compressed heuristic -- otherwise plain source
    containing such text would be misclassified as compressed and preprocessed.
    """
    regions = scan_opaque_regions(text)
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


#: Thresholds that classify a marker-dense source as compressed. They are
#: heuristics: a source with this many markers (or this share of marker
#: characters) is compact-encoded even when it also carries structure words.
_MARKER_COUNT_STRONG = 50
_MARKER_CHAR_RATIO = 0.02
_MARKER_COUNT_WEAK = 10

#: Structural keywords a real source body names at least once.
_STRUCTURAL_KEYWORDS = (
    const.GRAMMAR_VALUE_MODULEDEFINITION,
    const.GRAMMAR_VALUE_TYPEDEFINITIONS,
    const.GRAMMAR_VALUE_MODULEPARAMETERS,
    const.GRAMMAR_VALUE_EQUATIONBLOCK,
)


def _mask_opaque_regions(text: str) -> str:
    """Return *text* with every string and comment span replaced by spaces."""
    parts: list[str] = []
    cursor = 0
    for _kind, start, end in scan_opaque_regions(text):
        parts.append(text[cursor:start])
        parts.append(" " * (end - start))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def is_compressed(text: str) -> bool:
    """Detect compressed SattLine format.

    The **header flag** is authoritative: if the first line ends with ``C``
    the source is compressed; if it ends with ``N`` it is plain.  The flag
    is absent only when the file was not produced by a standard SattLine
    export, in which case the marker-based heuristic is used.
    """
    flag = _header_compression_flag(text)
    if flag == "C":
        return True
    if flag == "N":
        return False
    markers = _markers_outside_opaque_regions(text)
    if not markers:
        return False
    compact_len = max(len(_WHITESPACE_RE.sub("", text)), 1)
    marker_char_ratio = len("".join(markers)) / compact_len
    marker_count = len(markers)
    # A genuine source always names at least one structural keyword somewhere
    # outside its strings and comments; marker-dense text without one is
    # compressed. Opaque regions are masked first so a keyword inside a comment
    # cannot veto the classification.
    visible = _mask_opaque_regions(text)
    keyword_hits = sum(1 for kw in _STRUCTURAL_KEYWORDS if kw in visible)
    if marker_count >= _MARKER_COUNT_STRONG or marker_char_ratio >= _MARKER_CHAR_RATIO:
        return True
    return marker_count >= _MARKER_COUNT_WEAK and keyword_hits == 0


# ---------------------------------------------------------------------------
# Lexically-aware protection of string literals and comments
# ---------------------------------------------------------------------------


#: One character the grammar accepts at the start of an unquoted name, and one
#: it accepts inside a name. Both come from ``grammar/constants.py`` so the
#: scanner and the lexer cannot drift apart: a name may not begin with a digit,
#: and an apostrophe inside an unquoted name is name text rather than the start
#: of a quoted identifier.
_NAME_START_RE = regex.compile(f"[{const.GRAMMAR_CHARSET_NAME_START}]")
_NAME_TEXT_RE = regex.compile(f"[{const.GRAMMAR_CHARSET_NAME}]+")
#: A quoted identifier, exactly as the lexer's ``NAME`` terminal spells it: no
#: apostrophe inside, no line break, at least one character.
_QUOTED_NAME_RE = regex.compile(const.GRAMMAR_PATTERN_QUOTED_NAME)


def _scan_opaque_regions(text: str) -> list[tuple[str, int, int, bool]]:
    """Return ``(kind, start, end, closed)`` for every string and comment.

    ``closed`` is ``False`` for a ``(* ... *)`` comment whose nesting depth is
    still positive at the end of the text. Strings always report ``True``: an
    unterminated description ends at the line break by grammar rule, so it has a
    real boundary.
    """
    regions: list[tuple[str, int, int, bool]] = []
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
            regions.append(("C", index, cursor, depth == 0))
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
                if text[cursor] in "\r\n":
                    # The grammar accepts an unterminated description up to the
                    # line break, and no string spans lines.
                    break
                cursor += 1
            regions.append(("S", index, cursor, True))
            index = cursor
        elif text[index] == "'" and (quoted := _QUOTED_NAME_RE.match(text, index)) is not None:
            regions.append(("S", index, quoted.end(), True))
            index = quoted.end()
        else:
            # Consume a whole name run. An apostrophe inside an unquoted name
            # such as ``Pump'A`` is name text, and a quoted identifier may not
            # span a line, so only a run that starts at a name start character
            # is skipped here; anything else is ordinary code text.
            run = _NAME_TEXT_RE.match(text, index) if _NAME_START_RE.match(text, index) else None
            index = run.end() if run is not None else index + 1
    return regions


def scan_opaque_regions(text: str) -> list[tuple[str, int, int]]:
    """Return ``(kind, start, end)`` for every string ('S') and comment ('C').

    The scanner follows the grammar's lexical boundaries: nested ``(* ... *)``
    comments, doubled ``""`` escapes, a string or a variable description that
    ends at a line break (``STRING_CRLF`` accepts an unterminated description),
    and a single-quoted identifier such as ``'#84'``, whose body is literal
    text rather than a marker.
    """
    return [(kind, start, end) for kind, start, end, _closed in _scan_opaque_regions(text)]


def closed_comment_spans(text: str) -> list[tuple[int, int]]:
    """Return the span of every ``(* ... *)`` comment that is properly closed.

    A comment whose nesting depth is still positive at the end of the text is
    left out: there is no reliable boundary for it, so a caller must not treat
    its body as safe to rewrite.
    """
    return [(start, end) for kind, start, end, closed in _scan_opaque_regions(text) if kind == "C" and closed]


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
    if not set(replacement) & set(region):
        # No character survives from the matched region, so the LCS table would
        # be empty and every replacement character is generated. This is the
        # common case: a `#NN` code shares no character with the keyword it
        # expands to.
        return [GENERATED] * len(replacement)
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
    new_map: list[int] = []
    last = 0
    for match in pattern.finditer(decoded):
        start, end = match.start(), match.end()
        if start > last:
            parts.append(decoded[last:start])
            new_map.extend(char_map[last:start])
        replacement = match.expand(repl) if isinstance(repl, str) else repl(match)
        parts.append(replacement)
        new_map.extend(_align_replacement(replacement, decoded[start:end], char_map[start:end]))
        last = end
    if last < len(decoded):
        parts.append(decoded[last:])
        new_map.extend(char_map[last:])
    new_decoded = "".join(parts)
    if len(new_map) != len(new_decoded):  # pragma: no cover - invariant by construction
        raise PreprocessError("internal error: decoded text / map length mismatch")  # pragma: no cover
    return new_decoded, new_map


def _decode_markers_in_run(
    text: str,
    start: int,
    end: int,
    mapping: Mapping[str, str],
    parts: list[str],
    char_map: list[int],
) -> None:
    """Decode the markers of one non-opaque ``[start, end)`` run into *parts*.

    The run's own source offsets are its initial map, so an unknown marker is
    reported at its character offset in the **original** source even when
    earlier text has already been rewritten.
    """
    if start >= end:
        return
    run_map = list(range(start, end))

    def _subst(match: re.Match[str]) -> str:
        tok = match.group(0)
        value = mapping.get(tok)
        if value is None:
            raise PreprocessError(f"Unknown compressed marker {tok!r} at character offset {run_map[match.start()]}")
        return value

    decoded, decoded_map = _regex_sub(text[start:end], run_map, _MARKER_RE, _subst)
    parts.append(decoded)
    char_map.extend(decoded_map)


def _decode_with_map(text: str, mapping: Mapping[str, str]) -> tuple[str, list[int]]:
    """Decode *text* with *mapping*, returning ``(decoded, char_map)``.

    The opaque regions (string literals, quoted identifiers, ``(* ... *)``
    comments) are copied through byte for byte and keep their exact source
    offsets. Marker substitution runs only on the runs between them, and the
    region boundaries are carried out of band: no placeholder is ever spliced
    into the text, so a source that spells something resembling an internal
    marker is ordinary text and neither grows nor injects anything. A
    replacement that does not survive from its matched region is
    :data:`GENERATED` rather than given a fake original offset.
    """
    parts: list[str] = []
    char_map: list[int] = []
    cursor = 0
    for _kind, start, end in scan_opaque_regions(text):
        _decode_markers_in_run(text, cursor, start, mapping, parts, char_map)
        parts.append(text[start:end])
        char_map.extend(range(start, end))
        cursor = end
    _decode_markers_in_run(text, cursor, len(text), mapping, parts, char_map)
    decoded = "".join(parts)
    if len(char_map) != len(decoded):  # pragma: no cover - invariant by construction
        raise PreprocessError("internal error: decoded text / map length mismatch")  # pragma: no cover
    return decoded, char_map


def decode_compressed(text: str, mapping: Mapping[str, str]) -> str:
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
    mapping = dict(SCANNER_TOKENS)
    decoded = decode_compressed(text, mapping)
    return decoded, mapping


def preprocess_source(text: str) -> SourceDocument:
    """Return a :class:`SourceDocument` with full original-source provenance.

    Plain text is returned as an identity document (no normalization). For
    compressed text the returned document carries the decoded text and the
    per-character map back to the original source. A compressed file that
    decodes to the text it started from (a header-flagged file with no markers)
    is also returned as an identity document, because there is nothing to map.
    """
    if not is_compressed(text):
        return SourceDocument.identity(text)
    # A header-flagged compact file is *coded* by definition; the density
    # heuristic also fires on partially hand-coded text where raw keywords are
    # ordinary source. The two are distinguished per token from the character
    # provenance (see ``grammar.sattline_lexer``).
    mapping = dict(SCANNER_TOKENS)
    decoded, char_map = _decode_with_map(text, mapping)
    if decoded == text:
        return SourceDocument.identity(text)
    return SourceDocument(text, decoded, tuple(char_map))
