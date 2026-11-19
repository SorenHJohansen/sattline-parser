"""The exported builtin registries are read-only and validation reads the same view.

A mutable export let a caller change the public lookup while validation kept the
copy it built at import, so the two answers disagreed. The registries are now
``FrozenMapping`` values: mutation raises, and every consumer reads one snapshot.
"""

from __future__ import annotations

import pickle
from typing import Any, cast

import pytest

from sattline_parser.api import parse_and_validate
from sattline_parser.builtins import (
    BUILTIN_ALIASES,
    BUILTIN_FUNCTIONS,
    BUILTIN_RECORD_SPECS,
    CATALOGUE_META,
    get_function_signature,
    is_builtin_function,
)
from sattline_parser.models.freeze import FrozenMapping

_REGISTRIES = (
    ("BUILTIN_FUNCTIONS", BUILTIN_FUNCTIONS),
    ("BUILTIN_ALIASES", BUILTIN_ALIASES),
    ("CATALOGUE_META", CATALOGUE_META),
    ("BUILTIN_RECORD_SPECS", BUILTIN_RECORD_SPECS),
)


@pytest.mark.parametrize(("name", "registry"), _REGISTRIES, ids=[entry[0] for entry in _REGISTRIES])
def test_a_registry_is_a_frozen_mapping(name: str, registry: object) -> None:
    assert isinstance(registry, FrozenMapping), f"{name} is mutable, so a caller can desynchronise it"

    writable = cast("Any", registry)
    key = next(iter(writable))
    with pytest.raises(TypeError):
        writable[key] = writable[key]
    with pytest.raises(TypeError):
        del writable[key]


def test_a_registry_pickles_into_an_equal_read_only_mapping() -> None:
    clone = pickle.loads(pickle.dumps(BUILTIN_FUNCTIONS))

    assert isinstance(clone, FrozenMapping)
    assert clone == BUILTIN_FUNCTIONS


def test_the_public_lookup_and_validation_agree_after_a_refused_mutation() -> None:
    """A refused write leaves both answers on the one snapshot validation reads."""
    signature = get_function_signature("equalstrings")
    assert signature is not None
    assert get_function_signature("EqualString") is signature
    assert is_builtin_function("EqualString")
    assert BUILTIN_ALIASES["EqualString"] == "equalstrings"

    with pytest.raises(TypeError):
        cast("Any", BUILTIN_FUNCTIONS)["EqualString"] = "not a signature"

    assert get_function_signature("EqualString") is signature
    source = (
        '"Syntax version 2.23"\n'
        '"Original file date: ---"\n'
        '"Program date: ---, name: Arity"\n'
        "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        '   Left: string := "";\n'
        '   Right: string := "";\n'
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "   EQUATIONBLOCK E COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "      Left = EqualString(Left);\n"
        "ENDDEF (*BasePicture*);\n"
    )
    diagnostics = [d for d in parse_and_validate(source, log_failures=False)[1] if d.code.value == "SL-V013"]

    # The validator still knows the documented arity, so the wrong call is reported.
    assert diagnostics
