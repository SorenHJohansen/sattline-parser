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
from .models import DependencyGraph, LoadDiagnostic, LoadMode, LoadValidation, SattLineProgram


class SattLineProject:
    """Owns the resolved program registry and the derived dependency graph.

    Program names use canonical (casefolded) identities internally, giving
    case-insensitive lookup while preserving the caller's original spelling in
    each ``SattLineProgram.name``.
    """

    def __init__(self) -> None:
        self._programs: dict[str, SattLineProgram] = {}
        self._diagnostics: tuple[LoadDiagnostic, ...] = ()
        self._cycles: tuple[tuple[str, ...], ...] = ()

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
        validate: LoadValidation = LoadValidation.FULL,
    ) -> SattLineProject:
        """Load a project from ``roots`` plus ``targets``.

        Each target is resolved across the ordered roots, its ``.l`` / ``.z``
        dependency file (when present) is read, and dependencies are loaded
        recursively before the target itself. When a code file has a ``.g`` /
        ``.y`` sibling, the companion is parsed into the program's graphics
        model. Programs are canonicalized by casefolded identity: each name is
        visited and parsed exactly once, and cycles resolve as edges in the
        derived graph. ``strict=True`` (default) fails fast on missing or
        unparseable artifacts; ``strict=False`` skips the failing program and
        continues.

        ``validate=FULL`` (default) runs the single-file validator per program
        with the definitions visible from already-loaded dependencies and stores
        the findings on each program. ``validate=NONE`` parses only.

        ``cache_dir`` optionally enables the parser-owned lookup and AST caches
        so repeated loads skip re-discovery and re-parsing. When ``None`` the
        load is fully in-memory and hermetic.
        """
        loader = ProjectLoader(
            roots=roots,
            mode=mode,
            strict=strict,
            debug=debug,
            cache_dir=cache_dir,
            validate=validate,
        )
        program_registry = loader.resolve(targets)
        project = cls()
        project._programs = program_registry
        project._diagnostics = loader.diagnostics
        project._cycles = loader.cycles
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

    def diagnostics(self) -> tuple[LoadDiagnostic, ...]:
        """Non-fatal load findings (missing/empty sidecars, cycles, stray sidecars).

        These are conditions the loader reports and an operator may
        continue past; they are surfaced rather than raised so the default
        ``strict=True`` contract (missing *bodies* fail) is unchanged.
        """
        return self._diagnostics

    def cycles(self) -> tuple[tuple[str, ...], ...]:
        """Dependency cycle paths recorded during the load, in discovery order.

        Each path starts at the dependency that closed the loop and ends at the
        same name, for example ``("alpha", "beta", "alpha")``. The loader also
        records a ``dependency-cycle`` load diagnostic; this view is the data
        form consumers can render or compare. A project built directly from
        programs rather than loaded computes the paths from its edges.
        """
        if self._cycles:
            return self._cycles
        return _dependency_cycles(self.graph().edges)

    def libraries(self) -> tuple[str, ...]:
        """Library names that resolved at least one loaded program, sorted."""
        return tuple(sorted({program.library for program in self._programs.values() if program.library is not None}))

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


def _dependency_cycles(edges: tuple[tuple[str, str], ...]) -> tuple[tuple[str, ...], ...]:
    """Cycle paths computed from dependency edges (fallback for direct construction)."""
    adjacency: dict[str, list[str]] = {}
    for dependent, dependency in edges:
        adjacency.setdefault(dependent, []).append(dependency)

    found: list[tuple[str, ...]] = []
    seen: set[frozenset[str]] = set()
    explored: set[str] = set()

    def walk(node: str, trail: tuple[str, ...], on_trail: frozenset[str]) -> None:
        for neighbour in adjacency.get(node, ()):
            if neighbour in on_trail:
                cycle = (*trail[trail.index(neighbour) :], neighbour)
                key = frozenset(cycle)
                if key not in seen:
                    seen.add(key)
                    found.append(cycle)
            elif neighbour not in explored:
                walk(neighbour, (*trail, neighbour), on_trail | {neighbour})
        explored.add(node)

    for start in adjacency:
        if start not in explored:
            walk(start, (start,), frozenset({start}))
    return tuple(found)


__all__ = ["SattLineProject"]
