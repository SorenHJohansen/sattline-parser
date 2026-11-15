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

from collections.abc import Callable, Sequence
from pathlib import Path

from sattline_parser.source_io import parse_source_bytes, private_cache_dir

from . import executor as _executor
from . import parallel as _parallel
from . import plan as _plan_module
from .assembler import ProjectAssembler
from .ast_cache import FileASTCache, source_snapshot
from .discovery import ProjectLookup
from .executor import ParseExecutor
from .lookup_cache import FileLookupCache
from .models import (
    GraphicsModel,
    LoadDiagnostic,
    LoadDiagnosticKind,
    LoadMode,
    LoadValidation,
    SattLineProgram,
)
from .plan import ResolvedArtifact as _ResolvedArtifact
from .planner import ProjectPlanner, read_dependency_names
from .scope import ProjectValidator

__all__ = ["ProjectLoader", "read_dependency_names"]

#: Historical names for the worker machinery and the plan key. They are aliases,
#: not copies, so a monkeypatched alias is the callable the loader uses.
_ParseFailure = _executor.ParseFailure
_ParseOutcome = _executor.ParseOutcome
_parse_failure_record = _executor.parse_failure_record
_rebuild_parse_failure = _executor.rebuild_parse_failure


def _parse_code_file(task: tuple[str, str, str | None, bool]) -> _executor.ParseOutcome:  # pyright: ignore[reportUnusedFunction]
    """Worker entry point through this module's own parse and snapshot names.

    The real pool uses the executor's function directly. This wrapper keeps the
    loader's historical call site, including a caller that substitutes the
    parser or the snapshot function for a test.
    """
    return _executor.parse_code_file(
        task,
        parse_bytes=parse_source_bytes,
        snapshot=source_snapshot,
    )


_plan_key = _plan_module.plan_key
_pool_allowed = _parallel.pool_allowed
_process_pool = _parallel.process_pool
_start_method = _parallel.start_method


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

        self._planner = ProjectPlanner(
            lookup=lookup,
            mode=mode,
            debug=debug,
            diagnose=self._diagnose,
            artifact_resolver=self._resolve_artifact,
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
            companion_loader=self._load_companion,
        )
        self._executor = ParseExecutor(
            mode=mode,
            workers=workers,
            log_failures=log_failures,
            debug=debug,
            ast_cache=self._ast_cache,
            secure_cache_dir=secure_cache_dir,
            pool_factory=_process_pool,
            parse_bytes=parse_source_bytes,
            snapshot_factory=source_snapshot,
        )

    @property
    def diagnostics(self) -> tuple[LoadDiagnostic, ...]:
        """Non-fatal load findings, in discovery then assembly order."""
        return tuple(self._diagnostics)

    @property
    def _resolved_dependencies(self) -> dict[str, tuple[str, ...]]:
        return self._planner.resolved_dependencies

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
            self._assembler.assemble(
                self._planner.plans,
                resolved_dependencies=self._planner.resolved_dependencies,
                outcomes=outcomes,
            )
            self._assert_registry_post_order()
            self._validator.assert_no_moduletype_cycles()
            if self._validate is LoadValidation.INVOKED:
                self._validator.validate_invoked()
            return self._name_registry()
        finally:
            if self._lookup_cache is not None:
                self._lookup_cache.flush()

    def _resolve_artifact(
        self,
        name: str,
        *,
        program_name: str,
        dependency: str | None,
    ) -> _ResolvedArtifact:
        """Delegate to the planner, keeping the historical patch point."""
        return self._planner.resolve_artifact(name, program_name=program_name, dependency=dependency)

    def _load_companion(
        self,
        code_path: Path,
        *,
        name: str,
        program_name: str,
        dependency: str | None,
    ) -> tuple[Path | None, GraphicsModel | None]:
        """Delegate to the assembler, keeping the historical patch point."""
        return self._assembler._load_companion(  # pyright: ignore[reportPrivateUsage]
            code_path,
            name=name,
            program_name=program_name,
            dependency=dependency,
        )

    def _name_registry(self) -> dict[str, SattLineProgram]:
        """The public registry: one unit per folded name, first resolution wins.

        Every planned body assembles, so the first resolution is always the
        exposed one. The key is ``str.casefold``, the project view's own
        canonical spelling, and ``SattLineProject`` looks up by the same rule.
        Language identity inside a unit uses the CP1252 table
        (``fold_identifier``); artifact identity uses :class:`ArtifactIdentity`.
        """
        registry: dict[str, SattLineProgram] = {}
        for program in self._registry.values():
            registry.setdefault(program.name.casefold(), program)
        return registry

    def _assert_registry_post_order(self) -> None:
        """Assert that every loaded dependency precedes its consumer."""
        seen: set[str] = set()
        for key, program in self._registry.items():
            for dependency_key in self._resolved_dependencies.get(key, ()):
                if dependency_key in self._registry and dependency_key not in seen:
                    dependency_name = self._registry[dependency_key].name
                    raise RuntimeError(
                        f"loader registry is not in post-order: {program.name!r} precedes dependency {dependency_name!r}"
                    )
            seen.add(key)


# The worker machinery lives in ``executor`` and the plan types in ``plan``.
# These aliases keep the historical import paths working for a consumer that
# reaches into the loader module, and they are the names this module's own tests
# have always used.
