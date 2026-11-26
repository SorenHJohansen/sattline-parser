"""The project freeze boundary keeps a tree renderable, picklable, and copyable."""

from __future__ import annotations

import copy
import dataclasses
import pickle
from typing import cast

import pytest

from sattline_parser.api import parse_source_text
from sattline_parser.ast import BasePicture, IntLiteral
from sattline_parser.formatting import format_source
from sattline_parser.models.freeze import FrozenMapping, copy_frozen_ast, freeze_ast

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
    frozen = cast("FrozenMapping[object, object]", freeze_ast({"items": [1, 2]}))

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


def test_copy_frozen_ast_copies_sharing_without_touching_the_source() -> None:
    """A tail held by two fields is one object before and after the copy."""
    picture = parse_source_text(
        """"Syntax version 2.23"
"Original file date: ---"
"Program date: ---, name: Shared"
Frozen Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 ) Enable_ = True : InVar_ "Flag"
ENDDEF (*Shared*);
""",
        log_failures=False,
    )
    assert picture.moduledef is not None
    rectangle = picture.moduledef.graph_objects[0]
    original_tail = rectangle.properties.get("enable_tail")
    original_tails = rectangle.properties.get("tails")
    assert original_tail is not None
    assert original_tails is not None
    assert original_tail is original_tails[0]

    copied = cast(BasePicture, copy_frozen_ast(picture))

    assert copied.moduledef is not None
    copied_rectangle = copied.moduledef.graph_objects[0]
    copied_tail = copied_rectangle.properties.get("enable_tail")
    copied_tails = copied_rectangle.properties.get("tails")
    assert copied_tail is not None
    assert copied_tails is not None
    assert copied_tail is copied_tails[0]
    assert copied_tail is not original_tail
    # The caller keeps its own mutable tree.
    assert isinstance(picture.moduledef.graph_objects, list)
    assert isinstance(copied.moduledef.graph_objects, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        copied.moduledef.grid = 0.5


def test_copy_frozen_ast_detaches_literal_metadata() -> None:
    """A numeric literal carries mutable source metadata, so it is copied."""
    picture = parse_source_text(
        """"Syntax version 2.23"
"Original file date: ---"
"Program date: ---, name: Literal"
Frozen Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION
LOCALVARIABLES
   X: integer := 7;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*Literal*);
""",
        log_failures=False,
    )
    literal = picture.localvariables[0].init_value
    assert isinstance(literal, IntLiteral)

    copied = cast(BasePicture, copy_frozen_ast(picture))
    copied_literal = copied.localvariables[0].init_value
    assert isinstance(copied_literal, IntLiteral)
    assert copied_literal == literal
    assert copied_literal is not literal
    with pytest.raises(dataclasses.FrozenInstanceError):
        copied_literal.written = "caller mutation"
