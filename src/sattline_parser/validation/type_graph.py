"""Record and datatype field resolution for validation and analyzers.

The graph is built from the file's ``DATATYPE`` definitions plus the builtin
record field specifications. It answers "what is the datatype of this field
path?" without deciding whether an access is legal; callers apply the rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache

from sattline_parser.builtins.records import BUILTIN_RECORD_SPECS
from sattline_parser.models.ast_model import BasePicture, DataType, ScalarDatatype, Variable
from sattline_parser.names import fold_identifier


@dataclass(frozen=True, slots=True)
class FieldDef:
    """One field of a record datatype."""

    name: str
    datatype: ScalarDatatype | str
    state: bool | None = False


def _record_def(datatype: DataType) -> RecordDef:
    """A declared record's fields, keyed by folded field name, with a known shape."""
    fields: dict[str, FieldDef] = {}
    for field in datatype.var_list:
        definition = FieldDef(name=field.name, datatype=field.datatype, state=field.state)
        fields[fold_identifier(definition.name)] = definition
    return RecordDef(name=datatype.name, fields_by_key=fields)


@dataclass(frozen=True, slots=True)
class RecordDef:
    """A record datatype and its fields, keyed by folded field name.

    ``shape_known`` distinguishes a declared shape from a transcribed one. A
    record declared in a file, or loaded from a dependency, has a known shape
    even when it declares zero fields: every field it omits is provably absent.
    A builtin record spec with no field table is declared but not modelled, so a
    field access through it is unproven rather than a typo.
    """

    name: str
    fields_by_key: dict[str, FieldDef]
    shape_known: bool = True


class TypeGraph:
    """Case-insensitive graph of record datatypes.

    Backed by the file's ``DATATYPE`` definitions, where each field is a
    :class:`Variable` in ``DataType.var_list``, plus the builtin record specs.
    """

    def __init__(
        self,
        records_by_key: dict[str, RecordDef],
        duplicated_names: frozenset[str] = frozenset(),
    ) -> None:
        self._records_by_key = records_by_key
        #: Names declared more than once in the same file. Two shapes are two
        #: valid readings, so both a missing field and a field's datatype are
        #: unproven rather than whichever definition happened to be read last.
        self._duplicated_names = duplicated_names

    @staticmethod
    @cache
    def _builtin_records() -> dict[str, RecordDef]:
        records: dict[str, RecordDef] = {}
        for datatype_name, field_specs in BUILTIN_RECORD_SPECS.items():
            fields = {
                fold_identifier(field_name): FieldDef(name=field_name, datatype=datatype)
                for field_name, datatype in field_specs
            }
            # An empty builtin spec is a declared name whose shape is not
            # transcribed, so its fields stay unproven.
            records[fold_identifier(datatype_name)] = RecordDef(
                name=datatype_name, fields_by_key=fields, shape_known=bool(fields)
            )
        return records

    @classmethod
    def from_datatypes(
        cls,
        datatypes: Iterable[DataType],
        *,
        fallback: Iterable[DataType] = (),
    ) -> TypeGraph:
        """Build a graph from ``datatypes`` with ``fallback`` shapes underneath.

        ``datatypes`` are the definitions the caller owns, for example the file's
        own ``DATATYPE`` declarations. ``fallback`` are definitions that must not
        shadow them, for example loaded dependencies. A name declared more than
        once in ``datatypes`` has two shapes and is unproven; a ``fallback``
        definition of the same name is replaced, not counted as a duplicate.
        """
        records = dict(cls._builtin_records())
        for datatype in fallback:
            records[fold_identifier(datatype.name)] = _record_def(datatype)
        seen: set[str] = set()
        duplicated: set[str] = set()
        for datatype in datatypes:
            key = fold_identifier(datatype.name)
            if key in seen:
                duplicated.add(key)
            seen.add(key)
            records[key] = _record_def(datatype)
        return cls(records, frozenset(duplicated))

    @classmethod
    def from_basepicture(cls, bp: BasePicture) -> TypeGraph:
        return cls.from_datatypes(bp.datatype_defs)

    def has_record(self, type_name: str) -> bool:
        return fold_identifier(type_name) in self._records_by_key

    def has_known_fields(self, type_name: str) -> bool:
        """True when the record's shape is modelled well enough to judge a field.

        A declared record has a known shape even with zero fields, so an omitted
        field there is a typo. An empty builtin spec is declared but not
        modelled, and a name declared more than once has more than one valid
        shape, so in those two cases a missing field is unproven rather than
        absent.
        """
        key = fold_identifier(type_name)
        if key in self._duplicated_names:
            return False
        record = self._records_by_key.get(key)
        return record is not None and record.shape_known

    def record(self, type_name: str) -> RecordDef | None:
        return self._records_by_key.get(fold_identifier(type_name))

    def field(self, record_type: str, field_name: str) -> FieldDef | None:
        """The field, or ``None`` when it is absent or the shape is unproven.

        A name declared more than once has more than one valid shape, so a field
        present in only the last definition is not evidence: the field's
        datatype is unproven and its access cannot be type-checked.
        """
        key = fold_identifier(record_type)
        if key in self._duplicated_names:
            return None
        record = self._records_by_key.get(key)
        if record is None:
            return None
        return record.fields_by_key.get(fold_identifier(field_name))

    def field_type(self, record_type: str, field_name: str) -> ScalarDatatype | str | None:
        field = self.field(record_type, field_name)
        return field.datatype if field is not None else None

    def iter_leaf_field_paths(self, root_type: ScalarDatatype | str) -> Iterator[tuple[str, ...]]:
        """Yield field paths from a type down to leaf (simple) datatypes.

        A simple datatype yields the empty path. A record yields paths such as
        ``("I", "WT001", "value")``. Unknown external types and cycles are
        treated as leaves so expansion always terminates.
        """
        if isinstance(root_type, ScalarDatatype):
            yield ()
            return

        stack: list[tuple[str, tuple[str, ...], frozenset[str]]] = [(root_type, (), frozenset())]

        while stack:
            type_name, prefix, ancestors = stack.pop()
            type_key = fold_identifier(type_name)
            record = self._records_by_key.get(type_key)
            if record is None or not record.fields_by_key or type_key in ancestors:
                yield prefix
                continue

            next_ancestors = ancestors | {type_key}
            for field in record.fields_by_key.values():
                new_prefix = (*prefix, field.name)
                if isinstance(field.datatype, ScalarDatatype):
                    yield new_prefix
                else:
                    stack.append((str(field.datatype), new_prefix, next_ancestors))

    def iter_all_addressable_paths(self, root_var: Variable) -> Iterator[tuple[str, ...]]:
        """Expand leaf paths for a variable's declared datatype."""
        yield from self.iter_leaf_field_paths(root_var.datatype)


__all__ = ["FieldDef", "RecordDef", "TypeGraph"]
