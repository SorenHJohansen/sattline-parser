"""Built-in function and datatype tables used by the strict validation pass.

The function signatures are the corpus-documented subset of the SattLine
built-in library (exercised by ``tests/fixtures/corpus``). Unknown call names
are intentionally left alone: only calls whose name appears in
:data:`BUILTIN_FUNCTIONS` are arity/direction-checked, so real-world modules
that use library entries we do not yet model pass through unvalidated.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Final

from sattline_parser.models.ast_model import Simple_DataType
from sattline_parser.validation.names import fold_identifier

#: Canonical (casefolded) names of all primitive datatypes. ``Variable`` normalises
#: recognised names to ``Simple_DataType`` at init; anything left as ``str`` after
#: parsing is a custom (record) type name, so only those strings are candidates for a
#: built-in-name typo.
BUILTIN_DATATYPE_NAMES: Final[frozenset[str]] = frozenset(member.value for member in Simple_DataType)

#: Near-miss similarity cutoff used when suggesting a built-in datatype for a
#: custom name. Kept high enough that unrelated record names are never flagged.
_BUILTIN_TYPO_CUTOFF: Final[float] = 0.82


@dataclass(frozen=True, slots=True)
class BuiltinFunction:
    """Signature of a SattLine built-in call.

    ``min_args`` / ``max_args`` bound the accepted argument count,
    ``out_arg_positions`` lists 1-based argument positions that must resolve to
    a writable variable reference (a built-in writes through those).
    """

    name: str
    min_args: int
    max_args: int
    out_arg_positions: frozenset[int] = frozenset()


def _build_builtin_functions() -> dict[str, BuiltinFunction]:
    spec: dict[str, tuple[int, int, frozenset[int]]] = {
        "copytime": (2, 2, frozenset({2})),
        "copyvariable": (3, 3, frozenset({2, 3})),
        "copystring": (3, 3, frozenset({2, 3})),
        "equal": (2, 2, frozenset()),
        "equalstrings": (3, 3, frozenset()),
        "getstringpos": (1, 1, frozenset()),
        "setstringpos": (3, 3, frozenset({2, 3})),
        "stringlength": (1, 1, frozenset()),
    }
    return {name: BuiltinFunction(name, *arity) for name, arity in spec.items()}


#: Lower-case canonical name -> signature.
BUILTIN_FUNCTIONS: Final[dict[str, BuiltinFunction]] = _build_builtin_functions()

#: Native identity key (folded) -> signature. Function names are case-insensitive.
_FOLDED_FUNCTIONS: Final[dict[str, BuiltinFunction]] = {
    fold_identifier(name): signature for name, signature in BUILTIN_FUNCTIONS.items()
}
_FOLDED_DATATYPE_NAMES: Final[dict[str, str]] = {fold_identifier(name): name for name in BUILTIN_DATATYPE_NAMES}


def is_builtin_function(name: str) -> bool:
    return fold_identifier(name) in _FOLDED_FUNCTIONS


def builtin_function_signature(name: str) -> BuiltinFunction | None:
    return _FOLDED_FUNCTIONS.get(fold_identifier(name))


def builtin_datatype_typo(datatype: str) -> str | None:
    """Return the built-in datatype name a custom datatype string seems to misspell.

    Only fires for names that are not exact matches (those are already normalised
    to ``Simple_DataType`` by ``Variable``) and that sit within the similarity
    cutoff of exactly one built-in; otherwise ``None``.
    """
    matches = difflib.get_close_matches(
        fold_identifier(datatype), sorted(_FOLDED_DATATYPE_NAMES), n=1, cutoff=_BUILTIN_TYPO_CUTOFF
    )
    return _FOLDED_DATATYPE_NAMES[matches[0]] if matches else None
