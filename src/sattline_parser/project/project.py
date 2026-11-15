"""SattLineProject: the loaded, resolved view of a SattLine artifact set.

``load`` walks the whole tree: file discovery, recursive dependency resolution,
and ``.g`` / ``.y`` graphics companion parsing through the project loader. The
public ``from_programs`` builder covers tests and consumers that already hold
parsed programs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from ._cycles import dependency_cycles
from .index import ProjectIndex
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
        self._index: ProjectIndex | None = None

    @classmethod
    def from_programs(cls, programs: Mapping[str, SattLineProgram]) -> SattLineProject:
        """Build a project directly from a name-to-program mapping.

        For a consumer that already holds parsed programs, or a test that wants
        to exercise the graph views without a filesystem. Each mapping key must
        be the program's own name, compared case-insensitively, because the
        project keys programs by folded name. A key that disagrees with
        ``program.name``, or two keys that fold together, raise ``ValueError``.
        Unlike ``load``, this path does not reject a cycle, which is what makes
        ``cycles`` useful.
        """
        project = cls()
        registry: dict[str, SattLineProgram] = {}
        for key, program in programs.items():
            canonical = key.casefold()
            if canonical != program.name.casefold():
                raise ValueError(f"mapping key {key!r} does not match program name {program.name!r}")
            if canonical in registry:
                raise ValueError(f"two mapping keys fold to {canonical!r}")
            registry[canonical] = program
        project._programs = registry
        return project

    @classmethod
    def load(
        cls,
        roots: Sequence[Path],
        mode: LoadMode,
        targets: Sequence[str],
        *,
        debug: Callable[[str], None] | None = None,
        cache_dir: Path | None = None,
        validate: LoadValidation = LoadValidation.INVOKED,
        workers: int = 1,
    ) -> SattLineProject:
        """Load a project from ``roots`` plus ``targets``.

        ``validate`` defaults to :attr:`LoadValidation.INVOKED`: each target is
        validated in full, while a dependency file contributes only the module
        types the target invokes.

        Each target is resolved through ``roots`` in the caller's order, its
        ``.l`` / ``.z`` dependency file (when present) is read, and dependencies
        are loaded recursively before the target itself. Earlier roots win: when
        two roots hold a same-named unit, the body in the earlier root is the
        one loaded, and the later body is never planned, parsed, or validated.
        When a code file has a ``.g`` / ``.y`` sibling, the companion is parsed
        into the program's graphics model. Programs are canonicalized by
        casefolded identity, so one name resolves to one body and each body is
        visited and parsed once. A missing or unparseable artifact fails the
        whole load, so a project is either complete or not returned. A recursive
        sidecar chain or a module type that instantiates itself is a structural
        error too.

        ``validate=INVOKED`` (default) validates each target in full while a
        dependency file contributes only the module types the target invokes,
        transitively. ``validate=FULL`` runs the single-file validator over
        every loaded program. ``validate=NONE`` parses only.

        ``cache_dir`` optionally enables the parser-owned lookup and AST caches
        so repeated loads skip re-discovery and re-parsing. When ``None`` the
        load is fully in-memory and hermetic.

        ``workers`` parses program bodies in that many processes. Discovery
        resolves every artifact first, so the closure is complete before any
        parse starts and the result is identical at any worker count; only the
        time changes. ``1`` keeps the load in the calling process.
        """
        loader = ProjectLoader(
            roots=roots,
            mode=mode,
            debug=debug,
            cache_dir=cache_dir,
            validate=validate,
            workers=workers,
        )
        program_registry = loader.resolve(targets)
        project = cls()
        project._programs = program_registry
        project._diagnostics = loader.diagnostics
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
        """Non-fatal load findings, in discovery then assembly order.

        Missing, empty, stray, and family-mismatched sidecars and a folded name
        that resolved to two bodies are conditions the loader reports and an
        operator may continue past. They are surfaced rather than raised,
        because a missing *body* is a load failure and a sidecar is not.
        """
        return self._diagnostics

    def cycles(self) -> tuple[tuple[str, ...], ...]:
        """Every dependency cycle in the declared graph, canonical and sorted.

        Each path starts at its smallest node name and ends at the same name,
        for example ``("alpha", "beta", "alpha")``. A loaded project has no
        cycles because the loader rejects them, so this view is only non-empty
        for a project built directly from programs. It stays available for
        consumers that inspect a hand-built graph or a stored edge set.
        """
        return dependency_cycles(self.graph().edges)

    def libraries(self) -> tuple[str, ...]:
        """Library names that resolved at least one loaded program, sorted."""
        return tuple(sorted({program.library for program in self._programs.values() if program.library is not None}))

    def dependencies_of(self, name: str) -> tuple[str, ...]:
        """Declared dependencies (as spelled) of ``name``, in declaration order."""
        return self.get(name).dependencies

    def dependents_of(self, name: str) -> tuple[str, ...]:
        """Loaded programs declaring ``name`` as a dependency, in load order.

        Like :meth:`dependencies_of`, the answer is spelled the way each
        dependent declared itself, so a caller can pass a returned name back to
        :meth:`get` and read the same program's ``name``.
        """
        key = name.casefold()
        return tuple(
            program.name
            for program in self._programs.values()
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

    @property
    def index(self) -> ProjectIndex:
        """Definitions and uses across the loaded units, built once.

        The index is derived from the parsed trees and cached for the lifetime
        of the project. Use :meth:`ProjectIndex.definitions_of` to answer "who
        defines X" and :meth:`ProjectIndex.usages_of` to answer "who uses Y".
        Both compare names the way the language does, case-insensitively.
        """
        if self._index is None:
            self._index = ProjectIndex(self._programs)
        return self._index


__all__ = ["SattLineProject"]
