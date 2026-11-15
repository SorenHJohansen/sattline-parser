"""Round-trip tests for the whole-file formatter (``formatting/source.py``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sattline_parser.api import parse_source_file, parse_source_text
from sattline_parser.ast import VarTail
from sattline_parser.formatting import UnsupportedFormattingError, format_module, format_source

_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"


def _fixtures() -> list[Path]:
    return sorted([*_CORPUS.glob("valid/*.s"), *_CORPUS.glob("edge_cases/*.s")])


@pytest.mark.parametrize("path", _fixtures(), ids=lambda path: path.name)
def test_a_whole_file_round_trips_through_its_own_source(path: Path) -> None:
    picture = parse_source_file(path, log_failures=False)

    formatted = format_source(picture)
    reparsed = parse_source_text(formatted, log_failures=False)

    assert reparsed == picture
    # Formatting is idempotent: a second pass changes nothing.
    assert format_source(reparsed) == formatted


def test_graphics_and_interactor_properties_survive_the_round_trip() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "InteractWidgets.s", log_failures=False)

    reparsed = parse_source_text(format_source(picture), log_failures=False)

    assert reparsed.moduledef is not None
    original_objects = picture.moduledef.interact_objects if picture.moduledef else []
    reparsed_objects = reparsed.moduledef.interact_objects if reparsed.moduledef else []
    assert [obj.properties for obj in reparsed_objects] == [obj.properties for obj in original_objects]


def test_format_module_renders_one_block() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "ModuleDefWithCode.s", log_failures=False)
    assert picture.moduledef is not None

    text = format_module(picture.moduledef)

    assert text.startswith("ModuleDef\n")
    assert "ClippingBounds =" in text


def test_a_lost_tail_association_raises_instead_of_moving_the_tail() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "MinimalProgram.s", log_failures=False)
    picture.header.invoke_coord_tails = [VarTail("in", "PosX")]
    picture.header.coordinate_tails = ()

    with pytest.raises(UnsupportedFormattingError, match="coordinate tails"):
        format_source(picture)


def test_a_header_coordinate_tail_is_written_after_its_coordinate() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "UnCompressedFullGrammar.s", log_failures=False)

    formatted = format_source(picture)
    submodule = next(
        submodule for submodule in picture.submodules if any(getattr(submodule.header, "coordinate_tails", ()))
    )
    groups = submodule.header.coordinate_tails
    index = next(position for position, group in enumerate(groups) if group)
    value = str(float(submodule.header.invoke_coord[index]))
    tail = groups[index][0]
    assert isinstance(tail, VarTail)
    line = next(line for line in formatted.splitlines() if line.strip().startswith(submodule.header.name))

    assert f"{value} : {'InVar_' if tail.direction == 'in' else 'OutVar_'}" in line
