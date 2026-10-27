"""Native identifier identity (CP1252 upper-byte folding).

SattLine compares identifiers case-insensitively using a *byte* table recovered
from the workstation build at ``00806168`` (``005b5290``, ``005b5f90``,
``005b6ce0``). The table is not Unicode case folding:

* ``a``-``z`` fold to ``A``-``Z``;
* ``0x9A`` folds to ``0x8A`` and ``0x9C`` to ``0x8C`` (single-byte pairs, so
  ``œ``/``Œ`` match but ``oe`` does not);
* ``0xE0``-``0xF6`` fold to ``0xC0``-``0xD6`` and ``0xF8``-``0xFE`` to
  ``0xD8``-``0xDE``;
* ``0xFF`` folds to ``0x9F``;
* everything else is identity, so ``0xDF`` (``ß``) does **not** fold and
  ``Straße`` never equals ``STRASSE``.

Quoted identifiers compare *including* their quote delimiters, but case folding
still applies inside them. Physical filesystem identity is a different question
and keeps using :meth:`str.casefold` in the project layer.
"""

from __future__ import annotations

__all__ = ["fold_identifier", "identifiers_equal"]


def _build_fold_bytes() -> dict[int, int]:
    """CP1252 byte -> folded byte, taken from the native upper-byte table."""
    table: dict[int, int] = {0x61 + offset: 0x41 + offset for offset in range(26)}
    table[0x9A] = 0x8A
    table[0x9C] = 0x8C
    for byte in range(0xE0, 0xF7):
        table[byte] = byte - 0x20
    for byte in range(0xF8, 0xFF):
        table[byte] = byte - 0x20
    table[0xFF] = 0x9F
    return table


_FOLD_BYTES: dict[int, int] = _build_fold_bytes()


def _fold_char(char: str) -> str:
    try:
        raw = char.encode("cp1252")
    except UnicodeEncodeError:
        # Characters outside the CP1252 profile are not folded: the native table
        # has no entry for them, and Unicode case folding is a different rule.
        return char
    folded = _FOLD_BYTES.get(raw[0])
    if folded is None:
        return char
    return bytes((folded,)).decode("cp1252")


def fold_identifier(name: str) -> str:
    """Return the native identity key for an identifier."""
    if name.isascii():
        return name.upper()
    return "".join(_fold_char(char) for char in name)


def identifiers_equal(left: str, right: str) -> bool:
    """Compare two identifiers the way the native symbol table does."""
    return fold_identifier(left) == fold_identifier(right)
