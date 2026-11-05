"""Tests for the public ``sattline_parser.types`` namespace."""

from __future__ import annotations

import sattline_parser.types as sl_types
from sattline_parser.validation import typing

#: Names a consumer imports instead of reaching into ``validation.typing``.
_REQUIRED_CONSUMER_NAMES = (
    "infer_literal_datatype",
    "is_string_simple_type",
    "resolve_variable_field_datatype",
    "split_dotted_name",
)

_EXPECTED_ALL = {
    "FieldGraph",
    "FieldSpec",
    "Simple_DataType",
    "TypeFamily",
    "assignment_type_matches",
    "builtin_type_matches",
    "datatype_family",
    "expression_is_zero_literal",
    "extract_time_literal",
    "family_of",
    "format_datatype",
    "has_time_literal_marker",
    "infer_literal_datatype",
    "is_anytype_datatype",
    "is_boolean",
    "is_boolean_datatype",
    "is_numeric",
    "is_numeric_datatype",
    "is_string_simple_type",
    "is_valid_duration_literal",
    "is_valid_time_literal",
    "literal_matches_expected_datatype",
    "merge_compatible_types",
    "merge_numeric_types",
    "normalize_builtin_datatype",
    "resolve_variable_field_datatype",
    "split_dotted_name",
    "suggest_datatype_name",
}


def test_required_type_facts_are_public() -> None:
    for name in _REQUIRED_CONSUMER_NAMES:
        assert name in sl_types.__all__, name


def test_export_set_matches_the_documented_surface() -> None:
    assert set(sl_types.__all__) == _EXPECTED_ALL


def test_every_export_resolves_to_the_implementation() -> None:
    for name in sl_types.__all__:
        assert getattr(sl_types, name) is getattr(typing, name), name


def test_all_names_are_unique_and_sorted() -> None:
    assert sl_types.__all__ == sorted(sl_types.__all__)
    assert len(sl_types.__all__) == len(set(sl_types.__all__))
