"""SattLineProject: the loaded, resolved view of a SattLine artifact set.

Phases 3-4 wire ``load`` end to end: file discovery, recursive dependency
resolution, and ``.g`` / ``.y`` graphics companion parsing via the project
loader. The phase-1 internal ``_from_programs`` builder remains for tests and
schema-only construction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from .loader import ProjectLoader
from .models import DependencyGraph, LoadMode, SattLineProgram


class SattLineProject:
    """Owns the resolved program registry and the derived dependency graph.

    Program names use canonical (casefolded) identities internally, giving
    case-insensitive lookup while preserving the caller's original spelling in
    each ``SattLineProgram.name``.
    """

    def __init__(self) -> None:
        self._programs: dict[str, SattLineProgram] = {}

    @classmethod
    def _from_programs(cls, programs: Mapping[str, SattLineProgram]) -> SattLineProject:
        """Build a project directly from a name-to-program mapping.

        Schema-only seam for tests and consumers that already hold resolved
        programs. Names are casefolded into canonical keys.
        """
        project = cls()
        project._programs = {name.casefold(): program for name, program in programs.items()}
        return project

    @classmethod
    def load(
        cls,
        roots: Sequence[Path],
        mode: LoadMode,
        targets: Sequence[str],
        *,
        strict: bool = True,
        debug: Callable[[str], None] | None = None,
        cache_dir: Path | None = None,
    ) -> SattLineProject:
        """Load a project from ``roots`` plus ``targets`` (Phases 3-4).

        Each target is resolved across the ordered roots, its ``.l`` / ``.z``
        dependency file (when present) is read, and dependencies are loaded
        recursively before the target itself. When a code file has a ``.g`` /
        ``.y`` sibling, the companion is parsed into the program's graphics
        model. Programs are canonicalized by casefolded identity: each name is
        visited and parsed exactly once, and cycles resolve as edges in the
        derived graph. ``strict=True`` (default) fails fast on missing or
        unparseable artifacts; ``strict=False`` skips the failing program and
        continues.

        ``cache_dir`` optionally enables the parser-owned lookup and AST caches
        so repeated loads skip re-discovery and re-parsing. When ``None`` the
        load is fully in-memory and hermetic.
        """
        program_registry = ProjectLoader(
            roots=roots, mode=mode, strict=strict, debug=debug, cache_dir=cache_dir
        ).resolve(targets)
        project = cls()
        project._programs = program_registry
        return project

    def get(self, name: str) -> SattLineProgram:
        """Return the loaded program by name (case-insensitive).

        Raises ``KeyError`` when the program is not part of this project.
        """
        try:
            return self._programs[name.casefold()]
        except KeyError:
            raise KeyError(f"no loaded program {name!r} in this project") from None

    def __contains__(self, name: str) -> bool:
        return name.casefold() in self._programs

    def programs(self) -> Mapping[str, SattLineProgram]:
        """Read-only canonical view over the loaded programs."""
        return MappingProxyType(self._programs)

    def dependencies_of(self, name: str) -> tuple[str, ...]:
        """Declared dependencies (as spelled) of ``name``, in declaration order."""
        return self.get(name).dependencies

    def dependents_of(self, name: str) -> tuple[str, ...]:
        """Loaded programs declaring ``name`` as a dependency, in load order."""
        key = name.casefold()
        return tuple(
            owner
            for owner, program in self._programs.items()
            if key in (dependency.casefold() for dependency in program.dependencies)
        )

    def graph(self) -> DependencyGraph:
        """Derived dependency graph: sorted nodes, all declared edges.

        Edge endpoints are canonical (casefolded) identities; edges may reference
        dependency names that are not themselves nodes until full resolution.
        """
        edges = tuple(
            (owner, dependency.casefold())
            for owner, program in self._programs.items()
            for dependency in program.dependencies
        )
        return DependencyGraph(nodes=tuple(sorted(self._programs)), edges=edges)


__all__ = ["SattLineProject"]
