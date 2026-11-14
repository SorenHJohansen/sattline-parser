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
from collections.abc import Callable, Iterable, Mapping, Sequence

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

    Only keys in the closure contribute, so a definition from an unrelated
    program is never borrowed.
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
    *,
    closure_of: Callable[[str], frozenset[str]] | None = None,
) -> dict[str, set[str]]:
    """Map each program key to the module-type names reached from ``targets``.

    ``programs`` is the loader registry: program key to an object with ``code``
    (a :class:`BasePicture`). ``targets`` are program keys. A target contributes
    every module type in its own file and every library module type its
    submodules invoke. Those library definitions contribute their own nested
    invocations, transitively.

    ``closure_of`` answers "which program keys can this key see" and defaults to
    walking the declared dependency names. The loader passes its resolved
    dependency keys instead, because one name may resolve to different bodies
    for different requesters.
    """
    index: dict[str, list[tuple[str, ModuleTypeDef]]] = {}
    closures: dict[str, frozenset[str]] = {}
    for key, program in programs.items():
        if closure_of is not None:
            closures[key] = closure_of(key)
        else:
            closures[key] = visible_program_keys(programs, key, program.dependencies)
        for moduletype in program.code.moduletype_defs:
            index.setdefault(moduletype.name.casefold(), []).append((key, moduletype))

    pending: deque[tuple[str, str]] = deque()
    for target in targets:
        program = programs.get(target)
        if program is None:
            continue
        pending.extend((reference, target) for reference in iter_moduletype_refs(program.code.submodules))
        for moduletype in program.code.moduletype_defs:
            pending.extend((reference, target) for reference in iter_moduletype_refs(moduletype.submodules))

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
