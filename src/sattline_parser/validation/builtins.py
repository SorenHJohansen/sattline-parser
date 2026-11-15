"""Builtin function and datatype tables used by the strict validation pass.

The signatures live in :mod:`sattline_parser.builtins`; this module adapts them
to the validator's arity and parameter view and keeps the datatype-name typo
helper. The adaptation is cached, so a call site asks once per signature rather
than rebuilding the view on every checked call.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Final

from sattline_parser.builtins.functions import (
    BuiltinFunction as _BuiltinFunction,
)
from sattline_parser.builtins.functions import (
    BuiltinParameter,
    get_function_signature,
)
from sattline_parser.models.ast_model import Simple_DataType
from sattline_parser.names import fold_identifier
from sattline_parser.validation.typing import suggest_datatype_name

#: Canonical (casefolded) names of all primitive datatypes. ``Variable`` normalises
#: recognised names to ``Simple_DataType`` at init; anything left as ``str`` after
#: parsing is a custom (record) type name, so only those strings are candidates for a
#: built-in-name typo.
BUILTIN_DATATYPE_NAMES: Final[frozenset[str]] = frozenset(member.value for member in Simple_DataType)


@dataclass(frozen=True, slots=True)
class BuiltinFunction:
    """Validator view of a documented builtin call.

    ``min_args`` / ``max_args`` bound the accepted argument count and
    ``parameters`` carries the documented direction and datatype for the
    argument-type rule. Both bounds are ``None`` when the documented arity is
    unknown, so a call is not rejected for a count the catalogue never recorded.
    A typed entry's lower bound is its leading required count; an untyped entry
    that records an arity pins both bounds to it. A written position is derived
    from the parameter direction, so the view carries no second copy of that
    fact.
    """

    name: str
    min_args: int | None
    max_args: int | None
    parameters: tuple[BuiltinParameter, ...] = ()
    kind: str = "function"
    return_type: str | None = None


@cache
def _adapt(signature: _BuiltinFunction) -> BuiltinFunction:
    arity = signature.arity
    if arity is None:
        min_args: int | None = None
        max_args: int | None = None
    elif signature.typed:
        required_args = 0
        for parameter in signature.parameters:
            if parameter.optional:
                break
            required_args += 1
        min_args = required_args
        max_args = arity
    else:
        # An untyped entry records only the count, with no per-argument
        # directions, so every documented argument is required.
        min_args = arity
        max_args = arity
    return BuiltinFunction(
        name=signature.name,
        min_args=min_args,
        max_args=max_args,
        parameters=signature.parameters,
        kind=signature.kind,
        return_type=signature.return_type,
    )


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
    "BuiltinFunction",
    "builtin_datatype_typo",
    "builtin_function_signature",
]
