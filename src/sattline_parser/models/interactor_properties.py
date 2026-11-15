"""Catalogue of the interactor properties the scanner names but the grammar does not.

An interactor body accepts any ``NAME`` as a flag or as an ``NAME = value``
assignment. That keeps an unknown property parsing, but it also means a reader
sees ``FlagClause("Int_Value")`` with no hint what the property is. This module
names the spellings the scanner enum defines, classifies each one, and reads a
property's written clause out of the interactor that carries it.

The catalogue is vocabulary, not a runtime contract. The parser still stores the
clause exactly as written, in ``InteractProperties.body`` or in the flat
``flags`` / ``assigns`` lists a ``ComButProc_`` uses, and an unknown property
still parses as a generic clause. A spec says what the spelling is for, and the
``datatype`` is the value type when the spelling or the grammar fixes it; a
property whose written value can be any SattLine value has ``datatype`` ``None``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from sattline_parser.grammar.constants import KEY_ASSIGNS, KEY_BODY, KEY_FLAGS
from sattline_parser.names import fold_identifier

from .ast_model import InteractObject, ScalarDatatype
from .clauses import AssignClause, FlagClause
from .properties import InteractBodyEntry

__all__ = [
    "InteractorPropertyKind",
    "InteractorPropertySpec",
    "TypedInteractorProperty",
    "find_interactor_property",
    "interactor_property_catalogue",
    "typed_interactor_properties",
]


class InteractorPropertyKind(StrEnum):
    """What role an interactor property plays in the written body."""

    #: Chooses or names a variable, such as ``SelectVariable`` or ``OK_Variable``.
    SELECT = "select"
    #: Configures a numeric range or step, such as ``OpMin`` or ``OpStep``.
    RANGE = "range"
    #: Configures display width or precision, such as ``Digits_``.
    COUNTER = "counter"
    #: A boolean setting or action, such as ``Visible_`` or ``ToggleAction``.
    BOOLEAN = "boolean"
    #: A typed literal value, such as ``Int_Value`` or ``Real_Value``.
    NUMERIC = "numeric"
    #: A text value, such as ``SetApp_`` or ``Alt_Text``.
    TEXT = "text"
    #: An event binding, such as ``Event_Severity_``.
    EVENT = "event"


@dataclass(frozen=True, slots=True)
class InteractorPropertySpec:
    """One known interactor property spelling.

    ``name`` is the spelling the scanner enum defines. ``kind`` groups the
    spelling by role. ``datatype`` is the written value's scalar type when the
    spelling fixes it, and ``None`` when any value is accepted. ``summary`` is a
    short description for a reader or a ``query`` row.
    """

    name: str
    kind: InteractorPropertyKind
    datatype: ScalarDatatype | None
    summary: str


def _spec(
    name: str,
    kind: InteractorPropertyKind,
    datatype: ScalarDatatype | None,
    summary: str,
) -> InteractorPropertySpec:
    return InteractorPropertySpec(name=name, kind=kind, datatype=datatype, summary=summary)


_BOOLEAN = ScalarDatatype.BOOLEAN
_INTEGER = ScalarDatatype.INTEGER
_REAL = ScalarDatatype.REAL
_STRING = ScalarDatatype.STRING

#: Every interactor property spelling the scanner enum defines, keyed by folded
#: name. A spelling is listed only when the scanner table carries it, so the
#: table and this catalogue cannot drift apart silently.
interactor_property_catalogue: Mapping[str, InteractorPropertySpec] = MappingProxyType(
    {
        fold_identifier(spec.name): spec
        for spec in (
            _spec("SelectVariable", InteractorPropertyKind.SELECT, None, "Variable selected by the interactor"),
            _spec("Variable", InteractorPropertyKind.SELECT, None, "Variable bound to the interactor value"),
            _spec("OK_Variable", InteractorPropertyKind.SELECT, None, "Variable set when the OK button is chosen"),
            _spec("Cancel_Variable", InteractorPropertyKind.SELECT, None, "Variable set when Cancel is chosen"),
            _spec("SetApp_", InteractorPropertyKind.SELECT, _STRING, "Application name the interactor sets"),
            _spec("OpMin", InteractorPropertyKind.RANGE, _REAL, "Lowest operator value"),
            _spec("OpMax", InteractorPropertyKind.RANGE, _REAL, "Highest operator value"),
            _spec("OpStep", InteractorPropertyKind.RANGE, _REAL, "Operator step size"),
            _spec("SetVal_", InteractorPropertyKind.RANGE, None, "Value the operator writes"),
            _spec("Value_", InteractorPropertyKind.RANGE, None, "Current value of the interactor"),
            _spec("Dim_", InteractorPropertyKind.RANGE, None, "Dimension applied to the interactor"),
            _spec("Decimal_", InteractorPropertyKind.COUNTER, _INTEGER, "Decimal places to display"),
            _spec("Digits_", InteractorPropertyKind.COUNTER, _INTEGER, "Digits to display"),
            _spec("NoOf_", InteractorPropertyKind.COUNTER, _INTEGER, "Number of displayed items"),
            _spec("Bool_Value", InteractorPropertyKind.NUMERIC, _BOOLEAN, "Boolean value"),
            _spec("Int_Value", InteractorPropertyKind.NUMERIC, _INTEGER, "Integer value"),
            _spec("Real_Value", InteractorPropertyKind.NUMERIC, _REAL, "Real value"),
            _spec("String_Value", InteractorPropertyKind.TEXT, _STRING, "String value"),
            _spec("Alt_Text", InteractorPropertyKind.TEXT, _STRING, "Alternative text"),
            _spec("Event_Text_", InteractorPropertyKind.EVENT, _STRING, "Text reported with the event"),
            _spec("Event_Tag_", InteractorPropertyKind.EVENT, _STRING, "Tag reported with the event"),
            _spec("Event_Severity_", InteractorPropertyKind.EVENT, None, "Severity reported with the event"),
            _spec("Event_Class_", InteractorPropertyKind.EVENT, None, "Class reported with the event"),
            _spec("Key_", InteractorPropertyKind.TEXT, None, "Key that activates the interactor"),
            _spec("Visible_", InteractorPropertyKind.BOOLEAN, _BOOLEAN, "Whether the interactor is visible"),
            _spec("Value_Changed", InteractorPropertyKind.BOOLEAN, _BOOLEAN, "Whether the value changed this scan"),
            _spec("SetAction", InteractorPropertyKind.BOOLEAN, _BOOLEAN, "Action chosen when the value is set"),
            _spec("ResetAction", InteractorPropertyKind.BOOLEAN, _BOOLEAN, "Action chosen when the value is reset"),
            _spec("ToggleAction", InteractorPropertyKind.BOOLEAN, _BOOLEAN, "Action chosen when the value toggles"),
            _spec("Enable_Delay", InteractorPropertyKind.BOOLEAN, None, "Delay applied to enabling the interactor"),
        )
    }
)


def find_interactor_property(name: str) -> InteractorPropertySpec | None:
    """The catalogue entry for an interactor property spelling, or ``None``.

    Comparison uses :func:`sattline_parser.names.fold_identifier`, the same
    identity rule the symbol table uses, so the spelling is case-insensitive.
    """
    return interactor_property_catalogue.get(fold_identifier(name))


@dataclass(frozen=True, slots=True)
class TypedInteractorProperty:
    """One written interactor property, with its catalogue entry when known.

    ``clause`` is the parsed ``FlagClause`` or ``AssignClause``, unchanged.
    ``spec`` is ``None`` for a spelling the catalogue does not define, so a
    custom property still appears in the sequence.
    """

    clause: FlagClause | AssignClause
    spec: InteractorPropertySpec | None

    @property
    def name(self) -> str:
        """The property spelling as written."""
        return self.clause.name

    @property
    def value(self) -> object:
        """The written value, or ``None`` for a bare flag."""
        return getattr(self.clause, "value", None)


def typed_interactor_properties(obj: InteractObject) -> tuple[TypedInteractorProperty, ...]:
    """The interactor's flag and assignment properties, in written order.

    An interactor keeps its properties in one of two shapes. A ``ComButProc_``
    stores flat ``flags`` and ``assigns`` lists with no ordering between the
    kinds; every other interactor stores one ordered ``body``. The body shape is
    read first, then the flat lists, so a hand-built object that carries both is
    still read once per clause.

    A clause reached twice is yielded once. Entries that are not a flag or an
    assignment, such as an alignment or a colour, are not properties and are
    skipped.
    """
    return tuple(_iter_properties(obj))


def _iter_properties(obj: InteractObject) -> Iterator[TypedInteractorProperty]:
    seen: set[int] = set()
    properties = obj.properties
    body: list[InteractBodyEntry] | None = properties.get(KEY_BODY)
    for entry in body or ():
        if isinstance(entry, (FlagClause, AssignClause)) and id(entry) not in seen:
            seen.add(id(entry))
            yield _typed(entry)
    for clause in (*properties.get(KEY_FLAGS, ()), *properties.get(KEY_ASSIGNS, ())):
        if id(clause) not in seen:
            seen.add(id(clause))
            yield _typed(clause)


def _typed(clause: FlagClause | AssignClause) -> TypedInteractorProperty:
    return TypedInteractorProperty(clause=clause, spec=find_interactor_property(clause.name))
