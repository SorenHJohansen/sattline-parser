"""Invoked-module reachability across a loaded project.

A program file can define many module types; a library file usually defines far
more than any one consumer invokes. Validation for an invoked scope starts at
the selected program's own module tree, follows every ``ModuleTypeInstance``
reference into the loaded definitions, and continues through the submodules of
those definitions. Only the module types reached this way are validated.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping

from sattline_parser.models.ast_model import (
    BasePicture,
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
    codes: dict[str, BasePicture] = {}
    for key, program in programs.items():
        code = program.code
        codes[key] = code
        for moduletype in code.moduletype_defs:
            index.setdefault(moduletype.name.casefold(), []).append((key, moduletype))

    pending: deque[str] = deque()
    for target in targets:
        code = codes.get(target.casefold())
        if code is None:
            continue
        pending.extend(iter_moduletype_refs(code.submodules))
        for moduletype in code.moduletype_defs:
            pending.extend(iter_moduletype_refs(moduletype.submodules))

    reachable: dict[str, set[str]] = {}
    seen: set[str] = set()
    while pending:
        name = pending.popleft().casefold()
        if name in seen:
            continue
        seen.add(name)
        for key, moduletype in index.get(name, ()):
            reachable.setdefault(key, set()).add(moduletype.name.casefold())
            pending.extend(iter_moduletype_refs(moduletype.submodules))
    return reachable


__all__ = ["invoked_moduletypes", "iter_moduletype_refs"]
