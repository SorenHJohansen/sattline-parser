"""Invoked-module reachability across a loaded project.

A program file can define many module types; a library file usually defines far
more than any one consumer invokes. Validation for an invoked scope starts at
the selected program's own module tree, follows every ``ModuleTypeInstance``
reference into the loaded definitions, and continues through the submodules of
those definitions. Only the module types reached this way are validated.

Name resolution is scoped to the referencing program's dependency closure: two
libraries may reuse a module-type name, and a reference inside one closure must
never pull the other library's definition into the invoked set.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence

from sattline_parser.models.ast_model import (
    FrameModule,
    ModuleTypeDef,
    ModuleTypeInstance,
    SingleModule,
)

from .models import SattLineProgram

ModuleNode = SingleModule | FrameModule | ModuleTypeInstance


def iter_moduletype_refs(nodes: Iterable[ModuleNode]) -> Iterable[str]:
    """Yield every module-type name referenced below ``nodes``."""
    for node in nodes:
        if isinstance(node, ModuleTypeInstance):
            yield node.moduletype_name
        else:
            yield from iter_moduletype_refs(node.submodules)


def visible_program_keys(
    programs: Mapping[str, SattLineProgram],
    key: str,
    dependencies: Sequence[str],
) -> frozenset[str]:
    """The program keys *key* can see: itself plus its transitive dependencies.

    A dependency that was not loaded contributes nothing, so an incomplete
    closure stays incomplete rather than silently borrowing a same-named
    definition from an unrelated program.
    """
    visible = {key}
    seen = {key}
    pending = [dependency.casefold() for dependency in dependencies]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        program = programs.get(current)
        if program is None:
            continue
        visible.add(current)
        pending.extend(dependency.casefold() for dependency in program.dependencies)
    return frozenset(visible)


def invoked_moduletypes(
    programs: Mapping[str, SattLineProgram],
    targets: Iterable[str],
) -> dict[str, set[str]]:
    """Map each program key to the module-type names reached from ``targets``.

    ``programs`` is the loader registry: program key to an object with ``code``
    (a :class:`BasePicture`). A target contributes every module type in its own
    file and every library module type its submodules invoke. Those library
    definitions contribute their own nested invocations, transitively.
    """
    index: dict[str, list[tuple[str, ModuleTypeDef]]] = {}
    closures: dict[str, frozenset[str]] = {}
    for key, program in programs.items():
        closures[key] = visible_program_keys(programs, key, program.dependencies)
        for moduletype in program.code.moduletype_defs:
            index.setdefault(moduletype.name.casefold(), []).append((key, moduletype))

    pending: deque[tuple[str, str]] = deque()
    for target in targets:
        key = target.casefold()
        program = programs.get(key)
        if program is None:
            continue
        pending.extend((reference, key) for reference in iter_moduletype_refs(program.code.submodules))
        for moduletype in program.code.moduletype_defs:
            pending.extend((reference, key) for reference in iter_moduletype_refs(moduletype.submodules))

    reachable: dict[str, set[str]] = {}
    seen: set[tuple[str, str]] = set()
    while pending:
        name, requester = pending.popleft()
        folded = name.casefold()
        if (folded, requester) in seen:
            continue
        seen.add((folded, requester))
        for key, moduletype in _resolve_moduletype(folded, requester, index, closures):
            reachable.setdefault(key, set()).add(moduletype.name.casefold())
            pending.extend((reference, key) for reference in iter_moduletype_refs(moduletype.submodules))
    return reachable


def _resolve_moduletype(
    name: str,
    requester: str,
    index: Mapping[str, list[tuple[str, ModuleTypeDef]]],
    closures: Mapping[str, frozenset[str]],
) -> list[tuple[str, ModuleTypeDef]]:
    """Definitions visible to *requester* for *name*.

    A local definition wins, then a definition from the requester's dependency
    closure. A definition in an unrelated program is never used, so a library
    that reuses a module-type name cannot have its unused types validated
    because another closure happened to invoke the same name.
    """
    entries = index.get(name, ())
    local = [entry for entry in entries if entry[0] == requester]
    if local:
        return local
    visible = closures[requester]
    return [entry for entry in entries if entry[0] in visible]


__all__ = ["invoked_moduletypes", "iter_moduletype_refs", "visible_program_keys"]
