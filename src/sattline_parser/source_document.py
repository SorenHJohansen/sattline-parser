"""Source provenance: mapping normalized/decoded text back to the original source.

The parser pipeline may decode/preprocess compressed SattLine text before the
Lark parser sees it. Lark therefore reports positions in the *normalized* text,
while AST spans and diagnostics must refer to the *original* source.

:class:`SourceDocument` carries the original text, the normalized text, and a
per-character map from normalized offsets back to original offsets. The mapping
distinguishes four situations:

* **Exact mappings** -- characters that exist in the original source map to
  their exact original offset.
* **Generated characters** -- inserted text with no exact source equivalent
  (for example a trailing ``;`` injected by the decoder) maps to the
  first-class :data:`GENERATED` marker (:class:`Generated`, value ``-1``) and
  is *anchored* to the nearest preceding real source offset when a position or
  range is requested. A generated character never claims an exact original
  position of its own.
* **Anchor positions** -- generated characters and end-of-input boundaries map
  through their nearest real source character (the anchor). Generated text
  inside a span is covered by the anchor's original range.
* **Deleted source regions** -- original text removed by the preprocessor has
  no normalized counterpart and therefore no map entries. A range spanning the
  surviving text around a deleted region necessarily includes the deleted
  region in its original-range result; the map never invents a position for
  deleted text itself.

The per-character map is ``tuple[int, ...]``; every entry is either a real
original offset (``>= 0``) or the :data:`GENERATED` sentinel. The sentinel is
a distinct type rather than a bare ``-1`` so code that builds or rewrites maps
can tell "this character was inserted by the preprocessor" apart from an
ordinary offset value, and so a generated character can never be mistaken for
(and never silently becomes) a real source position.

Spans use the half-open model ``[start, end)`` in both coordinate systems, so
an end offset equal to the length of a text is a valid boundary. A normalized
offset at or past the end of the normalized text maps to the original boundary
just after the last real source character, never to the position of the final
character.
"""

from __future__ import annotations

from bisect import bisect_right

from lark import Token, Tree
from lark.exceptions import UnexpectedCharacters, UnexpectedInput
from lark.tree import Meta

from sattline_parser.models.ast_model import SourceSpan

__all__ = [
    "GENERATED",
    "Generated",
    "SourceDocument",
    "remap_parse_error",
    "remap_tree_to_original",
]


class Generated(int):
    """First-class provenance marker for generated (inserted) characters.

    A generated character has no exact original-source offset. In the
    per-character source map it is stored as this distinct type with value
    ``-1``; :class:`SourceDocument` anchors it to the nearest real source
    character when a position or range is requested. Subclassing ``int`` keeps
    the map compatible with offset arithmetic and ``>= 0`` checks while giving
    generated provenance a verifiable, first-class type (``isinstance(entry,
    Generated)``), so a generated character is never conflated with a real
    offset merely because it occupies a position in the normalized text.
    """

    __slots__ = ()

    def __new__(cls) -> Generated:
        return int.__new__(cls, -1)

    def __repr__(self) -> str:
        return "GENERATED"


GENERATED = Generated()


def _line_starts(text: str) -> tuple[int, ...]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return tuple(starts)


class SourceDocument:
    """Original text, normalized text, and the mapping between the two.

    ``char_map`` maps each character offset of ``normalized_text`` to the
    corresponding offset in ``original_text``, or :data:`GENERATED` when the
    character was produced by the preprocessor (inserted/generated text).
    """

    __slots__ = ("_char_map", "_is_identity", "_line_starts", "normalized_text", "original_text")

    def __init__(self, original_text: str, normalized_text: str, char_map: tuple[int, ...]) -> None:
        if len(char_map) != len(normalized_text):
            raise ValueError("char_map length must match normalized_text length")
        self.original_text = original_text
        self.normalized_text = normalized_text
        self._char_map = char_map
        self._line_starts = _line_starts(original_text)
        self._is_identity = original_text == normalized_text

    @classmethod
    def identity(cls, text: str) -> SourceDocument:
        """A source document where normalized text equals the original text."""
        return cls(text, text, tuple(range(len(text))))

    def is_identity(self) -> bool:
        """True when no preprocessing took place (original == normalized)."""
        return self._is_identity

    def map_position(self, norm_offset: int) -> int | None:
        """Map a normalized offset to an original offset.

        Returns the exact original offset when the character exists in the
        original source. For generated characters, returns the nearest
        preceding original offset (its anchor). An offset at or past the end of
        the normalized text is the end-of-input boundary: it maps to the
        original boundary just after the last real source character (a valid
        half-open ``end`` offset), so EOF is a boundary, never the position of
        the final character. Returns ``None`` only for a negative input offset.
        """
        if norm_offset < 0:
            return None
        if norm_offset >= len(self._char_map):
            cursor = len(self._char_map) - 1
            while cursor >= 0:
                value = self._char_map[cursor]
                if value >= 0:
                    return value + 1
                cursor -= 1
            return 0
        value = self._char_map[norm_offset]
        if value >= 0:
            return value
        cursor = norm_offset - 1
        while cursor >= 0:
            value = self._char_map[cursor]
            if value >= 0:
                return value
            cursor -= 1
        return 0

    def map_range(self, norm_start: int, norm_end: int) -> tuple[int, int]:
        """Map a normalized half-open range to the tightest original range.

        The result is the smallest contiguous original range whose real
        characters cover the real characters of the normalized range. Text that
        the preprocessor deleted has no normalized counterpart, so a range that
        spans the surviving text around it includes the deleted region in the
        result. Generated characters inside the range are anchored to the
        nearest real original position, so the returned range always points
        into the original source without inventing positions.

        An empty range (``norm_start >= norm_end``) maps to a zero-width range
        at the mapped boundary position. A range ending at the end of the
        normalized text maps to the corresponding original end boundary.
        """
        if norm_start >= norm_end:
            boundary = self.map_position(norm_start)
            pos = 0 if boundary is None else boundary
            return pos, pos
        mapped_start = self.map_position(norm_start)
        start = 0 if mapped_start is None else mapped_start
        end: int | None = None
        cursor = norm_end - 1
        while cursor >= norm_start:
            if 0 <= cursor < len(self._char_map):
                value = self._char_map[cursor]
                if value >= 0:
                    end = value + 1
                    break
            cursor -= 1
        if end is None:
            cursor = norm_end
            while cursor < len(self._char_map):
                value = self._char_map[cursor]
                if value >= 0:
                    end = value + 1
                    break
                cursor += 1
        if end is None:
            end = len(self.original_text)
        return start, end

    def line_col(self, orig_offset: int) -> tuple[int, int]:
        """Return the one-based (line, column) for an original offset."""
        if orig_offset < 0:
            orig_offset = 0
        if orig_offset > len(self.original_text):
            orig_offset = len(self.original_text)
        index = bisect_right(self._line_starts, orig_offset) - 1
        line = index + 1
        column = orig_offset - self._line_starts[index] + 1
        return line, column

    def span_from_normalized(self, norm_start: int, norm_end: int) -> SourceSpan | None:
        """Build an original-source :class:`SourceSpan` from a normalized range."""
        start, end = self.map_range(norm_start, norm_end)
        line, column = self.line_col(start)
        return _build_span(start, end, line, column)


def _build_span(start: int, end: int, line: int, column: int) -> SourceSpan:
    return SourceSpan(start=start, end=end, line=line, column=column)


def _remap_token(token: Token, doc: SourceDocument) -> None:
    start_pos = getattr(token, "start_pos", None)
    end_pos = getattr(token, "end_pos", None)
    if not isinstance(start_pos, int) or not isinstance(end_pos, int):
        return
    mapped_start = doc.map_position(start_pos)
    mapped_end = doc.map_position(end_pos - 1)
    if mapped_start is None or mapped_end is None:
        return
    token.start_pos = mapped_start
    token.end_pos = mapped_end + 1
    line, column = doc.line_col(mapped_start)
    token.line = line
    token.column = column
    end_line, end_column = doc.line_col(token.end_pos)
    token.end_line = end_line
    token.end_column = end_column


def _remap_meta(meta: Meta, doc: SourceDocument) -> None:
    start_pos = getattr(meta, "start_pos", None)
    end_pos = getattr(meta, "end_pos", None)
    if not isinstance(start_pos, int) or not isinstance(end_pos, int):
        return
    mapped_start = doc.map_position(start_pos)
    mapped_end = doc.map_position(end_pos - 1)
    if mapped_start is None or mapped_end is None:
        return
    meta.start_pos = mapped_start
    meta.end_pos = mapped_end + 1
    line, column = doc.line_col(mapped_start)
    meta.line = line
    meta.column = column
    end_line, end_column = doc.line_col(meta.end_pos)
    meta.end_line = end_line
    meta.end_column = end_column


def _walk(node: Token | Tree[Token], doc: SourceDocument) -> None:
    if isinstance(node, Tree):
        tree_node = node
        _remap_meta(tree_node.meta, doc)
        for child in tree_node.children:
            _walk(child, doc)
    else:
        _remap_token(node, doc)


def remap_tree_to_original(tree: Tree[Token], doc: SourceDocument) -> None:
    """Rewrite every position in *tree* from normalized to original coordinates.

    ``tree`` is mutated in place so that ``meta`` and ``Token`` positions refer
    to the original source. This is a no-op for identity documents.
    """
    if doc.is_identity():
        return
    _walk(tree, doc)


def remap_parse_error(exc: Exception, doc: SourceDocument) -> None:
    """Rewrite an UnexpectedInput's position fields to original coordinates.

    Mutates ``line``, ``column``, ``pos_in_stream`` (and the offending token's
    position when present) so downstream diagnostics, logging, and callers
    reading the exception attributes all see original-source locations.
    """
    if not isinstance(exc, UnexpectedInput):
        return
    pos = getattr(exc, "pos_in_stream", None)
    mapped: int | None = None
    if isinstance(pos, int):
        mapped = doc.map_position(pos)
        if mapped is not None:
            line, column = doc.line_col(mapped)
            exc.pos_in_stream = mapped  # type: ignore[assignment]  # runtime-only attribute
            exc.line = line
            exc.column = column
    if isinstance(exc, UnexpectedCharacters) and mapped is not None and 0 <= mapped < len(doc.original_text):
        exc.char = doc.original_text[mapped]
        exc._context = exc.get_context(doc.original_text)  # pyright: ignore[reportPrivateUsage]
    token = getattr(exc, "token", None)
    if isinstance(token, Token):
        token_pos = getattr(token, "start_pos", None)
        if isinstance(token_pos, int):
            mapped_token = doc.map_position(token_pos)
            if mapped_token is not None:
                token.start_pos = mapped_token
                line, column = doc.line_col(mapped_token)
                token.line = line
                token.column = column
    exc._sattline_remapped = True  # type: ignore[attr-defined]  # runtime tag consumed by diagnostics
