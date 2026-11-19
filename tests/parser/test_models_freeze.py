"""The project freeze boundary keeps a tree renderable, picklable, and copyable."""

from __future__ import annotations

import copy
import dataclasses
import pickle
from typing import cast

import pytest

from sattline_parser.api import parse_source_text
from sattline_parser.ast import BasePicture
from sattline_parser.formatting import format_source
from sattline_parser.models.freeze import FrozenMapping, freeze_ast

_SOURCE = """"Syntax version 2.23"
"Original file date: ---"
"Program date: ---, name: Frozen"
Frozen Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION
ModuleParameters
   Wait: Time_Value := Time_Value "1h";
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 )
ENDDEF (*Frozen*);
"""


def _frozen_picture() -> BasePicture:
    return cast(BasePicture, freeze_ast(parse_source_text(_SOURCE, log_failures=False)))


def test_a_frozen_time_value_still_renders_as_source() -> None:
    """A frozen ``Time_Value`` payload is a mapping, not a dict subclass."""
    frozen = _frozen_picture()

    text = format_source(frozen)

    assert 'Wait: Time_Value := Time_Value "1h";' in text
    assert "{" not in text
    reparsed = parse_source_text(text, log_failures=False)
    assert reparsed == parse_source_text(_SOURCE, log_failures=False)


def test_a_frozen_tree_pickles_and_stays_immutable() -> None:
    frozen = _frozen_picture()

    restored = pickle.loads(pickle.dumps(frozen))

    assert restored == frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        restored.moduleparameters[0].name = "Renamed"
    with pytest.raises(AttributeError):
        restored.moduleparameters.append(restored.moduleparameters[0])


def test_a_frozen_tree_deep_copies_and_stays_immutable() -> None:
    frozen = _frozen_picture()

    copied = copy.deepcopy(frozen)

    assert copied == frozen
    assert copied is not frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        copied.moduleparameters[0].name = "Renamed"
    with pytest.raises(AttributeError):
        copied.moduleparameters.append(copied.moduleparameters[0])
    assert copied.moduledef is not None
    with pytest.raises(AttributeError):
        copied.moduledef.graph_objects.append(copied.moduledef.graph_objects[0])


def test_a_frozen_mapping_is_read_only() -> None:
    frozen = cast("FrozenMapping", freeze_ast({"items": [1, 2]}))

    assert isinstance(frozen, FrozenMapping)
    assert frozen["items"] == (1, 2)
    assert list(frozen) == ["items"]
    assert len(frozen) == 1
    assert repr(frozen) == "FrozenMapping({'items': (1, 2)})"
    with pytest.raises(TypeError):
        cast("dict[str, object]", frozen)["other"] = 3


def test_a_frozen_mapping_copies_without_breaking_the_read_only_view() -> None:
    frozen = FrozenMapping({"a": 1})

    assert copy.copy(frozen) is frozen
    assert copy.deepcopy(frozen) is frozen
    assert pickle.loads(pickle.dumps(frozen)) == frozen
    assert FrozenMapping() == {}
