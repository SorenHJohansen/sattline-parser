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
from sattline_parser.models.ast_model import BasePicture, DataType, Simple_DataType, Variable
from sattline_parser.names import fold_identifier


@dataclass(frozen=True, slots=True)
class FieldDef:
    """One field of a record datatype."""

    name: str
    datatype: Simple_DataType | str
    state: bool | None = False


@dataclass(frozen=True, slots=True)
class RecordDef:
    """A record datatype and its fields, keyed by folded field name."""

    name: str
    fields_by_key: dict[str, FieldDef]


class TypeGraph:
    """Case-insensitive graph of record datatypes.

    Backed by the file's ``DATATYPE`` definitions, where each field is a
    :class:`Variable` in ``DataType.var_list``, plus the builtin record specs.
    """

    def __init__(self, records_by_key: dict[str, RecordDef]) -> None:
        self._records_by_key = records_by_key

    @staticmethod
    @cache
    def _builtin_records() -> dict[str, RecordDef]:
        records: dict[str, RecordDef] = {}
        for datatype_name, field_specs in BUILTIN_RECORD_SPECS.items():
            fields = {
                fold_identifier(field_name): FieldDef(name=field_name, datatype=datatype)
                for field_name, datatype in field_specs
            }
            records[fold_identifier(datatype_name)] = RecordDef(name=datatype_name, fields_by_key=fields)
        return records

    @classmethod
    def from_datatypes(cls, datatypes: Iterable[DataType]) -> TypeGraph:
        records = dict(cls._builtin_records())
        for datatype in datatypes:
            fields: dict[str, FieldDef] = {}
            for field in datatype.var_list:
                definition = FieldDef(name=field.name, datatype=field.datatype, state=field.state)
                fields[fold_identifier(definition.name)] = definition
            records[fold_identifier(datatype.name)] = RecordDef(name=datatype.name, fields_by_key=fields)
        return cls(records)

    @classmethod
    def from_basepicture(cls, bp: BasePicture) -> TypeGraph:
        return cls.from_datatypes(bp.datatype_defs)

    def has_record(self, type_name: str) -> bool:
        return fold_identifier(type_name) in self._records_by_key

    def record(self, type_name: str) -> RecordDef | None:
        return self._records_by_key.get(fold_identifier(type_name))

    def field(self, record_type: str, field_name: str) -> FieldDef | None:
        record = self.record(record_type)
        if record is None:
            return None
        return record.fields_by_key.get(fold_identifier(field_name))

    def field_type(self, record_type: str, field_name: str) -> Simple_DataType | str | None:
        field = self.field(record_type, field_name)
        return field.datatype if field is not None else None

    def iter_leaf_field_paths(self, root_type: Simple_DataType | str) -> Iterator[tuple[str, ...]]:
        """Yield field paths from a type down to leaf (simple) datatypes.

        A simple datatype yields the empty path. A record yields paths such as
        ``("I", "WT001", "value")``. Unknown external types and cycles are
        treated as leaves so expansion always terminates.
        """
        if isinstance(root_type, Simple_DataType):
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
                if isinstance(field.datatype, Simple_DataType):
                    yield new_prefix
                else:
                    stack.append((str(field.datatype), new_prefix, next_ancestors))

    def iter_all_addressable_paths(self, root_var: Variable) -> Iterator[tuple[str, ...]]:
        """Expand leaf paths for a variable's declared datatype."""
        yield from self.iter_leaf_field_paths(root_var.datatype)


__all__ = ["FieldDef", "RecordDef", "TypeGraph"]
