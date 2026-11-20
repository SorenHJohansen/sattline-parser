"""SattLineProject: the loaded, resolved view of a SattLine artifact set.

``load`` walks the whole tree: file discovery, recursive dependency resolution,
and ``.g`` / ``.y`` graphics companion parsing through the project loader. The
public ``from_programs`` builder covers tests and consumers that already hold
parsed programs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import cast

from sattline_parser.models.ast_model import BasePicture
from sattline_parser.models.freeze import copy_frozen_ast, freeze_ast

from ._cycles import dependency_cycles
from .identity import UnitIdentity
from .index import ProjectIndex
from .loader import ProjectLoader
from .models import DependencyGraph, LoadDiagnostic, LoadMode, LoadValidation, SattLineProgram


class SattLineProject:
    """Owns the resolved program registry and the derived dependency graph.

    Program names use canonical (casefolded) identities internally, giving
    case-insensitive lookup while preserving the caller's original spelling in
    each ``SattLineProgram.name``. A casefolded key is only a view key, and a
    name the language keeps apart from the stored spelling, such as ``STRASSE``
    beside ``Straße``, is not resolved by it: each unit is resolved by its own
    language identity. When two loaded units share one casefold key, the key
    names no single unit and both are keyed by their language identities, so both
    stay addressable and neither answers for the other.
    """

    def __init__(self) -> None:
        self._programs: dict[str, SattLineProgram] = {}
        #: Folded language identity of every spelling that reached a loaded unit
        #: -> that unit's view key.
        self._identity_views: dict[str, str] = {}
        self._diagnostics: tuple[LoadDiagnostic, ...] = ()
        self._index: ProjectIndex | None = None

    def _attach(
        self,
        programs: Mapping[str, SattLineProgram],
        *,
        copy_ast: bool,
        identity_views: Mapping[str, str] | None = None,
    ) -> None:
        """Install the registry as an immutable snapshot.

        ``load`` owns the trees the loader produced, so it freezes them in
        place. ``from_programs`` receives trees the caller still owns, so it
        copies first. The copy is built and frozen in one iterative pass, so a
        tree at the depth the parser accepts is copied without growing the
        Python call stack.
        """
        registry: dict[str, SattLineProgram] = {}
        for key, program in programs.items():
            code = copy_frozen_ast(program.code) if copy_ast else freeze_ast(program.code)
            registry[key] = replace(program, code=cast(BasePicture, code))
        self._programs = registry
        self._identity_views = {UnitIdentity.of(program.name).key: key for key, program in registry.items()}
        for identity, view in (identity_views or {}).items():
            self._identity_views.setdefault(identity, view)

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
        project._attach(registry, copy_ast=True)
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

        Every scope checks type-reference bindings in all loaded files.
        ``validate`` defaults to :attr:`LoadValidation.INVOKED`: additional
        checks cover each target and the dependency module types it invokes.

        Each target is resolved through ``roots`` in the caller's order, its
        ``.l`` / ``.z`` dependency file (when present) is read, and the whole
        dependency closure is planned before the target itself is loaded. The
        path holds one library per name: a root whose directory name repeats an
        earlier root is shadowed and never searched, so a unit only it holds is
        not found. When two effective roots hold a same-named unit, the body in
        the earlier root is the one loaded, and the later body is never planned,
        parsed, or validated. When a code file has a ``.g`` / ``.y`` sibling,
        the companion is parsed into the program's graphics model. A name resolves to a body
        only when it matches under the language name table, so one name reaches
        one body and each body is visited and parsed once; every spelling that
        reached a body stays a name for it. A missing or unparseable artifact
        fails the whole load, so a project is either complete or not returned. A
        recursive sidecar chain or a module type that instantiates itself is a
        structural error too.

        ``validate=INVOKED`` (default) validates each target in full while a
        dependency file contributes only the module types the target invokes,
        transitively, beyond the always-on type-reference checks.
        ``validate=FULL`` validates every loaded program. ``validate=NONE``
        runs only type-reference binding checks.

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
        project._attach(program_registry, copy_ast=False, identity_views=loader.identity_views)
        project._diagnostics = loader.diagnostics
        return project

    def _resolve_view(self, name: str) -> str | None:
        """The view key *name* designates, or ``None``.

        A view key round-trips even when its spelling is not the unit's language
        name (``strasse`` for ``Straße``), so the caller's spelling is compared
        as written with the stored view key first. Any other name must match a
        loaded unit's spelling under :func:`~sattline_parser.names.fold_identifier`.
        A casefold-only name such as ``STRASSE`` beside ``Straße`` therefore
        designates neither through the casefold key nor through the identity
        table unless that unit loaded, and two language-distinct units that share
        a casefold key stay reachable through their own identities.
        """
        key = name.casefold()
        program = self._programs.get(key)
        if program is not None and (name == key or UnitIdentity.of(program.name) == UnitIdentity.of(name)):
            return key
        return self._identity_views.get(UnitIdentity.of(name).key)

    def _resolve(self, name: str) -> SattLineProgram | None:
        """The loaded unit *name* designates, or ``None``."""
        view = self._resolve_view(name)
        return None if view is None else self._programs[view]

    def _view_key(self, name: str) -> str:
        """The view key *name* designates, or its folded spelling when unknown.

        Used for graph edges: a declared dependency that resolved to a loaded
        unit points at that unit's own view key, so every endpoint of a loaded
        project is also a node and a unit that lost a casefold collision is not
        replaced by the unit that won it.
        """
        view = self._resolve_view(name)
        return view if view is not None else name.casefold()

    def get(self, name: str) -> SattLineProgram:
        """Return the loaded program by name (case-insensitive).

        Case-insensitivity is the language's own rule, so ``util``, ``Util``,
        and ``UTIL`` all designate one unit while ``STRASSE`` does not designate
        ``Straße``. A name that matches a loaded unit under ``fold_identifier``
        designates that unit, including a unit keyed by its language identity
        because the shared casefold key names no single unit. Raises ``KeyError``
        when the project holds no such unit.
        """
        program = self._resolve(name)
        if program is None:
            raise KeyError(f"no loaded program {name!r} in this project")
        return program

    def __contains__(self, name: str) -> bool:
        return self._resolve(name) is not None

    def programs(self) -> Mapping[str, SattLineProgram]:
        """Read-only canonical view over the loaded programs.

        Keys are the casefolded unit name, which is the view key every ordinary
        ASCII name has always had. When two loaded units share one casefold key,
        it names no single unit: every unit in that group is keyed by its
        language identity instead, so the mapping holds every loaded unit once
        and a dependency on either one still round-trips through :meth:`get`.
        """
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
        """Declared dependencies (as spelled) of ``name``, in declaration order.

        Every returned name designates a loaded unit in a project that came from
        :meth:`load`, so a caller can pass each one back to :meth:`get`. That
        includes a unit in a shared casefold group: it is reachable under its own
        language identity because the shared key names no single unit.
        """
        return self.get(name).dependencies

    def _unit_key(self, name: str) -> str:
        """The language identity of the unit *name* designates.

        The argument is resolved through :meth:`_resolve_view` first, so a
        ``programs()`` view key or a loaded spelling compares as the unit it
        names rather than as its own spelling. A name that designates no unit
        keeps its own identity, which is what lets a project built with
        ``from_programs`` compare a declared dependency it does not hold.
        """
        program = self._resolve(name)
        return UnitIdentity.of(program.name if program is not None else name).key

    def dependents_of(self, name: str) -> tuple[str, ...]:
        """Loaded programs declaring ``name`` as a dependency, in load order.

        The argument is resolved first, so a view key or an alias designates the
        unit it names. Like :meth:`dependencies_of`, the answer is spelled the
        way each dependent declared itself, so a caller can pass a returned name
        back to :meth:`get` and read the same program's ``name``.
        """
        target = self._unit_key(name)
        return tuple(
            program.name
            for program in self._programs.values()
            if any(self._unit_key(dependency) == target for dependency in program.dependencies)
        )

    def graph(self) -> DependencyGraph:
        """Derived dependency graph: sorted nodes, all declared edges.

        Edge endpoints are view keys. A declared dependency that resolved to a
        loaded unit points at that unit's own view key, including when the
        dependency used an alias or when its unit belongs to a shared casefold
        group keyed by language identity, so every endpoint of a loaded project
        is also a node and no edge is retargeted at a same-key unit. A project
        assembled directly with ``from_programs`` may declare an edge to a program
        it does not hold; that edge keeps the declared spelling's view key and
        names no node.
        """
        edges = tuple(
            (owner, self._view_key(dependency))
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
