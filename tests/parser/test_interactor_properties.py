"""Tests for the interactor property catalogue (``models/interactor_properties.py``)."""

from __future__ import annotations

import json
from pathlib import Path

from sattline_parser import parse_source_text
from sattline_parser.ast import (
    InteractObject,
    InteractorPropertyKind,
    ScalarDatatype,
    find_interactor_property,
    interactor_property_catalogue,
    typed_interactor_properties,
)

_SOURCE = """\
"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: InteractCatalogue"

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
InteractObjects :
   TextBox_ ( -0.8 , 0.9 ) ( 0.8 , 0.7 )
      Int_Value
      Digits_ = 2
      Visible_
      Custom_Flag

   ComButProc_ ( -0.8 , 0.3 ) ( 0.8 , 0.1 )
      ToggleWindow
      Event_Text_ = "ready"
      Variable = 0.0

ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      X = 1;

ENDDEF (*BasePicture*);
"""


def _interactors() -> list[InteractObject]:
    picture = parse_source_text(_SOURCE)
    objects: list[InteractObject] = []
    assert picture.moduledef is not None
    objects.extend(picture.moduledef.interact_objects)
    return objects


def test_catalogue_classifies_a_known_spelling_case_insensitively() -> None:
    spec = find_interactor_property("int_value")

    assert spec is not None
    assert spec.name == "Int_Value"
    assert spec.kind is InteractorPropertyKind.NUMERIC
    assert spec.datatype is ScalarDatatype.INTEGER


def test_catalogue_returns_none_for_an_unknown_spelling() -> None:
    assert find_interactor_property("Custom_Flag") is None


def test_typed_properties_read_the_body_shape_in_written_order() -> None:
    text_box = _interactors()[0]

    typed = typed_interactor_properties(text_box)

    assert [item.name for item in typed] == ["Int_Value", "Digits_", "Visible_", "Custom_Flag"]
    assert [item.spec.name if item.spec is not None else None for item in typed] == [
        "Int_Value",
        "Digits_",
        "Visible_",
        None,
    ]
    assert typed[1].value == 2
    assert typed[2].value is None


def test_typed_properties_read_the_flat_shape() -> None:
    button = _interactors()[1]

    typed = typed_interactor_properties(button)

    assert [item.name for item in typed] == ["Event_Text_", "Variable"]
    assert typed[0].spec is not None and typed[0].spec.kind is InteractorPropertyKind.EVENT
    assert typed[1].spec is not None and typed[1].spec.kind is InteractorPropertyKind.SELECT


def test_typed_properties_yield_a_clause_once_when_both_shapes_hold_it() -> None:
    text_box = _interactors()[0]
    body = text_box.properties.get("body")
    assert body is not None
    shared = body[0]
    text_box.properties["flags"] = [shared]  # pyright: ignore[reportGeneralTypeIssues]

    typed = typed_interactor_properties(text_box)

    assert [item.name for item in typed].count("Int_Value") == 1


def test_every_catalogue_spelling_exists_in_the_scanner_table() -> None:
    table = Path(__file__).parents[2] / "src" / "sattline_parser" / "preprocessing" / "scanner_tokens.json"
    spellings = {row["text"] for row in json.loads(table.read_text(encoding="utf-8"))}

    missing = sorted(spec.name for spec in interactor_property_catalogue.values() if spec.name not in spellings)

    assert missing == []
