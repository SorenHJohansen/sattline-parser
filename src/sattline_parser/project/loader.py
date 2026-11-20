"""Recursive project resolution: the orchestrator over four load phases.

A load has four phases with different failure modes, and each lives in its own
module:

:mod:`~sattline_parser.project.planner`
    Resolve names to artifacts and dependencies into post-order plans. No
    parsing, no registry.
:mod:`~sattline_parser.project.executor`
    Parse the planned bodies, in this process or in a worker pool. Owns the AST
    cache and the picklable failure record.
:mod:`~sattline_parser.project.assembler`
    Turn a parsed body into a ``SattLineProgram``: origin, diagnostics,
    companions, registry entry.
:mod:`~sattline_parser.project.scope`
    Validation scope and diagnostic aggregation over the assembled registry.

``ProjectLoader`` wires them together, owns the non-fatal load diagnostics and
the two caches, and runs the three cross-phase invariants: registry post-order,
module-type recursion, and validation. A load is all or nothing: a missing or
unparseable artifact raises, and the two structural errors (a recursive sidecar
chain and a self-instantiating module type) are fatal in the same way.

A ``ProjectLoader`` resolves one load. Discovery plans, parse outcomes, and the
registry are per-load state, so a second ``resolve()`` call raises rather than
doubling the plans over an existing registry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from sattline_parser.source_io import private_cache_dir

from . import parallel as _parallel
from .assembler import ProjectAssembler
from .ast_cache import FileASTCache
from .discovery import ProjectLookup, ordered_lookup_bases
from .errors import ProjectLoadError
from .executor import ParseExecutor
from .formats import CompanionIndex
from .identity import UnitIdentity
from .lookup_cache import FileLookupCache
from .models import (
    LoadDiagnostic,
    LoadDiagnosticKind,
    LoadMode,
    LoadValidation,
    SattLineProgram,
)
from .planner import ProjectPlanner, read_dependency_names
from .scope import ProjectValidator

__all__ = ["ProjectLoader", "read_dependency_names"]


class ProjectLoader:
    """Orchestrate one load: plan, parse, assemble, validate."""

    def __init__(
        self,
        *,
        roots: Sequence[Path],
        mode: LoadMode,
        debug: Callable[[str], None] | None,
        cache_dir: Path | None,
        validate: LoadValidation = LoadValidation.INVOKED,
        workers: int = 1,
    ) -> None:
        # The whole cache root has to be private: the AST cache stores pickles,
        # and the lookup cache shares the same directory. Fail closed by
        # disabling both caches when the directory is not ours.
        secure_cache_dir = private_cache_dir(cache_dir) if cache_dir is not None else None
        self._lookup_cache = FileLookupCache(secure_cache_dir) if secure_cache_dir is not None else None
        self._ast_cache = FileASTCache(secure_cache_dir) if secure_cache_dir is not None else None
        _assert_roots_are_directories(roots)
        lookup = ProjectLookup(roots, mode, cache=self._lookup_cache, debug=debug)
        #: The parser logs a failure with its traceback. A plain load reports the
        #: problem once as a structured finding, so only a debug run asks for the
        #: parser's own log line and stack.
        log_failures = debug is not None
        self._validate = validate
        self._resolved = False
        #: Non-fatal load findings, and the set that keeps them unique.
        self._diagnostics: list[LoadDiagnostic] = []
        self._diagnostic_set: set[LoadDiagnostic] = set()
        #: Extra spellings that reached a loaded unit: the spelling's folded
        #: language identity -> the project view key of the unit it reached. One
        #: body can be named twice, for example through a symlink, and every
        #: spelling a sidecar used must resolve back to the unit it named.
        self._identity_views: dict[str, str] = {}
        #: One lazy companion directory index for this load. The planner's
        #: sidecar probe and the assembler's graphics and distribution roles
        #: share it, so a directory is listed once per load.
        self._companions = CompanionIndex(diagnose=self._diagnose)
        #: Whether this loader was constructed while another load was resolving.
        #: A nested load parses in this process rather than starting a second pool.
        self._nested = _parallel.loads_in_progress() > 0

        self._planner = ProjectPlanner(
            lookup=lookup,
            mode=mode,
            debug=debug,
            diagnose=self._diagnose,
            companions=self._companions,
        )
        #: Plan key -> the assembled unit. The public view keeps one unit per
        #: folded name; this registry keeps every resolved body.
        self._registry: dict[str, SattLineProgram] = {}
        self._validator = ProjectValidator(
            validate=validate,
            registry=self._registry,
            resolved_dependencies=self._planner.resolved_dependencies,
            target_plan_keys=self._planner.target_plan_keys,
        )
        self._assembler = ProjectAssembler(
            mode=mode,
            registry=self._registry,
            validator=self._validator,
            debug=debug,
            companions=self._companions,
            diagnose=self._diagnose,
        )
        self._executor = ParseExecutor(
            mode=mode,
            workers=workers,
            log_failures=log_failures,
            debug=debug,
            ast_cache=self._ast_cache,
            secure_cache_dir=secure_cache_dir,
            pool_factory=_parallel.process_pool,
            nested=self._nested,
        )

    @property
    def diagnostics(self) -> tuple[LoadDiagnostic, ...]:
        """Non-fatal load findings, in discovery then assembly order."""
        return tuple(self._diagnostics)

    @property
    def identity_views(self) -> Mapping[str, str]:
        """Every spelling that reached a loaded unit, as identity -> view key.

        Keys are the spelling's folded language identity, values are the project
        view key of the unit it reached. The mapping is filled by
        :meth:`resolve`.
        """
        return self._identity_views

    def _diagnose(self, kind: LoadDiagnosticKind, program: str, detail: str, path: Path | None = None) -> None:
        diagnostic = LoadDiagnostic(kind=kind, program=program, detail=detail, path=path)
        if diagnostic in self._diagnostic_set:
            return
        self._diagnostics.append(diagnostic)
        self._diagnostic_set.add(diagnostic)

    def resolve(self, targets: Sequence[str]) -> dict[str, SattLineProgram]:
        """Load every target and its dependencies; return the folded registry."""
        if self._resolved:
            raise RuntimeError("this ProjectLoader has already resolved a load; construct another loader")
        self._resolved = True
        try:
            with _parallel.load_in_progress():
                self._planner.resolve(targets)
                outcomes = self._executor.parse(self._planner.plans)
                self._assembler.assemble(self._planner.plans, outcomes=outcomes)
                self._assert_registry_post_order()
                self._validator.assert_no_moduletype_cycles()
                if self._validate is LoadValidation.INVOKED:
                    self._validator.validate_invoked()
                programs, view_of_plan = self._name_registry()
                self._identity_views = self._identity_view_registry(view_of_plan)
                return programs
        finally:
            if self._lookup_cache is not None:
                self._lookup_cache.flush()

    def _name_registry(self) -> tuple[dict[str, SattLineProgram], dict[str, str]]:
        """The public registry and the view key of every plan.

        One unit per ``str.casefold`` key. The key is the project view's own
        canonical spelling, and ``SattLineProject`` looks up by the same rule.

        Two units can share that key even though the language keeps them apart,
        for example ``Straße`` and ``STRASSE``. The casefold key then names no
        single unit, so every unit in that group is keyed by its language
        identity (:func:`~sattline_parser.names.fold_identifier`) instead. That
        identity is unique among the loaded units, so both stay addressable and a
        declared dependency on either one round-trips through ``get``. The
        planner has already reported the pair as a folded-name collision.
        """
        shared: dict[str, int] = {}
        for program in self._registry.values():
            key = program.name.casefold()
            shared[key] = shared.get(key, 0) + 1
        registry: dict[str, SattLineProgram] = {}
        view_of_plan: dict[str, str] = {}
        for plan_key, program in self._registry.items():
            view = program.name.casefold()
            if shared[view] > 1:
                view = UnitIdentity.of(program.name).key
            registry[view] = program
            view_of_plan[plan_key] = view
        return registry, view_of_plan

    def _identity_view_registry(self, view_of_plan: Mapping[str, str]) -> dict[str, str]:
        """Every spelling that reached a unit in the view, as identity -> view.

        A sidecar may name one body twice, for example directly and through a
        symlink. The body is planned once, so the second spelling would otherwise
        disappear and ``dependencies_of`` could return a name ``get`` cannot
        resolve. The unit's own name is registered from the registry, so a unit
        in a shared casefold group is reachable under its language identity.
        """
        views: dict[str, str] = {}
        for plan_key, program in self._registry.items():
            views.setdefault(UnitIdentity.of(program.name).key, view_of_plan[plan_key])
        for spelling, plan_key in self._planner.resolved_names.values():
            views.setdefault(UnitIdentity.of(spelling).key, view_of_plan[plan_key])
        return views

    def _assert_registry_post_order(self) -> None:
        """Assert that every loaded dependency precedes its consumer."""
        seen: set[str] = set()
        for key, program in self._registry.items():
            for dependency_key in self._planner.resolved_dependencies.get(key, ()):
                if dependency_key in self._registry and dependency_key not in seen:
                    dependency_name = self._registry[dependency_key].name
                    raise RuntimeError(
                        f"loader registry is not in post-order: {program.name!r} precedes dependency {dependency_name!r}"
                    )
            seen.add(key)


def _assert_roots_are_directories(roots: Sequence[Path]) -> None:
    """Reject a configured root that is not a readable directory.

    A root that is a regular file, missing, or under a denied ancestor is an
    input problem about that root, not an empty root: ``Path.is_dir`` answers
    ``False`` for all three, so the message names the root and the failure
    happens before any target is resolved. Checking the effective roots keeps a
    shadowed root, which is not on the loading path, out of the question.
    """
    for root in ordered_lookup_bases(roots):
        try:
            is_directory = root.is_dir()
        except OSError as exc:
            # A denied ancestor makes stat fail; that is the same input problem
            # as a root that is not a directory, so name the root either way.
            raise ProjectLoadError(
                root.name or str(root),
                f"root is not a readable directory: {root} ({exc.strerror or exc})",
            ) from exc
        if is_directory:
            continue
        raise ProjectLoadError(
            root.name or str(root),
            f"root is not a readable directory: {root}",
        )
