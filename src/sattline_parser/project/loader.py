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
module-type recursion, and validation. ``resolve`` is all or nothing: a missing
or unparseable artifact raises, and the two structural errors (a recursive
sidecar chain and a self-instantiating module type) are fatal in the same way.
``resolve_many`` shares the planning and parse pass, then reports each target's
failure separately so healthy targets still load.

A ``ProjectLoader`` resolves one load. Discovery plans, parse outcomes, and the
registry are per-load state, so a second ``resolve()`` call raises rather than
doubling the plans over an existing registry. Construct another loader.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
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
    CacheDisabledReason,
    CacheInfo,
    LoadDiagnostic,
    LoadDiagnosticKind,
    LoadMode,
    LoadValidation,
    SattLineProgram,
)
from .planner import ProjectPlanner, read_dependency_names
from .scope import ProjectValidator

__all__ = ["LoadedTarget", "ProjectLoader", "read_dependency_names"]


@dataclass(frozen=True, slots=True)
class LoadedTarget:
    """One successful target produced by :meth:`ProjectLoader.resolve_many`.

    The loader hands back the registry slice, the alias table, the scoped
    diagnostics, and the cache snapshot. ``SattLineProject`` turns it into the
    public result, so the loader never imports the project class.
    """

    programs: Mapping[str, SattLineProgram]
    identity_views: Mapping[str, str]
    diagnostics: tuple[LoadDiagnostic, ...]
    cache_info: CacheInfo


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
        defer_validation: bool = False,
    ) -> None:
        # The whole cache root has to be private: the AST cache stores pickles,
        # and the lookup cache shares the same directory. Fail closed by
        # disabling both caches when the directory is not ours.
        secure_cache_dir = private_cache_dir(cache_dir) if cache_dir is not None else None
        self._cache_dir = cache_dir
        self._secure_cache_dir = secure_cache_dir
        self._defer_validation = defer_validation
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
        #: A batch load defers target-scoped validation until it has split the
        #: registry into per-target closures, so assembly computes only the
        #: always-on type-reference diagnostics.
        self._assembly_validator = (
            ProjectValidator(
                validate=LoadValidation.NONE,
                registry=self._registry,
                resolved_dependencies=self._planner.resolved_dependencies,
                target_plan_keys=set(),
            )
            if defer_validation
            else self._validator
        )
        self._assembler = ProjectAssembler(
            mode=mode,
            registry=self._registry,
            validator=self._assembly_validator,
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

    @property
    def cache_info(self) -> CacheInfo:
        """The cache configuration and the work this load did against it."""
        lookup_enabled = self._lookup_cache is not None and self._lookup_cache.enabled
        ast_enabled = self._ast_cache is not None and self._ast_cache.enabled
        enabled = lookup_enabled and ast_enabled
        reason: CacheDisabledReason | None = None
        if not enabled:
            reason = self._disabled_cache_reason()
        lookup_hits = self._lookup_cache.hits if self._lookup_cache is not None else 0
        lookup_misses = self._lookup_cache.misses if self._lookup_cache is not None else 0
        return CacheInfo(
            enabled=enabled,
            disabled_reason=reason,
            ast_hits=self._executor.ast_hits,
            ast_misses=self._executor.ast_misses,
            lookup_hits=lookup_hits,
            lookup_misses=lookup_misses,
        )

    def _disabled_cache_reason(self) -> CacheDisabledReason:
        """Why the caches are off, as far as the loader can tell.

        No configured directory is intentional. A directory that exists but
        failed the privacy proof is a privacy refusal. A missing directory that
        could not be created, or a cache handle disabled after construction, is
        unavailable.
        """
        if self._cache_dir is None:
            return CacheDisabledReason.NOT_CONFIGURED
        if self._secure_cache_dir is None:
            return CacheDisabledReason.PRIVACY if self._cache_dir.is_dir() else CacheDisabledReason.UNAVAILABLE
        return CacheDisabledReason.UNAVAILABLE

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
        if self._defer_validation:
            raise RuntimeError("this ProjectLoader defers validation; use resolve_many for a batch load")
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
                programs, view_of_plan = self._name_registry(self._registry)
                self._identity_views = self._identity_view_registry(self._registry, view_of_plan)
                return programs
        finally:
            if self._lookup_cache is not None:
                self._lookup_cache.flush()

    def resolve_many(self, targets: Sequence[str]) -> tuple[dict[str, LoadedTarget], dict[str, ProjectLoadError]]:
        """Load targets independently while sharing every closure that succeeds.

        Discovery and parsing run once for the union of the targets. A target
        whose own closure contains a failed artifact reports that error and is
        left out of the successful results. The registry, parse outcomes, and
        cache work of the healthy targets are shared, so a dependency common to
        several targets is planned and parsed once.

        Each successful target carries a registry slice over its own closure
        only, with scoped validation applied against that target alone, so
        another target's findings cannot leak into its diagnostics.
        """
        if self._resolved:
            raise RuntimeError("this ProjectLoader has already resolved a load; construct another loader")
        if not self._defer_validation:
            raise RuntimeError("resolve_many requires a loader constructed with defer_validation=True")
        self._resolved = True
        loaded: dict[str, LoadedTarget] = {}
        failures: dict[str, ProjectLoadError] = {}
        try:
            with _parallel.load_in_progress():
                successes, planning_failures = self._planner.resolve_many(targets)
                failures.update(planning_failures)
                outcomes = self._executor.parse(self._planner.plans)
                assembly_failures = self._assembler.assemble_collecting(self._planner.plans, outcomes=outcomes)
                self._assert_registry_post_order()
                for target, target_key in successes.items():
                    closure = self._closure(target_key)
                    failure = self._first_closure_failure(closure, assembly_failures)
                    if failure is not None:
                        failures[target] = failure
                        continue
                    success = self._target_loaded(target_key, closure)
                    if isinstance(success, ProjectLoadError):
                        failures[target] = success
                    else:
                        loaded[target] = success
                return loaded, failures
        finally:
            if self._lookup_cache is not None:
                self._lookup_cache.flush()

    def _closure(self, key: str) -> frozenset[str]:
        """Plan keys of *key* and every unit it reaches through resolved deps."""
        seen: set[str] = set()
        pending = [key]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(self._planner.resolved_dependencies.get(current, ()))
        return frozenset(seen)

    def _first_closure_failure(
        self, closure: frozenset[str], failures: Mapping[str, ProjectLoadError]
    ) -> ProjectLoadError | None:
        """The first failed plan in plan order inside *closure*, if any."""
        for plan in self._planner.plans:
            if plan.key in closure and plan.key in failures:
                return failures[plan.key]
        return None

    def _target_loaded(self, target_key: str, closure: frozenset[str]) -> LoadedTarget | ProjectLoadError:
        """Build one successful target's registry slice from its own closure."""
        plan_order = [plan.key for plan in self._planner.plans if plan.key in closure]
        registry = {key: self._registry[key] for key in plan_order}
        resolved_dependencies = {
            key: tuple(dependency for dependency in self._planner.resolved_dependencies[key] if dependency in closure)
            for key in registry
        }
        validator = ProjectValidator(
            validate=self._validate,
            registry=registry,
            resolved_dependencies=resolved_dependencies,
            target_plan_keys={target_key},
        )
        try:
            validator.assert_no_moduletype_cycles()
            validator.apply_scope()
        except ProjectLoadError as exc:
            return exc
        programs, view_of_plan = self._name_registry(registry)
        return LoadedTarget(
            programs=programs,
            identity_views=self._identity_view_registry(registry, view_of_plan),
            diagnostics=self._diagnostics_for(closure),
            cache_info=self.cache_info,
        )

    def _diagnostics_for(self, closure: frozenset[str]) -> tuple[LoadDiagnostic, ...]:
        """Load findings that belong to *closure*, plus skipped-file findings.

        A finding about a loaded unit is included only for a target whose
        closure holds that unit. A skipped file has no loaded unit and is
        reported for every target.
        """
        closure_identities = {UnitIdentity.of(self._registry[key].name).key for key in closure}
        for spelling, (plan_key) in self._planner.resolved_names.values():
            if plan_key in closure:
                closure_identities.add(UnitIdentity.of(spelling).key)
        return tuple(
            diagnostic
            for diagnostic in self._diagnostics
            if diagnostic.kind is LoadDiagnosticKind.SKIPPED_FILE
            or UnitIdentity.of(diagnostic.program).key in closure_identities
        )

    def _name_registry(
        self, registry: Mapping[str, SattLineProgram]
    ) -> tuple[dict[str, SattLineProgram], dict[str, str]]:
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
        for program in registry.values():
            key = program.name.casefold()
            shared[key] = shared.get(key, 0) + 1
        named: dict[str, SattLineProgram] = {}
        view_of_plan: dict[str, str] = {}
        for plan_key, program in registry.items():
            view = program.name.casefold()
            if shared[view] > 1:
                view = UnitIdentity.of(program.name).key
            named[view] = program
            view_of_plan[plan_key] = view
        return named, view_of_plan

    def _identity_view_registry(
        self, registry: Mapping[str, SattLineProgram], view_of_plan: Mapping[str, str]
    ) -> dict[str, str]:
        """Every spelling that reached a unit in the view, as identity -> view.

        A sidecar may name one body twice, for example directly and through a
        symlink. The body is planned once, so the second spelling would otherwise
        disappear and ``dependencies_of`` could return a name ``get`` cannot
        resolve. The unit's own name is registered from the registry, so a unit
        in a shared casefold group is reachable under its language identity.
        """
        views: dict[str, str] = {}
        for plan_key, program in registry.items():
            views.setdefault(UnitIdentity.of(program.name).key, view_of_plan[plan_key])
        for spelling, plan_key in self._planner.resolved_names.values():
            if plan_key in view_of_plan:
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
