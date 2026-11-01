"""Builtin function and datatype tables used by the strict validation pass.

The signatures live in :mod:`sattline_parser.builtins`; this module adapts them
to the validator's arity/write-position view and keeps the datatype-name typo
helper. Unknown call names are left alone: only calls whose name appears in the
builtin registry are checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sattline_parser.builtins.functions import (
    BUILTIN_FUNCTIONS as _BUILTIN_FUNCTIONS,
)
from sattline_parser.builtins.functions import (
    BuiltinFunction as _BuiltinFunction,
)
from sattline_parser.builtins.functions import (
    BuiltinParameter,
    get_function_signature,
)
from sattline_parser.models.ast_model import Simple_DataType
from sattline_parser.validation.names import fold_identifier
from sattline_parser.validation.typing import suggest_datatype_name

#: Canonical (casefolded) names of all primitive datatypes. ``Variable`` normalises
#: recognised names to ``Simple_DataType`` at init; anything left as ``str`` after
#: parsing is a custom (record) type name, so only those strings are candidates for a
#: built-in-name typo.
BUILTIN_DATATYPE_NAMES: Final[frozenset[str]] = frozenset(member.value for member in Simple_DataType)


@dataclass(frozen=True, slots=True)
class BuiltinFunction:
    """Validator view of a documented builtin call.

    ``min_args`` / ``max_args`` bound the accepted argument count,
    ``out_arg_positions`` lists 1-based argument positions that must resolve to
    a writable variable reference, and ``parameters`` carries the documented
    direction and datatype for the argument-type rule.
    """

    name: str
    min_args: int
    max_args: int
    out_arg_positions: frozenset[int] = frozenset()
    parameters: tuple[BuiltinParameter, ...] = ()
    kind: str = "function"
    return_type: str | None = None


def _adapt(signature: _BuiltinFunction) -> BuiltinFunction:
    required_args = 0
    for parameter in signature.parameters:
        if parameter.optional:
            break
        required_args += 1
    return BuiltinFunction(
        name=signature.name,
        min_args=required_args,
        max_args=signature.arity,
        out_arg_positions=signature.out_arg_positions,
        parameters=signature.parameters,
        kind=signature.kind,
        return_type=signature.return_type,
    )


#: Lower-case canonical name -> signature.
BUILTIN_FUNCTIONS: Final[dict[str, BuiltinFunction]] = {
    name: _adapt(signature) for name, signature in _BUILTIN_FUNCTIONS.items()
}

#: Folded identity key -> signature. Function names are case-insensitive.
_FOLDED_FUNCTIONS: Final[dict[str, BuiltinFunction]] = {
    fold_identifier(name): signature for name, signature in BUILTIN_FUNCTIONS.items()
}
_FOLDED_DATATYPE_NAMES: Final[dict[str, str]] = {fold_identifier(name): name for name in BUILTIN_DATATYPE_NAMES}


def builtin_function_signature(name: str) -> BuiltinFunction | None:
    """Return the validator signature for ``name``, including documented aliases."""
    signature = get_function_signature(name)
    return None if signature is None else _adapt(signature)


def builtin_datatype_typo(datatype: str) -> str | None:
    """Return the built-in datatype name a custom datatype string seems to misspell.

    Only fires for names that are not exact matches (those are already normalised
    to ``Simple_DataType`` by ``Variable``) and that sit within the bounded edit
    distance of exactly one built-in; otherwise ``None``.
    """
    return suggest_datatype_name(datatype, sorted(_FOLDED_DATATYPE_NAMES.values()))


__all__ = [
    "BUILTIN_DATATYPE_NAMES",
    "BUILTIN_FUNCTIONS",
    "BuiltinFunction",
    "builtin_datatype_typo",
    "builtin_function_signature",
]
