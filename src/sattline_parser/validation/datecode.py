"""DateCode arithmetic recovered from the native build.

Two separate concerns live here, and neither belongs in the parser's hot path:

* **Normalisation** of a *declared* stamp. The native reader reduces a
  non-negative literal modulo 2 000 000 000 (`005ab1b0`, `005ccaa0`). We keep the
  raw source integer in the AST so round-trips stay lossless and expose the
  reduction here for semantic consumers.
* **Generation** of a *new* stamp from the clock (`005cb910`). This is what an
  editor does when it imports a definition; parsing must never call it, because
  synthesising a stamp would rewrite the file the user opened (DATE-02/DATE-03).

A negative literal needs the native signed arithmetic, which is not recovered;
:func:`normalized_datecode` refuses instead of applying Python's modulo, whose
sign convention differs from C's.
"""

from __future__ import annotations

__all__ = ["DATECODE_MODULUS", "compute_datecode", "normalized_datecode"]

#: Native reduction modulus for declared stamps (DATE-01).
DATECODE_MODULUS = 2_000_000_000


def normalized_datecode(value: int) -> int:
    """Return the stamp the native reader stores for a non-negative literal.

    Negative literals raise: the recovered evidence only covers ``n >= 0`` and
    Python's ``%`` would silently disagree with plain C signed arithmetic.
    """
    if value < 0:
        raise ValueError(
            f"DateCode {value} is negative; the native signed reduction is not recovered, "
            "so no normalised value is claimed"
        )
    return value % DATECODE_MODULUS


def compute_datecode(internal_day: int, milliseconds_of_day: int) -> int:
    """Return the native "new DateCode" for a clock reading (DATE-02).

    Native ``005cb910`` computes ``(internal_day % 100 + 1) * (milliseconds_of_day
    // 10)``. The result is neither reversible nor monotonic, so it must never be
    used as a version or cache key.
    """
    return (internal_day % 100 + 1) * (milliseconds_of_day // 10)
