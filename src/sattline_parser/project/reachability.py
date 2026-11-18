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
from sattline_parser.names import fold_identifier

from .identity import UnitIdentity
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
    program is never borrowed. A declared dependency is resolved in the caller's
    key space: an exact mapping key first, then the program's own name compared
    with the language name table, so ``{"Main": main}`` and ``{"main": main}``
    both answer for a sidecar that declares ``Main``. The result holds the
    caller's keys, never a spelling invented here.
    """
    lookup = _key_space(programs)
    visible = {key}
    seen = {key}
    pending = list(dependencies)
    while pending:
        current = _resolve_program_key(programs, lookup, pending.pop())
        if current is None or current in seen:
            continue
        seen.add(current)
        visible.add(current)
        pending.extend(programs[current].dependencies)
    return frozenset(visible)


def _key_space(programs: Mapping[str, SattLineProgram]) -> dict[str, str]:
    """Program names mapped to their caller keys by language identity.

    Only the program's own name is registered, and only under
    :func:`~sattline_parser.names.fold_identifier`. A mapping key is not folded:
    a caller that keys by ``str.casefold`` view key, such as ``strasse`` for
    ``Straße``, must not make a dependency named ``STRASSE`` resolve to that
    unit. A caller's exact mapping key still resolves through
    :func:`_resolve_program_key`, and the first registration wins.
    """
    lookup: dict[str, str] = {}
    for program_key, program in programs.items():
        lookup.setdefault(UnitIdentity.of(program.name).key, program_key)
    return lookup


def _resolve_program_key(
    programs: Mapping[str, SattLineProgram],
    lookup: Mapping[str, str],
    spelling: str,
) -> str | None:
    """The caller's key for *spelling*, or ``None`` when it names no program.

    An exact mapping key is accepted as written. Any other spelling is compared
    with the program names under the language name table, so case differences the
    language folds resolve while ``Straße`` and ``STRASSE`` stay apart.
    """
    if spelling in programs:
        return spelling
    return lookup.get(UnitIdentity.of(spelling).key)


def invoked_moduletypes(
    programs: Mapping[str, SattLineProgram],
    targets: Iterable[str],
    *,
    closure_of: Callable[[str], frozenset[str]] | None = None,
) -> dict[str, set[str]]:
    """Map each program key to the module-type names reached from ``targets``.

    ``programs`` is the loader registry: program key to an object with ``code``
    (a :class:`BasePicture`). ``targets`` name programs in the caller's key
    space: an exact mapping key, or a program name that matches under
    :func:`~sattline_parser.names.fold_identifier`. A target contributes every
    module type in its own file and every library module type its submodules
    invoke. Those library definitions contribute their own nested invocations,
    transitively. Keys are the mapping keys the caller supplied, and the values
    are module-type names folded with
    :func:`sattline_parser.names.fold_identifier`, so a caller can compare them
    with the language name table.

    ``closure_of`` answers "which program keys can this key see" and defaults to
    walking the declared dependency names in the caller's key space. The loader
    passes its resolved dependency keys instead, because one name may resolve to
    different bodies for different requesters.
    """
    lookup = _key_space(programs)
    index: dict[str, list[tuple[str, ModuleTypeDef]]] = {}
    closures: dict[str, frozenset[str]] = {}
    for key, program in programs.items():
        if closure_of is not None:
            closures[key] = closure_of(key)
        else:
            closures[key] = visible_program_keys(programs, key, program.dependencies)
        for moduletype in program.code.moduletype_defs:
            index.setdefault(fold_identifier(moduletype.name), []).append((key, moduletype))

    pending: deque[tuple[str, str]] = deque()
    for target in targets:
        resolved = _resolve_program_key(programs, lookup, target)
        if resolved is None:
            continue
        program = programs[resolved]
        pending.extend((reference, resolved) for reference in iter_moduletype_refs(program.code.submodules))
        for moduletype in program.code.moduletype_defs:
            pending.extend((reference, resolved) for reference in iter_moduletype_refs(moduletype.submodules))

    reachable: dict[str, set[str]] = {}
    seen: set[tuple[str, str]] = set()
    while pending:
        name, requester = pending.popleft()
        folded = fold_identifier(name)
        if (folded, requester) in seen:
            continue
        seen.add((folded, requester))
        for key, moduletype in _resolve_moduletype(folded, requester, index, closures):
            reachable.setdefault(key, set()).add(fold_identifier(moduletype.name))
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
