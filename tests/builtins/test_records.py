"""Tests for the builtin record field specifications."""

from __future__ import annotations

from sattline_parser.builtins import (
    BUILTIN_DECLARED_DATATYPE_NAMES,
    BUILTIN_RECORD_SPECS,
    FIELDLESS_BUILTIN_RECORD_NAMES,
    OPAQUE_BUILTIN_RECORD_NAMES,
)
from sattline_parser.models.ast_model import Simple_DataType


def test_record_specs_and_declared_names_are_complete() -> None:
    assert len(BUILTIN_RECORD_SPECS) == 81
    assert len(BUILTIN_DECLARED_DATATYPE_NAMES) == 91
    assert len(set(BUILTIN_DECLARED_DATATYPE_NAMES)) == len(BUILTIN_DECLARED_DATATYPE_NAMES)


def test_declared_names_start_with_the_scalar_datatypes() -> None:
    scalars = [datatype.value for datatype in Simple_DataType]
    assert list(BUILTIN_DECLARED_DATATYPE_NAMES[: len(scalars)]) == scalars
    assert set(scalars) <= set(BUILTIN_DECLARED_DATATYPE_NAMES)


def test_opaque_and_fieldless_records_are_registered_with_empty_specs() -> None:
    for name in (*OPAQUE_BUILTIN_RECORD_NAMES, *FIELDLESS_BUILTIN_RECORD_NAMES):
        assert BUILTIN_RECORD_SPECS[name] == ()
    assert "Timer" in OPAQUE_BUILTIN_RECORD_NAMES
    assert "ArrayObject" in FIELDLESS_BUILTIN_RECORD_NAMES


def test_record_specs_are_ordered_field_datatype_pairs() -> None:
    spec = BUILTIN_RECORD_SPECS["BooleanSignal"]
    assert spec == (
        ("Value", Simple_DataType.BOOLEAN),
        ("IoValue", Simple_DataType.BOOLEAN),
        ("Forced", Simple_DataType.BOOLEAN),
    )


def test_record_field_can_reference_another_record() -> None:
    assert ("GroupRef", "tObject") in BUILTIN_RECORD_SPECS["VarGroupType"]


def test_every_field_spec_is_a_named_datatype_pair() -> None:
    for spec in BUILTIN_RECORD_SPECS.values():
        for field_name, datatype in spec:
            assert isinstance(field_name, str) and field_name
            assert isinstance(datatype, Simple_DataType | str)
