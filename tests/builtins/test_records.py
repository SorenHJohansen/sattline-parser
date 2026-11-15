"""Tests for the builtin record field specifications."""

from __future__ import annotations

from sattline_parser.builtins import (
    BUILTIN_DECLARED_DATATYPE_NAMES,
    BUILTIN_RECORD_SPECS,
    FIELDLESS_BUILTIN_RECORD_NAMES,
    OPAQUE_BUILTIN_RECORD_NAMES,
)
from sattline_parser.models.ast_model import ScalarDatatype


def test_record_specs_and_declared_names_are_complete() -> None:
    assert len(BUILTIN_RECORD_SPECS) == 111
    assert len(BUILTIN_DECLARED_DATATYPE_NAMES) == 121
    assert len(set(BUILTIN_DECLARED_DATATYPE_NAMES)) == len(BUILTIN_DECLARED_DATATYPE_NAMES)


def test_declared_names_start_with_the_scalar_datatypes() -> None:
    scalars = [datatype.value for datatype in ScalarDatatype]
    assert list(BUILTIN_DECLARED_DATATYPE_NAMES[: len(scalars)]) == scalars
    assert set(scalars) <= set(BUILTIN_DECLARED_DATATYPE_NAMES)


def test_only_the_native_handles_and_untranscribed_records_carry_an_empty_spec() -> None:
    empty = {name for name, spec in BUILTIN_RECORD_SPECS.items() if not spec}
    # The native handles have no fields at all; the three system records are
    # declared but their field tables are not part of the transcribed reference
    # set, so their shape stays unknown.
    assert empty == {"tObject", "ArrayObject", "QueueObject", "ByteRecord", "ComliMessage", "PidType"}
    assert set(OPAQUE_BUILTIN_RECORD_NAMES) | set(FIELDLESS_BUILTIN_RECORD_NAMES) <= empty
    assert "ArrayObject" in FIELDLESS_BUILTIN_RECORD_NAMES


def test_signature_only_records_are_declared_datatypes() -> None:
    """The types builtin signatures name must resolve as declared datatypes."""
    for name in ("ByteRecord", "ComliMessage", "PidType"):
        assert name in BUILTIN_RECORD_SPECS
        assert name in BUILTIN_DECLARED_DATATYPE_NAMES
        assert name not in OPAQUE_BUILTIN_RECORD_NAMES


def test_record_types_with_a_declared_shape_are_not_treated_as_opaque() -> None:
    # These names used to be registered with an empty spec because no field
    # table was available; they now carry their declared fields.
    for name in ("Timer", "AcofTimerType", "RandomGenerator", "EventSortRecType", "SortedEventType"):
        assert name not in OPAQUE_BUILTIN_RECORD_NAMES
        assert name not in FIELDLESS_BUILTIN_RECORD_NAMES
        assert BUILTIN_RECORD_SPECS[name]


def test_timer_records_share_the_running_and_counter_shape() -> None:
    assert BUILTIN_RECORD_SPECS["Timer"] == (
        ("Running", ScalarDatatype.BOOLEAN),
        ("Holding", ScalarDatatype.BOOLEAN),
        ("High", ScalarDatatype.INTEGER),
        ("Low", ScalarDatatype.INTEGER),
    )
    assert BUILTIN_RECORD_SPECS["AcofTimerType"] == (
        ("Running", ScalarDatatype.BOOLEAN),
        ("Hold", ScalarDatatype.BOOLEAN),
        ("High", ScalarDatatype.INTEGER),
        ("Low", ScalarDatatype.INTEGER),
    )


def test_sorted_event_record_nests_the_sort_record() -> None:
    assert BUILTIN_RECORD_SPECS["SortedEventType"] == (
        ("EventCondName", ScalarDatatype.TAGSTRING),
        ("EventState", ScalarDatatype.INTEGER),
        ("SortRecord", "EventSortRecType"),
        ("FormattedInfo", ScalarDatatype.MAXSTRING),
    )
    assert len(BUILTIN_RECORD_SPECS["EventSortRecType"]) == 5


def test_time_record_uses_the_millisecond_field_spelling_sources_write() -> None:
    names = [field_name for field_name, _ in BUILTIN_RECORD_SPECS["TimeRecord"]]
    assert names[-1] == "MilliSec"


def test_scan_group_data_carries_the_group_object_handle() -> None:
    assert BUILTIN_RECORD_SPECS["GroupData"] == (
        ("Executing", ScalarDatatype.BOOLEAN),
        ("GroupObject", "tObject"),
        ("WarmStarting", ScalarDatatype.BOOLEAN),
    )


def test_record_specs_are_ordered_field_datatype_pairs() -> None:
    spec = BUILTIN_RECORD_SPECS["BooleanSignal"]
    assert spec == (
        ("Value", ScalarDatatype.BOOLEAN),
        ("IoValue", ScalarDatatype.BOOLEAN),
        ("Forced", ScalarDatatype.BOOLEAN),
    )


def test_record_field_can_reference_another_record() -> None:
    assert ("GroupRef", "tObject") in BUILTIN_RECORD_SPECS["VarGroupType"]


def test_every_field_spec_is_a_named_datatype_pair() -> None:
    for spec in BUILTIN_RECORD_SPECS.values():
        for field_name, datatype in spec:
            assert isinstance(field_name, str) and field_name
            assert isinstance(datatype, ScalarDatatype | str)
