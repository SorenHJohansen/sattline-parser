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
    assert len(BUILTIN_RECORD_SPECS) == 108
    assert len(BUILTIN_DECLARED_DATATYPE_NAMES) == 118
    assert len(set(BUILTIN_DECLARED_DATATYPE_NAMES)) == len(BUILTIN_DECLARED_DATATYPE_NAMES)


def test_declared_names_start_with_the_scalar_datatypes() -> None:
    scalars = [datatype.value for datatype in Simple_DataType]
    assert list(BUILTIN_DECLARED_DATATYPE_NAMES[: len(scalars)]) == scalars
    assert set(scalars) <= set(BUILTIN_DECLARED_DATATYPE_NAMES)


def test_only_the_native_object_handles_carry_an_empty_spec() -> None:
    empty = {name for name, spec in BUILTIN_RECORD_SPECS.items() if not spec}
    assert empty == {"tObject", "ArrayObject", "QueueObject"}
    assert empty == set(OPAQUE_BUILTIN_RECORD_NAMES) | set(FIELDLESS_BUILTIN_RECORD_NAMES)
    assert "ArrayObject" in FIELDLESS_BUILTIN_RECORD_NAMES


def test_record_types_with_a_declared_shape_are_not_treated_as_opaque() -> None:
    # These names used to be registered with an empty spec because no field
    # table was available; they now carry their declared fields.
    for name in ("Timer", "AcofTimerType", "RandomGenerator", "EventSortRecType", "SortedEventType"):
        assert name not in OPAQUE_BUILTIN_RECORD_NAMES
        assert name not in FIELDLESS_BUILTIN_RECORD_NAMES
        assert BUILTIN_RECORD_SPECS[name]


def test_timer_records_share_the_running_and_counter_shape() -> None:
    assert BUILTIN_RECORD_SPECS["Timer"] == (
        ("Running", Simple_DataType.BOOLEAN),
        ("Holding", Simple_DataType.BOOLEAN),
        ("High", Simple_DataType.INTEGER),
        ("Low", Simple_DataType.INTEGER),
    )
    assert BUILTIN_RECORD_SPECS["AcofTimerType"] == (
        ("Running", Simple_DataType.BOOLEAN),
        ("Hold", Simple_DataType.BOOLEAN),
        ("High", Simple_DataType.INTEGER),
        ("Low", Simple_DataType.INTEGER),
    )


def test_sorted_event_record_nests_the_sort_record() -> None:
    assert BUILTIN_RECORD_SPECS["SortedEventType"] == (
        ("EventCondName", Simple_DataType.TAGSTRING),
        ("EventState", Simple_DataType.INTEGER),
        ("SortRecord", "EventSortRecType"),
        ("FormattedInfo", Simple_DataType.MAXSTRING),
    )
    assert len(BUILTIN_RECORD_SPECS["EventSortRecType"]) == 5


def test_time_record_uses_the_millisecond_field_spelling_sources_write() -> None:
    names = [field_name for field_name, _ in BUILTIN_RECORD_SPECS["TimeRecord"]]
    assert names[-1] == "MilliSec"


def test_scan_group_data_carries_the_group_object_handle() -> None:
    assert BUILTIN_RECORD_SPECS["GroupData"] == (
        ("Executing", Simple_DataType.BOOLEAN),
        ("GroupObject", "tObject"),
        ("WarmStarting", Simple_DataType.BOOLEAN),
    )


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
