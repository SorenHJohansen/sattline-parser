"""Freeze a parsed AST at the project boundary.

A project exposes a parsed tree and a derived index over that tree. If a caller
can mutate the tree after the index is built, the two views disagree. A loaded
project therefore owns an immutable snapshot: every mutable model node carries a
lock flag, and every list and mapping reachable from the root is replaced by a
tuple or a read-only mapping.

The parser and transformer build mutable nodes. Only :func:`freeze_ast` locks
them, so construction is unchanged. ``from_programs`` copies and freezes in one
pass with :func:`copy_frozen_ast`, so the caller keeps ownership of the tree it
passed in.

The copy uses an explicit stack. A parsed tree may be as deep as the parser
accepts, and ``copy.deepcopy`` grows the Python call stack several frames per
level, so it overflows on a tree the parser accepts. Freezing in place is a
single frame per level and stays inside the limit.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, cast

__all__ = ["FrozenMapping", "FrozenNode", "copy_frozen_ast", "freeze_ast"]


class FrozenMapping[Key, Value](Mapping[Key, Value]):
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

    def __init__(self, data: Mapping[Key, Value] | None = None) -> None:
        self._data: dict[Key, Value] = dict(data or {})

    def __getitem__(self, key: Key) -> Value:
        return self._data[key]

    def __iter__(self) -> Iterator[Key]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenMapping({self._data!r})"

    def __reduce__(self) -> tuple[type[FrozenMapping[Key, Value]], tuple[dict[Key, Value]]]:
        return (FrozenMapping, (dict(self._data),))

    def __copy__(self) -> FrozenMapping[Key, Value]:
        return self

    def __deepcopy__(self, memo: dict[int, object] | None = None) -> FrozenMapping[Key, Value]:
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


def copy_frozen_ast(value: object) -> object:
    """Return a frozen deep copy of *value*.

    The copy keeps the caller's tree untouched and preserves object sharing, so
    two fields that held one tail object still hold one copied object after the
    copy. A dataclass is rebuilt from its fields with the copied children, and a
    ``FrozenNode`` copy is locked before it is returned. Immutable
    values (scalars, enum members, a ``FrozenMapping``) keep their identity.

    The traversal is post-order over an explicit stack, so a tree at the depth
    the parser accepts does not grow the Python call stack.
    """
    memo: dict[int, object] = {}
    pending: list[tuple[object, bool]] = [(value, False)]
    while pending:
        current, rebuild = pending.pop()
        if not _is_composite(current):
            continue
        identity = id(current)
        if rebuild:
            # A shared child can be scheduled by more than one owner. The first
            # copy wins, so both owners keep sharing one object.
            memo.setdefault(identity, _rebuild(current, memo))
            continue
        if identity in memo:
            continue
        pending.append((current, True))
        for child in _composite_children(current):
            pending.append((child, False))
    return memo[id(value)] if _is_composite(value) else value


def _is_composite(value: object) -> bool:
    """True for a value whose children have to be copied or frozen."""
    if _is_literal(value):
        return True
    if isinstance(value, (list, tuple, dict)):
        return True
    return dataclasses.is_dataclass(value) and not isinstance(value, type)


def _is_literal(value: object) -> bool:
    """True for a numeric literal that carries mutable source metadata.

    ``IntLiteral`` and ``FloatLiteral`` subclass ``int`` and ``float`` but hold
    ``span``, ``clamped``, and ``written`` as ordinary attributes. Treating them
    as immutable scalars would share them with the caller across the project
    boundary, where those attributes could then be changed on both sides.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and hasattr(value, "written")
        and hasattr(value, "clamped")
    )


def _copy_literal(value: object) -> object:
    """A detached copy of an ``IntLiteral`` or ``FloatLiteral``."""
    literal = cast(Any, value)
    number = float(literal) if isinstance(value, float) else int(literal)
    factory = cast("Callable[..., object]", type(value))
    return factory(number, literal.span, literal.clamped, literal.written)


def _composite_children(value: object) -> tuple[object, ...]:
    """The direct child values of a composite value."""
    if _is_literal(value):
        return ()
    if isinstance(value, dict):
        return tuple(cast("dict[object, object]", value).values())
    if isinstance(value, (list, tuple)):
        return tuple(cast("Sequence[object]", value))
    node = cast(Any, value)
    return tuple(getattr(node, field.name) for field in dataclasses.fields(node))


def _resolve(value: object, memo: dict[int, object]) -> object:
    """Return the copied form of *value*, or *value* when it is immutable."""
    return memo[id(value)] if _is_composite(value) else value


def _rebuild(value: object, memo: dict[int, object]) -> object:
    """Build one composite from its already-copied children."""
    if _is_literal(value):
        return _copy_literal(value)
    if isinstance(value, list):
        return tuple(_resolve(item, memo) for item in cast("list[object]", value))
    if isinstance(value, tuple):
        return tuple(_resolve(item, memo) for item in cast("tuple[object, ...]", value))
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return FrozenMapping({key: _resolve(item, memo) for key, item in mapping.items()})
    node = cast(Any, value)
    fields = {field.name: _resolve(getattr(node, field.name), memo) for field in dataclasses.fields(node)}
    copy: object = type(node)(**fields)
    if isinstance(copy, FrozenNode):
        object.__setattr__(copy, "_frozen", True)
    return copy


def _freeze(value: object) -> object:
    if _is_literal(value):
        return _copy_literal(value)
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
