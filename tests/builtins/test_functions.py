"""Tests for the builtin function registry."""

from __future__ import annotations

from sattline_parser.builtins import (
    BUILTIN_ALIASES,
    BUILTIN_FUNCTIONS,
    CATALOGUE_META,
    BuiltinFunction,
    get_function_signature,
    is_builtin_function,
)


def test_catalogue_carries_every_entry_and_alias() -> None:
    assert len(BUILTIN_FUNCTIONS) == 180
    assert BUILTIN_ALIASES == {"EqualString": "equalstrings"}


def test_meta_states_coverage_and_provenance() -> None:
    assert CATALOGUE_META["documented_total"] == 171
    assert CATALOGUE_META["carried_total"] == 180
    assert CATALOGUE_META["typed_entries"] == 178
    assert CATALOGUE_META["untyped_entries"] == 2
    assert CATALOGUE_META["omissions"] == []
    primary = CATALOGUE_META["primary_source"]
    assert isinstance(primary, dict)
    assert primary["title"] == "SattLine Language User manual"
    assert primary["edition"] == "System Version 3.1"
    not_located = CATALOGUE_META["not_located"]
    assert isinstance(not_located, dict)
    assert not_located["count"] == 9


def test_lookup_is_case_insensitive() -> None:
    signature = get_function_signature("CoPyTiMe")
    assert signature is not None
    assert signature.name == "copytime"


def test_alias_resolves_to_the_canonical_signature() -> None:
    alias = get_function_signature("EqualString")
    canonical = get_function_signature("equalstrings")
    assert alias is canonical
    assert alias is not None
    assert alias.arity == 3


def test_unknown_name_returns_none() -> None:
    assert get_function_signature("NotABuiltin") is None
    assert is_builtin_function("NotABuiltin") is False


def test_is_builtin_function_accepts_canonical_names_and_aliases() -> None:
    assert is_builtin_function("StringLength") is True
    assert is_builtin_function("EqualString") is True


def test_signature_exposes_arity_and_written_positions() -> None:
    signature = get_function_signature("CopyVariable")
    assert isinstance(signature, BuiltinFunction)
    assert signature.kind == "procedure"
    assert signature.arity == 3
    assert signature.out_arg_positions == frozenset({2, 3})
    assert [parameter.name for parameter in signature.parameters] == ["Source", "Destination", "Status"]


def test_function_with_no_written_positions() -> None:
    signature = get_function_signature("Equal")
    assert signature is not None
    assert signature.out_arg_positions == frozenset()


def test_untyped_entries_keep_their_arity() -> None:
    get_flag = get_function_signature("GetPrivilegeFlag")
    reset_flag = get_function_signature("ResetPrivilegeFlag")
    assert get_flag is not None and get_flag.typed is False
    assert get_flag.arity == 0
    assert reset_flag is not None and reset_flag.kind == "procedure"
    assert reset_flag.arity == 0


def test_trailing_optional_parameters_are_marked() -> None:
    signature = get_function_signature("writeline")
    assert signature is not None
    assert [(parameter.name, parameter.optional) for parameter in signature.parameters] == [
        ("FileRef", False),
        ("String", False),
        ("AsyncOperation", True),
        ("DebugStatus", True),
    ]


def test_precision_scangroup_flag_is_preserved() -> None:
    signature = get_function_signature("abs")
    assert signature is not None
    assert signature.precision_scangroup is True
    plain = get_function_signature("StringLength")
    assert plain is not None
    assert plain.precision_scangroup is False
