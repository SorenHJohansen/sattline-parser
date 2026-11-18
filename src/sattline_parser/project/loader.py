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
from .discovery import ProjectLookup
from .executor import ParseExecutor
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
        #: Extra spellings that reached a loaded unit: folded spelling -> (the
        #: spelling, the project view key of the unit it reached). One body can be
        #: named twice, for example through a symlink, and every spelling a
        #: sidecar used must resolve back to the unit it named.
        self._aliases: dict[str, tuple[str, str]] = {}

        self._planner = ProjectPlanner(
            lookup=lookup,
            mode=mode,
            debug=debug,
            diagnose=self._diagnose,
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
        )
        self._executor = ParseExecutor(
            mode=mode,
            workers=workers,
            log_failures=log_failures,
            debug=debug,
            ast_cache=self._ast_cache,
            secure_cache_dir=secure_cache_dir,
            pool_factory=_parallel.process_pool,
        )

    @property
    def diagnostics(self) -> tuple[LoadDiagnostic, ...]:
        """Non-fatal load findings, in discovery then assembly order."""
        return tuple(self._diagnostics)

    @property
    def aliases(self) -> Mapping[str, tuple[str, str]]:
        """Every extra spelling that reached a loaded unit.

        Keys are folded spellings, values are the spelling as it was written and
        the project view key of the unit it reached. The mapping is filled by
        :meth:`resolve`.
        """
        return self._aliases

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
            self._planner.resolve(targets)
            outcomes = self._executor.parse(self._planner.plans)
            self._assembler.assemble(self._planner.plans, outcomes=outcomes)
            self._assert_registry_post_order()
            self._validator.assert_no_moduletype_cycles()
            if self._validate is LoadValidation.INVOKED:
                self._validator.validate_invoked()
            programs = self._name_registry()
            self._aliases = self._alias_registry(programs)
            return programs
        finally:
            if self._lookup_cache is not None:
                self._lookup_cache.flush()

    def _name_registry(self) -> dict[str, SattLineProgram]:
        """The public registry: one unit per folded name, first resolution wins.

        Every planned body assembles, so the first resolution is always the
        exposed one. The key is ``str.casefold``, the project view's own
        canonical spelling, and ``SattLineProject`` looks up by the same rule.

        Two units can share that key even though the language keeps them apart,
        for example ``Straße`` and ``STRASSE``. The first in plan order wins and
        the planner has already reported the pair as a folded-name collision,
        because a casefolded view has no second slot for it. Language identity
        inside a unit uses the CP1252 table (``fold_identifier``); artifact
        identity uses :class:`ArtifactIdentity`.
        """
        registry: dict[str, SattLineProgram] = {}
        for program in self._registry.values():
            registry.setdefault(program.name.casefold(), program)
        return registry

    def _alias_registry(self, programs: Mapping[str, SattLineProgram]) -> dict[str, tuple[str, str]]:
        """Every extra spelling that reached a unit in *programs*.

        A sidecar may name one body twice, for example directly and through a
        symlink. The body is planned once, so the second spelling would otherwise
        disappear and ``dependencies_of`` could return a name ``get`` cannot
        resolve. A spelling whose unit lost the project view to a folded-name
        collision is dropped: that layout is already reported.
        """
        view_of_plan: dict[str, str] = {}
        for plan_key, program in self._registry.items():
            view = program.name.casefold()
            if programs.get(view) is program:
                view_of_plan[plan_key] = view
        aliases: dict[str, tuple[str, str]] = {}
        for key, (spelling, plan_key) in self._planner.resolved_names.items():
            view = view_of_plan.get(plan_key)
            if view is None or key == view:
                continue
            aliases[key] = (spelling, view)
        return aliases

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
