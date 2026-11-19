"""Freeze a parsed AST at the project boundary.

A project exposes a parsed tree and a derived index over that tree. If a caller
can mutate the tree after the index is built, the two views disagree. A loaded
project therefore owns an immutable snapshot: every mutable model node carries a
lock flag, and every list and mapping reachable from the root is replaced by a
tuple or a read-only mapping.

The parser and transformer build mutable nodes. Only :func:`freeze_ast` locks
them, so construction is unchanged. ``from_programs`` deep-copies before
freezing, so the caller keeps ownership of the tree it passed in.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from typing import Any, cast

__all__ = ["FrozenMapping", "FrozenNode", "freeze_ast"]


class FrozenMapping(Mapping[object, object]):
    """A read-only mapping that still pickles and deep-copies.

    ``types.MappingProxyType`` supports neither, so a frozen tree that carries a
    parsed ``Time_Value`` payload could not be pickled, deep-copied, or passed
    through ``from_programs``. This class is the read-only replacement: item
    assignment and deletion raise ``TypeError`` the way the proxy does, and
    ``__reduce__`` rebuilds it from a plain dict, so ``pickle`` and
    ``copy.deepcopy`` round-trip. It is immutable, so both copy protocols return
    the same object.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[object, object] | None = None) -> None:
        self._data: dict[object, object] = dict(data or {})

    def __getitem__(self, key: object) -> object:
        return self._data[key]

    def __iter__(self) -> Iterator[object]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenMapping({self._data!r})"

    def __reduce__(self) -> tuple[type[FrozenMapping], tuple[dict[object, object]]]:
        return (FrozenMapping, (dict(self._data),))

    def __copy__(self) -> FrozenMapping:
        return self

    def __deepcopy__(self, memo: dict[int, object] | None = None) -> FrozenMapping:
        del memo
        return self


class FrozenNode:
    """Mixin that rejects attribute mutation after :func:`freeze_ast` runs.

    The lock is an instance flag rather than a dataclass field, so it does not
    participate in equality, serialization, or field-coverage tests.
    """

    def __setattr__(self, name: str, value: object) -> None:
        if self.__dict__.get("_frozen", False):
            raise dataclasses.FrozenInstanceError(f"cannot assign to field {name!r} on a frozen AST node")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if self.__dict__.get("_frozen", False):
            raise dataclasses.FrozenInstanceError(f"cannot delete field {name!r} on a frozen AST node")
        object.__delattr__(self, name)


def freeze_ast(value: object) -> object:
    """Return *value* with every reachable mutable node and container frozen.

    Lists become tuples, dictionaries become read-only mappings, and every
    ``FrozenNode`` is locked. The traversal is in place for nodes, so the
    identity of the parsed root is preserved. It is idempotent: freezing an
    already frozen tree is a no-op.
    """
    return _freeze(value)


def _freeze(value: object) -> object:
    if isinstance(value, FrozenNode):
        node = cast(Any, value)
        for field in dataclasses.fields(node):
            object.__setattr__(node, field.name, _freeze(getattr(node, field.name)))
        object.__setattr__(node, "_frozen", True)
        return node
    if isinstance(value, list):
        items = cast("list[object]", value)
        return tuple(_freeze(item) for item in items)
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        return tuple(_freeze(item) for item in items)
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return FrozenMapping({key: _freeze(item) for key, item in mapping.items()})
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # Frozen dataclasses from the model layer still contain containers that
        # need the same treatment, but they cannot be locked again.
        node = cast(Any, value)
        for field in dataclasses.fields(node):
            object.__setattr__(node, field.name, _freeze(getattr(node, field.name)))
        return node
    return value
