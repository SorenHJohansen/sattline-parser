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

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

from sattline_parser.source_document import GENERATED, SourceDocument

__all__ = [
    "SCANNER_TOKENS",
    "SEED_MAPPING",
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
SCANNER_TOKENS: dict[str, str] = {
    row["code"]: row["text"]
    for row in cast("list[dict[str, str]]", json.loads(_TOKEN_DATA_PATH.read_text(encoding="utf-8")))
}

#: Historical name for :data:`SCANNER_TOKENS`, kept for API compatibility.
SEED_MAPPING: dict[str, str] = SCANNER_TOKENS

_MARKER_RE = re.compile(r"#[0-9A-Za-z;:=><?]{1,2}")
_WHITESPACE_RE = re.compile(r"\s+")


def _header_compression_flag(text: str) -> str | None:
    """Return the ``C``/``N`` compression flag from the first-line header, or ``None``.

    SattLine files begin with a quoted header line like::

        "Syntax version 2.23, date: 2026-08-26-11:48:22.200 C"

    where the final character before the closing quote is ``C`` (compressed)
    or ``N`` (normal).
    """
    nl = text.find("\n")
    first_line = text[:nl].strip() if nl >= 0 else text.strip()
    if first_line.startswith('"') and first_line.endswith('"'):
        body = first_line[1:-1].rstrip()
        if body and body[-1] in ("C", "N"):
            return body[-1]
    return None


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


def scan_opaque_regions(text: str) -> list[tuple[str, int, int]]:
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
        for kind, start, end in scan_opaque_regions(text):
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
    opaque placeholders for strings and comments, which are restored by
    :func:`_OpaqueRegistry.restore` at the end of the pipeline.
    """
    registry = _OpaqueRegistry(text)
    decoded, char_map = registry.protect(text)

    def _subst(m: re.Match[str]) -> str:
        tok = m.group(0)
        value = mapping.get(tok)
        if value is None:
            raise PreprocessError(f"Unknown compressed marker {tok!r} at character offset {m.start()}")
        return value

    decoded, char_map = _regex_sub(decoded, char_map, _MARKER_RE, _subst)
    return registry, decoded, char_map


def _decode_with_map(text: str, mapping: dict[str, str]) -> tuple[str, list[int]]:
    """Decode *text* with *mapping*, returning (decoded, char_map).

    String literals and ``(* ... *)`` comments stay protected through
    decoding and are restored last so provenance mapping is preserved.
    """
    registry, decoded, char_map = _decode_markers(text, mapping)
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
    # A header-flagged compact file is *coded* by definition; the density
    # heuristic also fires on partially hand-coded text where raw keywords are
    # ordinary source. The two are distinguished per token from the character
    # provenance (see ``grammar.sattline_lexer``).
    mapping = dict(SEED_MAPPING)
    decoded, char_map = _decode_with_map(text, mapping)
    return SourceDocument(text, decoded, tuple(char_map))
