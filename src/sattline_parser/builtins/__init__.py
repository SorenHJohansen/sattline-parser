"""Language facts about SattLine builtins.

This package owns the documented builtin function signatures and the builtin
record field specifications. It carries no validation policy: consumers decide
what to do with a signature or a field list.
"""

from __future__ import annotations

from .functions import (
    BUILTIN_ALIASES,
    BUILTIN_FUNCTIONS,
    CATALOGUE_META,
    BuiltinFunction,
    BuiltinParameter,
    get_function_signature,
    is_builtin_function,
)
from .records import (
    BUILTIN_DECLARED_DATATYPE_NAMES,
    BUILTIN_RECORD_SPECS,
    FIELDLESS_BUILTIN_RECORD_NAMES,
    OPAQUE_BUILTIN_RECORD_NAMES,
    BuiltinFieldSpec,
)

__all__ = [
    "BUILTIN_ALIASES",
    "BUILTIN_DECLARED_DATATYPE_NAMES",
    "BUILTIN_FUNCTIONS",
    "BUILTIN_RECORD_SPECS",
    "CATALOGUE_META",
    "FIELDLESS_BUILTIN_RECORD_NAMES",
    "OPAQUE_BUILTIN_RECORD_NAMES",
    "BuiltinFieldSpec",
    "BuiltinFunction",
    "BuiltinParameter",
    "get_function_signature",
    "is_builtin_function",
]
