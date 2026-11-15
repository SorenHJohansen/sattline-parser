"""Tests for the public AST serializer (``sattline_parser.serialization``)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sattline_parser import parse_source_text, to_json, to_jsonable
from sattline_parser.ast import BasePicture, SourceSpan


class _Colour(StrEnum):
    RED = "red"


@dataclass(frozen=True)
class _Leaf:
    name: str
    colour: _Colour
    span: SourceSpan


def test_serializer_emits_a_dataclass_field_by_field() -> None:
    leaf = _Leaf(name="X", colour=_Colour.RED, span=SourceSpan(1, 2, 3, 4))

    assert to_jsonable(leaf) == {
        "name": "X",
        "colour": "red",
        "span": {"start": 1, "end": 2, "line": 3, "column": 4},
    }


def test_serializer_is_unlimited_by_default_and_bounded_on_request() -> None:
    leaf = _Leaf(name="X", colour=_Colour.RED, span=SourceSpan(1, 2, 3, 4))

    unlimited = to_jsonable(leaf)
    assert isinstance(unlimited, dict)
    assert unlimited["name"] == "X"
    assert to_jsonable(leaf, depth=1) == {
        "name": "X",
        "colour": "red",
        "span": "<SourceSpan>",
    }


def test_serializer_handles_paths_and_mappings() -> None:
    assert to_jsonable(Path("/a/b")) == str(Path("/a/b"))
    assert to_jsonable({"key": Path("/a/b")}) == {"key": str(Path("/a/b"))}


_SOURCE = """"SyntaxVersion"
"OriginalFileDate"
"ProgramDate"
BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1
LOCALVARIABLES
    X: integer := 0;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
        X = 1;
ENDDEF (*BasePicture*);
"""


def test_serializer_covers_a_whole_picture() -> None:
    picture = parse_source_text(_SOURCE)

    payload = to_jsonable(picture)

    assert isinstance(picture, BasePicture)
    assert isinstance(payload, dict)
    assert payload["name"] == "BasePicture"
    assert isinstance(payload["header_info"], dict)
    # The serializer is a data view, so the payload must survive a JSON round trip.
    assert json.loads(json.dumps(payload)) == payload


def test_to_json_is_valid_json_text() -> None:
    picture = parse_source_text(_SOURCE)

    text = to_json(picture, compact=True)

    assert "\n" not in text
    assert json.loads(text)["name"] == "BasePicture"


def test_serializer_placeholder_names_the_elided_value() -> None:
    @dataclass(frozen=True)
    class Holder:
        items: tuple[int, ...]
        mapping: dict[str, int]

    payload = to_jsonable(Holder(items=(1, 2, 3), mapping={"a": 1}), depth=1)

    assert payload == {"items": "<3 items>", "mapping": "<1 keys>"}


def test_serializer_handles_bytes_and_sets_stably() -> None:
    assert to_jsonable(b"\x00\xff") == "00ff"
    assert to_jsonable({3, 1, 2}) == [1, 2, 3]
    assert to_jsonable({"b", "a"}) == ["a", "b"]


def test_serializer_placeholder_counts_a_set() -> None:
    assert to_jsonable({1, 2, 3}, depth=0) == "<3 items>"


def test_to_json_pretty_is_indented() -> None:
    text = to_json({"name": "X"})

    assert "\n" in text
    assert json.loads(text) == {"name": "X"}


def test_serializer_falls_back_to_repr_for_an_unknown_value() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "opaque"

    assert to_jsonable(Opaque()) == "opaque"
