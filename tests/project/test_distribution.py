# pyright: reportPrivateUsage=false
"""Distribution companion parsing (``project/distribution.py``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sattline_parser.project import (
    DistributionParseError,
    LoadMode,
    parse_distribution_file,
    parse_distribution_text,
    resolve_distribution_companion_path,
)

_EMPTY = """\
DistributionData
 ( Version "Distributiondata version 1.0" )
SourceCodeSystems
 (  )
ExecutingSystems
 (  )
"""

_ONE_CONTROLLER = """\
DistributionData
 ( Version "Distributiondata version 1.0" )
SourceCodeSystems
 (  )
ExecutingSystems
 ( Controller
    ( Name "172.18.0.1"
      Download ShortStopReconfig ) )
"""

_OP_STATION = """\
DistributionData
 ( Version "Distributiondata version 1.0" )
SourceCodeSystems
 (  )
ExecutingSystems
 ( OpStation
    ( Name "172.18.0.2"
      Download ShortStopReconfig ) )
"""

_TWO_TARGETS = """\
DistributionData
 ( Version "Distributiondata version 1.0" )
SourceCodeSystems
 (  )
ExecutingSystems
 ( Controller
    ( Name "172.18.0.1"
      Download ShortStopReconfig )
   Controller
    ( Name "172.18.0.3"
      Download LowMemReconfig ) )
"""

_SOURCE_ONLY = """\
DistributionData
 ( Version "Distributiondata version 1.0" )
SourceCodeSystems
 ( Controller
    ( Name "172.18.0.9"
      Download ShortStopReconfig ) )
ExecutingSystems
 (  )
"""


def test_empty_executing_systems_is_false() -> None:
    distribution = parse_distribution_text(_EMPTY)
    assert distribution.version == "Distributiondata version 1.0"
    assert distribution.source_code_systems == ()
    assert distribution.executing_systems == ()
    assert distribution.has_executing_system is False


def test_one_controller_target() -> None:
    distribution = parse_distribution_text(_ONE_CONTROLLER)
    assert distribution.has_executing_system is True
    target = distribution.executing_systems[0]
    assert (target.kind, target.name, target.download) == ("Controller", "172.18.0.1", "ShortStopReconfig")
    assert target.attributes == (("Download", "ShortStopReconfig"),)


def test_operator_station_target() -> None:
    distribution = parse_distribution_text(_OP_STATION)
    target = distribution.executing_systems[0]
    assert target.kind == "OpStation"
    assert target.name == "172.18.0.2"


def test_target_without_download_has_no_download_value() -> None:
    text = 'DistributionData ( Version "v" ) SourceCodeSystems ( ) ExecutingSystems ( Controller ( Name "a" ) )'
    target = parse_distribution_text(text).executing_systems[0]
    assert target.attributes == ()
    assert target.download is None


def test_multiple_targets_keep_file_order() -> None:
    distribution = parse_distribution_text(_TWO_TARGETS)
    assert [target.name for target in distribution.executing_systems] == ["172.18.0.1", "172.18.0.3"]
    assert [target.download for target in distribution.executing_systems] == ["ShortStopReconfig", "LowMemReconfig"]


def test_source_code_systems_do_not_count_as_executing() -> None:
    distribution = parse_distribution_text(_SOURCE_ONLY)
    assert [target.name for target in distribution.source_code_systems] == ["172.18.0.9"]
    assert distribution.executing_systems == ()
    assert distribution.has_executing_system is False


def test_section_and_key_case_is_folded() -> None:
    text = _ONE_CONTROLLER.replace("ExecutingSystems", "EXECUTINGSYSTEMS").replace("Download", "DOWNLOAD")
    distribution = parse_distribution_text(text)
    assert distribution.has_executing_system is True
    assert distribution.executing_systems[0].download == "ShortStopReconfig"


def test_doubled_quote_is_an_escaped_quote() -> None:
    text = _ONE_CONTROLLER.replace('"172.18.0.1"', '"172.18""0.1"')
    distribution = parse_distribution_text(text)
    assert distribution.executing_systems[0].name == '172.18"0.1'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "missing 'DistributionData' section"),
        ('DistributionData ( Version "v" )', "missing 'SourceCodeSystems' section"),
        (
            'DistributionData ( Version "v" ) SourceCodeSystems ( ) ExecutingSystems ( ) ArchiveSystems ( )',
            "unknown distribution section 'ArchiveSystems'",
        ),
        (
            'DistributionData ( Version "v" ) DistributionData ( Version "v" ) '
            "SourceCodeSystems ( ) ExecutingSystems ( )",
            "duplicate 'DistributionData' section",
        ),
        ("DistributionData ( ) SourceCodeSystems ( ) ExecutingSystems ( )", "exactly one Version"),
        (
            'DistributionData ( Version "v" Other "x" ) SourceCodeSystems ( ) ExecutingSystems ( )',
            "unknown DistributionData key 'Other'",
        ),
        (
            'DistributionData ( Version "v" ) SourceCodeSystems ( ) '
            "ExecutingSystems ( Controller ( Download ShortStopReconfig ) )",
            "has no Name",
        ),
        (
            'DistributionData ( Version "v" ) SourceCodeSystems ( ) '
            'ExecutingSystems ( Controller ( Name "a" Download ShortStopReconfig Download LowMemReconfig ) )',
            "repeats key 'Download'",
        ),
        (
            'DistributionData ( Version ( "v" ) ) SourceCodeSystems ( ) ExecutingSystems ( )',
            "expected a key",
        ),
        (
            'DistributionData ( "v" ) SourceCodeSystems ( ) ExecutingSystems ( )',
            "expected a key",
        ),
        (
            'DistributionData ( Version Foo ( "bar" ) ) SourceCodeSystems ( ) ExecutingSystems ( )',
            "must have one scalar value",
        ),
        (
            'DistributionData ( Version "v" Dangling ) SourceCodeSystems ( ) ExecutingSystems ( )',
            "has no value",
        ),
        (
            'DistributionData ( Version "v" ) SourceCodeSystems ( ) '
            'ExecutingSystems ( Controller ( Name "a" Download ) )',
            "has no value",
        ),
        (
            'DistributionData ( Version "v" ) SourceCodeSystems ( ) ExecutingSystems ( Controller )',
            "expected a system group",
        ),
        (
            'DistributionData ( Version "" ) SourceCodeSystems ( ) ExecutingSystems ( ) )',
            "unmatched ')'",
        ),
        (
            'DistributionData ( Version "v" ) SourceCodeSystems ( ) "junk"',
            "expected a group name",
        ),
        (
            'DistributionData ( Version "v" ) SourceCodeSystems ( ) ExecutingSystems',
            "expected '(' after",
        ),
        (
            'DistributionData ( Version "v" ) SourceCodeSystems ( ) ExecutingSystems (',
            "missing ')' for an open group",
        ),
        (
            'DistributionData ( Version "v" Version "w" ) SourceCodeSystems ( ) ExecutingSystems ( )',
            "exactly one Version",
        ),
        ('DistributionData ( Version "v )', "unterminated string"),
    ],
)
def test_malformed_companions_raise(text: str, message: str) -> None:
    with pytest.raises(DistributionParseError) as caught:
        parse_distribution_text(text)
    assert message.lower() in str(caught.value).lower()


def test_error_carries_a_position() -> None:
    with pytest.raises(DistributionParseError) as caught:
        parse_distribution_text('DistributionData\n ( Version "v" )\nSourceCodeSystems\n ( )\n')
    assert caught.value.line >= 1
    assert caught.value.column >= 1


def test_parse_distribution_file_missing_path_raises_oserror(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        parse_distribution_file(tmp_path / "Absent.q")


def test_deep_nesting_is_a_structured_error() -> None:
    text = "A ( " * 200 + ")" * 200
    with pytest.raises(DistributionParseError) as caught:
        parse_distribution_text(text)
    assert "nesting is deeper" in str(caught.value)


def test_parse_distribution_file_reads_cp1252(tmp_path: Path) -> None:
    path = tmp_path / "Main.q"
    path.write_bytes(_ONE_CONTROLLER.replace("172.18.0.1", "172.18.0.\u00e6").encode("cp1252"))
    distribution = parse_distribution_file(path)
    assert distribution.executing_systems[0].name == "172.18.0.\u00e6"


def test_resolve_companion_for_official_code(tmp_path: Path) -> None:
    code = tmp_path / "Main.x"
    code.write_text("", encoding="utf-8")
    (tmp_path / "Main.q").write_text(_EMPTY, encoding="utf-8")
    assert resolve_distribution_companion_path(code, mode=LoadMode.OFFICIAL) == tmp_path / "Main.q"


def test_resolve_companion_for_draft_code_prefers_p(tmp_path: Path) -> None:
    code = tmp_path / "Main.s"
    code.write_text("", encoding="utf-8")
    (tmp_path / "Main.p").write_text(_EMPTY, encoding="utf-8")
    (tmp_path / "Main.q").write_text(_EMPTY, encoding="utf-8")
    assert resolve_distribution_companion_path(code, mode=LoadMode.DRAFT) == tmp_path / "Main.p"


def test_resolve_companion_for_draft_code_ignores_official_q(tmp_path: Path) -> None:
    code = tmp_path / "Main.s"
    code.write_text("", encoding="utf-8")
    (tmp_path / "Main.q").write_text(_EMPTY, encoding="utf-8")
    assert resolve_distribution_companion_path(code, mode=LoadMode.DRAFT) is None


def test_resolve_companion_absent(tmp_path: Path) -> None:
    code = tmp_path / "Main.x"
    code.write_text("", encoding="utf-8")
    assert resolve_distribution_companion_path(code, mode=LoadMode.OFFICIAL) is None


def test_resolve_companion_for_a_companion_input_is_itself(tmp_path: Path) -> None:
    path = tmp_path / "Main.q"
    path.write_text(_EMPTY, encoding="utf-8")
    assert resolve_distribution_companion_path(path, mode=LoadMode.DRAFT) == path
