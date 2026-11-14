"""Recursive program loading, dependency resolution, and project validation.

The loader resolves a target across ordered roots, reads its dependency sidecar,
loads dependencies first, parses the body, and (when validation runs) runs the
single-file validator with the definitions visible from already-loaded programs.
``validate=INVOKED`` validates each target in full and limits dependency files
to the module types that target invokes, transitively.

Post-order is an invariant: the registry is built dependencies-first, so a
program's diagnostics are computed against a complete prefix of its closure.
The loader asserts that invariant. Invoked-scope validation runs after the graph
is complete because it needs the whole invocation graph.

A plan is keyed by the resolved code path, not by the folded name. One root's
``Util.s`` and another root's ``Util.s`` are therefore two plans with two
bodies, and each requester's closure follows the body its own ordered lookup
resolved. The public registry still holds one program per folded name; when one
name resolves to different bodies for different requesters, the loader keeps
the first and reports a ``NAME_RESOLUTION_CONFLICT`` diagnostic.

``tentative`` marking is owned here. A finding is tentative when the definition
it could not resolve, or the module type it resolved through, may have come
from a dependency that a non-strict load skipped. Purely local findings stay
final even when an unrelated dependency is missing.

Strict loading fails fast on missing or unparseable artifacts. Validation
findings never raise; ``strict`` governs load failures only. Two structural
errors are not recoverable by either strictness setting: a recursive sidecar
chain and a module type that instantiates itself.
"""

from __future__ import annotations

import multiprocessing
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, replace
from pathlib import Path

from sattline_parser.errors import PARSE_FAILURES
from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    FrameModule,
    ModuleTypeDef,
    ModuleTypeInstance,
    Simple_DataType,
    SingleModule,
    SourceSpan,
)
from sattline_parser.names import fold_identifier
from sattline_parser.source_io import parse_source_file, private_cache_dir, read_text_cp1252
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.type_graph import TypeGraph

from ._cycles import canonical_cycle, first_cycle
from .ast_cache import FileASTCache, source_snapshot
from .discovery import ProjectLookup
from .distribution import (
    DistributionParseError,
    parse_distribution_file,
    resolve_distribution_companion_path,
)
from .errors import (
    ArtifactLoadError,
    DependencyCycleError,
    DependencyNotFoundError,
    DependencyParseError,
    ModuleTypeCycleError,
    ProjectLoadError,
    StructuralProjectError,
)
from .formats import ALL_DEPS_EXTENSIONS, body_mode, find_companion_beside
from .graphics_parsing import GraphicsParseError, parse_graphics_file, resolve_graphics_companion_path
from .lookup_cache import FileLookupCache
from .models import (
    DistributionData,
    GraphicsModel,
    LoadDiagnostic,
    LoadDiagnosticKind,
    LoadMode,
    LoadValidation,
    ProgramFormat,
    SattLineProgram,
    SidecarState,
)
from .reachability import invoked_moduletypes, iter_moduletype_refs

#: Findings whose subject is a name no loaded definition resolved. A skipped
#: dependency may hold the definition, so they are tentative in an incomplete
#: closure.
_UNRESOLVED_NAME_CODES = frozenset(
    {
        DiagnosticCode.UNKNOWN_DATATYPE_NAME,
        DiagnosticCode.UNKNOWN_MODULETYPE_NAME,
    }
)

#: Findings produced by resolving a module type and checking a mapping against
#: it. They are tentative only when that module type is contributed by a
#: dependency whose own closure is incomplete.
_MODULE_MAPPING_CODES = frozenset(
    {
        DiagnosticCode.PARAM_TRANSFER_TYPE_MISMATCH,
        DiagnosticCode.PARAMETER_MAPPING_TARGET_UNKNOWN,
        DiagnosticCode.PARAMETER_MAPPING_TYPE_MISMATCH,
    }
)

#: The folded names of the scalar datatypes, which are always known.
_SCALAR_DATATYPE_NAMES = frozenset(fold_identifier(datatype.value) for datatype in Simple_DataType)


@dataclass(frozen=True, slots=True)
class _MappingDefinitions:
    """The folded definitions one parameter mapping resolves through."""

    #: The module type the instance names.
    moduletype: str
    #: The datatypes of that module type's parameters.
    datatypes: frozenset[str]


@dataclass(frozen=True, slots=True)
class _TentativeScope:
    """What can make a finding in one program depend on an unloaded dependency."""

    #: The program's own closure is incomplete, so an unresolved name may live
    #: in a skipped dependency.
    incomplete: bool
    #: Plan keys of the incomplete dependencies in this program's closure.
    incomplete_owners: frozenset[str]
    #: Folded module-type and datatype name to the plan keys that declare it.
    definition_owners: Mapping[str, frozenset[str]]
    #: Parameter-mapping span to the definitions the mapping resolves through.
    definitions_by_span: Mapping[SourceSpan, _MappingDefinitions]
    #: Local, external, and builtin datatypes, so an unresolved name is
    #: distinguishable from a known one. ``None`` when the closure is complete,
    #: where no finding can become tentative.
    type_graph: TypeGraph | None = None

    def mark(self, diagnostics: Sequence[Diagnostic]) -> list[Diagnostic]:
        """Mark the findings this scope cannot make final."""
        return [replace(item, tentative=True) if self._is_tentative(item) else item for item in diagnostics]

    def _is_tentative(self, item: Diagnostic) -> bool:
        if item.code in _UNRESOLVED_NAME_CODES:
            return self.incomplete
        if item.code not in _MODULE_MAPPING_CODES or item.span is None:
            return False
        definitions = self.definitions_by_span.get(item.span)
        if definitions is None:
            return False
        if self._owner_is_incomplete(definitions.moduletype):
            return True
        for datatype in definitions.datatypes:
            if self._owner_is_incomplete(datatype):
                return True
            if not self._is_known_datatype(datatype):
                # The parameter datatype may be declared by a skipped dependency.
                return True
        return False

    def _owner_is_incomplete(self, name: str) -> bool:
        owners = self.definition_owners.get(name)
        return bool(owners and owners & self.incomplete_owners)

    def _is_known_datatype(self, name: str) -> bool:
        if name in _SCALAR_DATATYPE_NAMES:
            return True
        return self.type_graph is not None and self.type_graph.has_record(name)


def read_dependency_names(deps_path: Path) -> tuple[str, ...]:
    """Read a ``.l`` / ``.z`` dependency file into declared dependency names.

    Each non-blank line is one dependency name; lines are trimmed, blank lines
    are ignored, and declaration order is preserved.
    """
    text = read_text_cp1252(deps_path)
    return tuple(line.strip() for line in text.splitlines() if line.strip())


@dataclass(frozen=True, slots=True)
class _ResolvedArtifact:
    """The resolved files and dependency metadata for one program name."""

    code_path: Path
    resolved_base: Path
    library: str
    deps_path: Path | None
    sidecar: SidecarState
    dependencies: tuple[str, ...]
    dependency_requester: Path


@dataclass(frozen=True, slots=True)
class _Plan:
    """One discovered program, resolved and ready to parse.

    Discovery fills a plan without parsing anything, so the whole closure is
    known before parse work starts. Assembly consumes plans in plan order,
    which is post-order: every dependency precedes its consumer. ``key`` is the
    resolved code path, so two roots holding a same-named unit are two plans.
    ``dependencies`` holds the plan key of each resolved dependency, in
    declaration order.
    """

    key: str
    name: str
    declared_by: str | None
    artifact: _ResolvedArtifact
    dependencies: tuple[str, ...] = ()


def _plan_key(code_path: Path) -> str:
    """The unique plan identity for a resolved body: its resolved code path."""
    try:
        return str(code_path.resolve())
    except OSError:
        return str(code_path)


def _iter_moduletype_instances(code: BasePicture) -> Iterable[ModuleTypeInstance]:
    """Yield every module-type instance in one picture, nested ones included."""
    pending: list[SingleModule | FrameModule | ModuleTypeInstance] = [*code.submodules]
    for moduletype in code.moduletype_defs:
        pending.extend(moduletype.submodules)
    while pending:
        node = pending.pop()
        if isinstance(node, ModuleTypeInstance):
            yield node
            continue
        pending.extend(node.submodules)


@dataclass(frozen=True, slots=True)
class _ParseOutcome:
    """A parsed body, or the text of the failure that stopped it."""

    ast: BasePicture | None = None
    failure: str | None = None
    #: The original failure, kept when the parse ran in this process so a
    #: caller can still reach a ``SourceTooDeepError`` limit or a decode
    #: offset through ``__cause__``. A worker returns text only.
    error: ProjectLoadError | None = None
    #: The source stat captured before the parse, so the parent can refuse to
    #: cache an AST when the file changed while a worker was reading it.
    snapshot: tuple[int, int] | None = None
    #: The AST came from the cache, so it has nothing to store.
    cached: bool = False


def _program_name(plan: _Plan) -> str:
    return plan.declared_by if plan.declared_by is not None else plan.name


def _dependency(plan: _Plan) -> str | None:
    return None if plan.declared_by is None else plan.name


def _parse_failure(program_name: str, code_name: str, dependency: str | None) -> ProjectLoadError:
    """The load error for a body that did not parse."""
    if dependency is None:
        return ArtifactLoadError(program_name, f"failed to parse {code_name}")
    return DependencyParseError(
        program_name,
        f"failed to parse dependency {dependency!r}",
        dependency=dependency,
    )


def _skipped_diagnostic(name: str, error: ProjectLoadError, parents: Sequence[str]) -> LoadDiagnostic:
    """The one ``LOAD_SKIPPED`` row for a name that could not be discovered."""
    detail = f"skipped {name!r}: {error}"
    if parents:
        detail += f" (requested by {', '.join(parents)})"
    return LoadDiagnostic(kind=LoadDiagnosticKind.LOAD_SKIPPED, program=name, detail=detail)


@dataclass(slots=True)
class _SkippedName:
    """One negative-cached discovery failure, with every requester that hit it."""

    error: ProjectLoadError
    parents: list[str]
    diagnostic: LoadDiagnostic
    index: int


#: One cache handle per worker process. Constructing a handle per task would
#: re-run the private-directory check and the startup prune for every file.
_WORKER_CACHES: dict[str, FileASTCache] = {}


def _worker_cache(cache_text: str) -> FileASTCache:
    cache = _WORKER_CACHES.get(cache_text)
    if cache is None:
        cache = FileASTCache(Path(cache_text))
        _WORKER_CACHES[cache_text] = cache
    return cache


def _parse_code_file(task: tuple[str, str, str | None]) -> _ParseOutcome:
    """Parse one code file into an AST.

    Runs in a child process when ``workers`` is greater than one, so it must not
    touch the loader or its registry. It reads the AST cache but never writes
    it: the parent owns every write, so the per-user cache key is created and
    the entries are signed by a single process. A failure comes back as text,
    because the error type and wording depend on the dependency edge and the
    parent owns both.
    """
    code_text, mode, cache_text = task
    code_path = Path(code_text)
    if cache_text is not None:
        cached = _worker_cache(cache_text).load(code_path, mode)
        if cached is not None:
            return _ParseOutcome(ast=cached, cached=True)
    snapshot = source_snapshot(code_path)
    try:
        picture = parse_source_file(code_path)
    except PARSE_FAILURES as exc:
        return _ParseOutcome(failure=str(exc) or type(exc).__name__)
    return _ParseOutcome(ast=picture, snapshot=snapshot)


def _start_method(methods: Sequence[str], *, threaded: bool) -> str | None:
    """The preferred pool start method, or ``None`` for the platform default.

    A single-threaded process prefers ``fork``: the caller needs no ``__main__``
    guard. Forking a process with other threads is deprecated in CPython and
    can inherit a lock another thread held at fork time, so a threaded host
    prefers ``forkserver``, then ``spawn``. Platforms that offer only ``fork``
    still get it: this is a preference, not a guarantee.
    """
    if threaded:
        for candidate in ("forkserver", "spawn"):
            if candidate in methods:
                return candidate
    for candidate in ("fork", "forkserver", "spawn"):
        if candidate in methods:
            return candidate
    return None


def _pool_allowed() -> bool:
    """A daemonic process may not start children, so a nested load stays in this one."""
    return not multiprocessing.current_process().daemon


def _process_pool(max_workers: int) -> ProcessPoolExecutor:
    """A process pool shaped for the current process."""
    method = _start_method(multiprocessing.get_all_start_methods(), threaded=threading.active_count() > 1)
    return ProcessPoolExecutor(max_workers=max_workers, mp_context=multiprocessing.get_context(method))


class ProjectLoader:
    """Recursive resolver producing the canonical program registry for a load."""

    def __init__(
        self,
        *,
        roots: Sequence[Path],
        mode: LoadMode,
        strict: bool,
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
        self._lookup = ProjectLookup(roots, mode, cache=self._lookup_cache, debug=debug)
        self._mode = mode
        self._strict = strict
        self._debug = debug
        self._validate = validate
        self._workers = max(1, workers)
        self._secure_cache_dir = secure_cache_dir
        #: Discovery order is post-order, so assembly is a single pass. Plans
        #: are keyed by resolved code path, so a same-named unit in another
        #: root is a second plan rather than a silent alias.
        self._plans: list[_Plan] = []
        self._planned: set[str] = set()
        #: Folded name -> the plan key that first resolved it.
        self._plan_key_by_name: dict[str, str] = {}
        #: Plan key -> the plan keys of its resolved dependencies.
        self._resolved_dependencies: dict[str, tuple[str, ...]] = {}
        self._parsed: dict[str, _ParseOutcome] = {}
        self._resolved = False
        #: Plan key -> the assembled program. The public view keeps one program
        #: per folded name; this registry keeps every resolved body.
        self._registry: dict[str, SattLineProgram] = {}
        #: Insertion-ordered set of folded names currently being loaded.
        self._loading: dict[str, None] = {}
        self._diagnostics: list[LoadDiagnostic] = []
        self._diagnostic_set: set[LoadDiagnostic] = set()
        #: Folded name -> the one negative-cached discovery failure.
        self._skipped: dict[str, _SkippedName] = {}
        #: Plan keys of the explicitly requested programs.
        self._target_plan_keys: set[str] = set()
        self._incomplete: set[str] = set()
        #: name -> datecode -> program keys declaring it. Conflict checks are
        #: scoped to a program's visible closure, so unrelated programs that
        #: happen to declare the same name never conflict with each other.
        self._moduletype_versions: dict[str, dict[int, set[str]]] = {}
        self._datatype_versions: dict[str, dict[int, set[str]]] = {}
        #: program key -> source label used in diagnostics.
        self._labels: dict[str, str] = {}

    def _dbg(self, message: str) -> None:
        if self._debug is not None:
            self._debug(message)

    @property
    def diagnostics(self) -> tuple[LoadDiagnostic, ...]:
        """Non-fatal findings recorded during this load, in discovery order."""
        return tuple(self._diagnostics)

    def _diagnose(self, kind: LoadDiagnosticKind, program: str, detail: str, path: Path | None = None) -> None:
        diagnostic = LoadDiagnostic(kind=kind, program=program, detail=detail, path=path)
        if diagnostic in self._diagnostic_set:
            return
        self._diagnostics.append(diagnostic)
        self._diagnostic_set.add(diagnostic)

    def resolve(self, targets: Sequence[str]) -> dict[str, SattLineProgram]:
        """Resolve ``targets`` into the canonical registry for this load.

        A loader accumulates one registry: discovery plans, parse outcomes, and
        the registry itself are per-load state, so a second call would double
        the plans and re-assemble over the first result. One loader resolves
        once; construct another for another load. The returned mapping holds one
        program per folded name, which is the documented project identity.
        """
        if self._resolved:
            raise RuntimeError("ProjectLoader.resolve() resolves one load; construct another loader")
        self._resolved = True
        try:
            for target in targets:
                plan_key = self._visit(target, requester_dir=None, declared_by=None)
                if plan_key is not None:
                    self._target_plan_keys.add(plan_key)
            self._parse_planned()
            self._assemble()
            self._assert_registry_post_order()
            self._assert_no_moduletype_cycles()
            if self._validate is LoadValidation.INVOKED:
                self._validate_invoked()
            return self._name_registry()
        finally:
            if self._lookup_cache is not None:
                self._lookup_cache.flush()

    def _name_registry(self) -> dict[str, SattLineProgram]:
        """The public registry: one program per folded name, first resolution wins.

        When the first-resolved body failed to assemble, the first body that did
        assemble carries the name, so a skipped plan never blanks a name that a
        later requester resolved successfully.
        """
        registry: dict[str, SattLineProgram] = {}
        for key, program in self._registry.items():
            name_key = program.name.casefold()
            exposed_key = self._plan_key_by_name.get(name_key)
            if exposed_key is not None and exposed_key != key and exposed_key in self._registry:
                continue
            registry.setdefault(name_key, program)
        return registry

    def _assert_no_moduletype_cycles(self) -> None:
        """Reject a module type whose instantiation chain returns to itself.

        Each program is checked against its visible closure, and a node is one
        *definition* (owning program plus folded name), so two libraries that
        reuse a name are two nodes, not one. A reference resolves to the
        referencing file's own definition first, then to any definition in the
        checked program's closure, which keeps a library that shadows a
        dependency's type name from looking recursive. Only the first cycle
        matters, and a graph can hold exponentially many elementary cycles, so
        the search stops as soon as it finds one.
        """
        for key in self._registry:
            visible_keys = self._visible_plan_keys(key)
            edges, labels, owners = _moduletype_edges(self._registry, visible_keys)
            cycle = first_cycle(edges)
            if cycle is not None:
                display = tuple(labels[node] for node in cycle)
                raise ModuleTypeCycleError(owners[cycle[0]], display)

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

    def _visit(self, name: str, *, requester_dir: Path | None, declared_by: str | None) -> str | None:
        """Plan one program and return its plan key, or ``None`` when it was skipped."""
        key = name.casefold()
        if key in self._loading:
            # A dependency loop has no finite load order. It is structural, so
            # neither strictness setting may recover from it.
            loading = tuple(self._loading)
            start = loading.index(key)
            raise DependencyCycleError(canonical_cycle((*loading[start:], key)))
        self._loading[key] = None
        try:
            return self._discover(name, requester_dir=requester_dir, declared_by=declared_by)
        finally:
            del self._loading[key]

    def _discover(self, name: str, *, requester_dir: Path | None, declared_by: str | None) -> str | None:
        """Resolve one program's artifacts and recurse into its dependencies.

        Discovery is path resolution and sidecar reads only: it never parses a
        body, so the whole closure is known before any parse work starts. The
        plan is appended after the recursion, which makes ``self._plans`` the
        post-order sequence the assembly phase needs.

        A name that resolves to a body this load already planned reuses that
        plan. A name that resolves to a *different* body is a second plan, and
        the conflict is reported when that body assembles, because the two
        requesters really did resolve two different units.
        """
        program_name = declared_by if declared_by is not None else name
        dependency = None if declared_by is None else name
        skipped = self._skipped.get(name.casefold())
        if skipped is not None:
            # A miss is name-global: the ordered bases are the same configured
            # roots for every requester, only their order changes. Reusing the
            # cached failure skips a second ordered scan and a second finding.
            self._record_skipped(name, parent=declared_by, error=skipped.error)
            return None
        try:
            self._dbg(f"Visiting: {name}")
            artifact = self._resolve_artifact(
                name,
                requester_dir=requester_dir,
                program_name=program_name,
                dependency=dependency,
            )
        except StructuralProjectError:
            raise
        except ProjectLoadError as exc:
            if self._strict:
                raise
            # Non-strict loading must not be silent: an agent or a CI job has to
            # be able to tell that a program is missing from the result. The
            # failure is cached per name, so a second requester extends the same
            # row instead of repeating the ordered scan and the finding.
            self._record_skipped(name, parent=declared_by, error=exc)
            return None
        plan_key = _plan_key(artifact.code_path)
        name_key = name.casefold()
        self._plan_key_by_name.setdefault(name_key, plan_key)
        if plan_key in self._planned:
            return plan_key
        self._planned.add(plan_key)
        resolved: list[str] = []
        incomplete = False
        for declared in artifact.dependencies:
            dependency_key = self._visit(
                declared,
                requester_dir=artifact.dependency_requester,
                declared_by=name,
            )
            if dependency_key is None:
                incomplete = True
            else:
                resolved.append(dependency_key)
        self._plans.append(
            _Plan(
                key=plan_key,
                name=name,
                declared_by=declared_by,
                artifact=artifact,
                dependencies=tuple(resolved),
            )
        )
        self._resolved_dependencies[plan_key] = tuple(resolved)
        if incomplete:
            self._incomplete.add(plan_key)
        return plan_key

    def _record_skipped(self, name: str, *, parent: str | None, error: ProjectLoadError) -> None:
        """Record one discovery failure, extending its parent list on a repeat."""
        key = name.casefold()
        requester = parent if parent is not None else name
        existing = self._skipped.get(key)
        if existing is None:
            diagnostic = _skipped_diagnostic(name, error, [requester])
            self._diagnostics.append(diagnostic)
            self._diagnostic_set.add(diagnostic)
            self._skipped[key] = _SkippedName(
                error=error,
                parents=[requester],
                diagnostic=diagnostic,
                index=len(self._diagnostics) - 1,
            )
            return
        if requester in existing.parents:
            return
        existing.parents.append(requester)
        updated = _skipped_diagnostic(name, existing.error, existing.parents)
        self._diagnostic_set.discard(existing.diagnostic)
        self._diagnostics[existing.index] = updated
        self._diagnostic_set.add(updated)
        existing.diagnostic = updated

    def _record_shared_name(self, name: str, plan_key: str) -> None:
        """Report one folded name resolving to different bodies for different requesters.

        Called when a body assembles, so the diagnostic only ever describes two
        bodies that really did load.
        """
        first = self._plan_key_by_name.get(name.casefold())
        if first is None or first == plan_key:
            return
        self._diagnose(
            LoadDiagnosticKind.NAME_RESOLUTION_CONFLICT,
            name,
            f"name {name!r} resolves to {first} for one requester and {plan_key} for another; "
            f"both bodies load, and the project registry keeps {first}",
            Path(plan_key),
        )

    def _parse_planned(self) -> None:
        """Parse every planned body, in parallel when ``workers`` allows it.

        Failures are carried, not raised: strict and non-strict differ in what
        they do with a failure, and that decision belongs to the assembly phase
        so both modes see the same error.
        """
        if not self._plans:
            return
        if self._workers <= 1 or len(self._plans) == 1:
            for plan in self._plans:
                self._parsed[plan.key] = self._parse_in_process(plan)
            return
        if not _pool_allowed():
            # A daemonic process cannot start children. Parsing here is slower
            # but correct, and the caller already owns a pool to run us on.
            self._dbg("Parsing in this process: a daemonic process cannot start workers")
            for plan in self._plans:
                self._parsed[plan.key] = self._parse_in_process(plan)
            return

        cache_text = None if self._secure_cache_dir is None else str(self._secure_cache_dir)
        tasks = [(str(plan.artifact.code_path), self._mode.value, cache_text) for plan in self._plans]
        workers = min(self._workers, len(tasks))
        self._dbg(f"Parsing {len(tasks)} bodies in {workers} processes")
        try:
            pool = _process_pool(workers)
        except (OSError, RuntimeError, ValueError) as exc:
            # A pool cannot always be created (no worker start method, a
            # restricted sandbox). Parsing is the load, not an optimisation
            # detail, so fall back to this process rather than failing.
            self._dbg(f"Parallel parsing unavailable ({exc}); parsing in this process")
            for plan in self._plans:
                self._parsed[plan.key] = self._parse_in_process(plan)
            return
        try:
            outcomes = list(pool.map(_parse_code_file, tasks, chunksize=1))
        except (BrokenProcessPool, OSError) as exc:
            # ``ProcessPoolExecutor`` starts its workers on the first submit, so
            # a missing worker start method, a denied fork, or an exhausted
            # process limit surfaces here rather than from the constructor. A
            # dead worker is the same story. Parsing is the load, not an
            # optimisation detail, so fall back to this process.
            pool.shutdown(wait=True, cancel_futures=True)
            self._dbg(f"Worker pool failed ({exc}); parsing in this process")
            for plan in self._plans:
                self._parsed[plan.key] = self._parse_in_process(plan)
            return
        except BaseException:
            # Interrupt: cancel the queued bodies before waiting for anything,
            # so a Ctrl-C does not have to drain the rest of the tree.
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            pool.shutdown(wait=True)
        for plan, outcome in zip(self._plans, outcomes, strict=True):
            self._parsed[plan.key] = outcome
            self._save_cached(plan, outcome)

    def _parse_in_process(self, plan: _Plan) -> _ParseOutcome:
        """Parse one plan through the loader's own cache, parser, and errors."""
        try:
            ast = self._load_ast(
                plan.artifact.code_path,
                program_name=_program_name(plan),
                dependency=_dependency(plan),
            )
        except ProjectLoadError as exc:
            return _ParseOutcome(failure=str(exc), error=exc)
        return _ParseOutcome(ast=ast)

    def _save_cached(self, plan: _Plan, outcome: _ParseOutcome) -> None:
        """Store a body the worker parsed and did not cache itself.

        A worker never writes the cache, so the per-user key and the entry
        signatures stay single-process. A parse that came from the cache has
        nothing to store, and a body whose source changed while the worker was
        reading it is left uncached rather than stored under newer metadata.
        """
        if outcome.ast is None or outcome.cached or self._ast_cache is None:
            return
        code_path = plan.artifact.code_path
        try:
            self._ast_cache.save(code_path, self._mode.value, outcome.ast, snapshot=outcome.snapshot)
        except OSError as exc:
            # The cache is an optimisation: a failed write must not turn a
            # successful parse into a load failure.
            self._dbg(f"Cache write failed for {code_path}: {exc}")

    def _assemble(self) -> None:
        """Turn the parsed plans into the canonical registry, in post-order."""
        for plan in self._plans:
            self._assemble_one(plan)

    def _assemble_one(self, plan: _Plan) -> None:
        artifact = plan.artifact
        if any(dependency in self._incomplete for dependency in plan.dependencies):
            self._incomplete.add(plan.key)

        outcome = self._parsed[plan.key]
        basepicture = outcome.ast
        if basepicture is None:
            error = _parse_failure(_program_name(plan), artifact.code_path.name, _dependency(plan))
            if self._strict:
                raise error from (outcome.error or RuntimeError(outcome.failure))
            self._incomplete.add(plan.key)
            self._diagnose(LoadDiagnosticKind.LOAD_SKIPPED, plan.name, f"skipped {plan.name!r}: {error}")
            return

        _set_origin(basepicture, file_name=artifact.code_path.name, library=artifact.library)
        try:
            self._assemble_body(plan, basepicture)
        except StructuralProjectError:
            raise
        except ProjectLoadError as exc:
            if self._strict:
                raise
            self._incomplete.add(plan.key)
            self._diagnose(LoadDiagnosticKind.LOAD_SKIPPED, plan.name, f"skipped {plan.name!r}: {exc}")

    def _assemble_body(self, plan: _Plan, basepicture: BasePicture) -> None:
        """Attach diagnostics, definitions, and companion, then register."""
        artifact = plan.artifact
        name = plan.name
        program_name = _program_name(plan)
        dependency = _dependency(plan)
        self._record_shared_name(name, plan.key)
        diagnostics = self._artifact_diagnostics(
            basepicture,
            key=plan.key,
            artifact=artifact,
        )
        self._remember_definitions(
            basepicture,
            library=artifact.library,
            file_name=artifact.code_path.name,
            program_key=plan.key,
        )

        graphics_path, graphics = self._load_companion(
            artifact.code_path,
            name=name,
            program_name=program_name,
            dependency=dependency,
        )
        distribution_path, distribution = self._load_distribution(
            artifact.code_path,
            name=name,
            program_name=program_name,
            dependency=dependency,
        )
        self._registry[plan.key] = SattLineProgram(
            name=name,
            code=basepicture,
            graphics=graphics,
            dependencies=artifact.dependencies,
            format=ProgramFormat(
                mode=body_mode(artifact.code_path.suffix, self._mode),
                code_ext=artifact.code_path.suffix.lower(),
                graphics_ext=graphics_path.suffix.lower() if graphics_path is not None else None,
                deps_ext=artifact.deps_path.suffix.lower() if artifact.deps_path is not None else None,
                distribution_ext=distribution_path.suffix.lower() if distribution_path is not None else None,
            ),
            source_path=artifact.code_path,
            deps_path=artifact.deps_path,
            sidecar=artifact.sidecar,
            library=artifact.library,
            resolved_base=artifact.resolved_base,
            distribution_path=distribution_path,
            distribution=distribution,
            diagnostics=diagnostics,
        )

    def _resolve_artifact(
        self,
        name: str,
        *,
        requester_dir: Path | None,
        program_name: str,
        dependency: str | None,
    ) -> _ResolvedArtifact:
        """Find the body, its sidecar, and the declared dependencies."""
        resolved = self._lookup.find_code_with_base(name, requester_dir=requester_dir)
        if resolved is None:
            raise DependencyNotFoundError(
                program_name,
                f"missing code file for {name!r}",
                dependency=dependency,
            )
        code_path, resolved_base = resolved
        library = resolved_base.name
        # The sidecar belongs to the selected body's prefix; see
        # ProjectLookup.find_deps_beside.
        deps_path = self._lookup.find_deps_beside(code_path, name, requester_dir=requester_dir)
        sidecar = SidecarState.ABSENT
        if deps_path is None:
            # A sidecar in the other family sits at the body's own prefix. Probe
            # for it directly, because a mode-filtered root-ordered search never
            # sees the other family and official mode would report a plain miss.
            same_prefix = find_companion_beside(code_path, sorted(ALL_DEPS_EXTENSIONS))
            stray = self._lookup.find_deps(name, requester_dir=requester_dir)
            if same_prefix is not None:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_FAMILY_MISMATCH,
                    program_name,
                    f"sidecar {same_prefix.name!r} does not match the artifact family of body "
                    f"{code_path.name!r}; not paired",
                    same_prefix,
                )
            elif stray is not None:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_ELSEWHERE,
                    program_name,
                    f"sidecar {stray.name!r} is not beside body {code_path.name!r}; not paired",
                    stray,
                )
            else:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_MISSING,
                    program_name,
                    f"no dependency sidecar beside {code_path.name!r}",
                    code_path,
                )
        dependency_requester = deps_path.parent if deps_path is not None else code_path.parent
        dependencies = self._read_deps(name, deps_path, program_name, dependency)
        if deps_path is not None:
            sidecar = SidecarState.PRESENT if dependencies else SidecarState.EMPTY
            if sidecar is SidecarState.EMPTY:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_EMPTY,
                    program_name,
                    f"sidecar {deps_path.name!r} declares no dependencies",
                    deps_path,
                )
        return _ResolvedArtifact(
            code_path=code_path,
            resolved_base=resolved_base,
            library=library,
            deps_path=deps_path,
            sidecar=sidecar,
            dependencies=dependencies,
            dependency_requester=dependency_requester,
        )

    def _artifact_diagnostics(
        self,
        basepicture: BasePicture,
        *,
        key: str,
        artifact: _ResolvedArtifact,
    ) -> tuple[Diagnostic, ...]:
        if self._validate is not LoadValidation.INVOKED:
            return self._program_diagnostics(
                basepicture,
                dependencies=self._resolved_dependencies.get(key, ()),
                library=artifact.library,
                file_name=artifact.code_path.name,
                key=key,
            )
        # Module diagnostics need the whole graph. Datecode findings belong to
        # an explicitly selected program; a library import is not the place to
        # report its own version drift. Ownership comes from the target set, not
        # from discovery order, so a target that was first reached as a
        # dependency still reports its own conflict whatever the target order.
        if key not in self._target_plan_keys:
            return ()
        return tuple(
            self._datecode_conflicts(
                basepicture,
                library=artifact.library,
                file_name=artifact.code_path.name,
                visible=self._visible_plan_keys(key),
            )
        )

    def _load_companion(
        self,
        code_path: Path,
        *,
        name: str,
        program_name: str,
        dependency: str | None,
    ) -> tuple[Path | None, GraphicsModel | None]:
        graphics_path = resolve_graphics_companion_path(code_path, mode=self._mode)
        if graphics_path is None:
            return None, None
        graphics = _load_graphics(
            self._dbg,
            graphics_path,
            program_name=program_name,
            dependency=dependency,
            name=name,
        )
        return graphics_path, graphics

    def _load_distribution(
        self,
        code_path: Path,
        *,
        name: str,
        program_name: str,
        dependency: str | None,
    ) -> tuple[Path | None, DistributionData | None]:
        """Read the distribution companion beside the selected body.

        A missing companion answers "unknown" and stays silent: distribution data
        is optional. A companion that exists but does not parse is an artifact
        failure, because an unreadable file must never be reported as "no
        executing system".
        """
        distribution_path = resolve_distribution_companion_path(code_path, mode=self._mode)
        if distribution_path is None:
            return None, None
        self._dbg(f"Parsing distribution: {distribution_path}")
        try:
            distribution = parse_distribution_file(distribution_path)
        except (OSError, UnicodeError, DistributionParseError) as exc:
            if dependency is None:
                raise ArtifactLoadError(
                    program_name,
                    f"failed to parse distribution companion {distribution_path.name} for {name!r}: {exc}",
                ) from exc
            raise DependencyParseError(
                program_name,
                f"failed to parse distribution companion for dependency {dependency!r}: {exc}",
                dependency=dependency,
            ) from exc
        return distribution_path, distribution

    def _closure(self, dependencies: Sequence[str]) -> frozenset[str]:
        """Plan keys of every program a set of resolved dependencies reaches."""
        closure: set[str] = set()
        pending = list(dependencies)
        while pending:
            key = pending.pop()
            if key in closure:
                continue
            closure.add(key)
            pending.extend(self._resolved_dependencies.get(key, ()))
        return frozenset(closure)

    def _visible_plan_keys(self, key: str) -> frozenset[str]:
        """Keys of every program *key* can see: itself plus its transitive deps."""
        return frozenset({key}) | self._closure(self._resolved_dependencies.get(key, ()))

    def _visible_definitions(
        self, dependencies: Sequence[str]
    ) -> tuple[tuple[DataType, ...], tuple[ModuleTypeDef, ...], dict[str, frozenset[str]]]:
        """Definitions from this program's transitive dependency closure.

        The registry is dependency-first, so filtering it by the closure keeps
        a deterministic order. Using the whole registry here would let an
        unrelated target's types hide an unknown-name finding. The owner map
        says which plan declared each folded name, so a finding can tell a
        local definition from one contributed by a dependency.
        """
        closure = self._closure(dependencies)
        datatypes: list[DataType] = []
        moduletypes: list[ModuleTypeDef] = []
        owners: dict[str, frozenset[str]] = {}
        for key, program in self._registry.items():
            if key not in closure:
                continue
            datatypes.extend(program.code.datatype_defs)
            moduletypes.extend(program.code.moduletype_defs)
            for definition in (*program.code.moduletype_defs, *program.code.datatype_defs):
                folded = fold_identifier(definition.name)
                owners[folded] = owners.get(folded, frozenset()) | {key}
        return tuple(datatypes), tuple(moduletypes), owners

    def _validate_invoked(self) -> None:
        """Add diagnostics for the module types each target actually invokes."""
        reachable = invoked_moduletypes(
            self._registry,
            self._target_plan_keys,
            closure_of=self._visible_plan_keys,
        )
        for key, program in list(self._registry.items()):
            dependencies = self._resolved_dependencies.get(key, ())
            if key in self._target_plan_keys:
                module_diagnostics = self._validate_code(program.code, dependencies=dependencies)
            else:
                names = reachable.get(key)
                if not names:
                    continue
                module_diagnostics = self._validate_code(
                    self._invoked_view(program.code, names),
                    dependencies=dependencies,
                )
            diagnostics = [*program.diagnostics, *module_diagnostics]
            scope = self._tentative_scope(key, program.code)
            self._registry[key] = replace(program, diagnostics=tuple(scope.mark(diagnostics)))

    def _tentative_scope(self, key: str, code: BasePicture) -> _TentativeScope:
        """What a finding in this program needs to stay final."""
        dependencies = self._resolved_dependencies.get(key, ())
        if key not in self._incomplete:
            return _TentativeScope(
                incomplete=False,
                incomplete_owners=frozenset(),
                definition_owners={},
                definitions_by_span={},
            )
        visible_datatypes, _, owners = self._visible_definitions(dependencies)
        return _TentativeScope(
            incomplete=True,
            incomplete_owners=self._closure(dependencies) & self._incomplete,
            definition_owners=owners,
            definitions_by_span=self._mapping_definitions(code, dependencies),
            type_graph=TypeGraph.from_datatypes([*code.datatype_defs, *visible_datatypes]),
        )

    def _mapping_definitions(
        self, code: BasePicture, dependencies: Sequence[str]
    ) -> dict[SourceSpan, _MappingDefinitions]:
        """The definitions each parameter mapping resolves through.

        A mapping depends on the module type it instantiates and on that module
        type's parameter datatypes: a parameter typed by a datatype from a
        skipped dependency cannot be checked against its real shape. The answer
        is per instance rather than per mapping, so it over-approximates a
        little; over-approximation can only keep a finding tentative.
        """
        visible: dict[str, ModuleTypeDef] = {}
        for moduletype in code.moduletype_defs:
            visible.setdefault(fold_identifier(moduletype.name), moduletype)
        for key in self._closure(dependencies):
            program = self._registry.get(key)
            if program is None:
                continue
            for moduletype in program.code.moduletype_defs:
                visible.setdefault(fold_identifier(moduletype.name), moduletype)
        definitions: dict[SourceSpan, _MappingDefinitions] = {}
        for node in _iter_moduletype_instances(code):
            moduletype_key = fold_identifier(node.moduletype_name)
            moduletype = visible.get(moduletype_key)
            datatypes = (
                frozenset(fold_identifier(parameter.datatype_text) for parameter in moduletype.moduleparameters)
                if moduletype is not None
                else frozenset[str]()
            )
            resolved = _MappingDefinitions(moduletype=moduletype_key, datatypes=datatypes)
            for mapping in node.parametermappings:
                if mapping.span is not None:
                    definitions.setdefault(mapping.span, resolved)
        return definitions

    def _validate_code(self, code: BasePicture, *, dependencies: Sequence[str]) -> tuple[Diagnostic, ...]:
        visible_datatypes, visible_moduletypes, _ = self._visible_definitions(dependencies)
        return validate_basepicture(
            code,
            external_datatypes=visible_datatypes,
            external_moduletype_defs=visible_moduletypes,
        )

    @staticmethod
    def _invoked_view(basepicture: BasePicture, names: set[str]) -> BasePicture:
        """A copy that contains only the invoked module types from one file."""
        selected = [moduletype for moduletype in basepicture.moduletype_defs if moduletype.name.casefold() in names]
        return replace(
            basepicture,
            moduletype_defs=selected,
            submodules=[],
            moduledefs=[],
            modulecodes=[],
            localvariables=[],
        )

    def _program_diagnostics(
        self,
        basepicture: BasePicture,
        *,
        dependencies: Sequence[str],
        library: str,
        file_name: str,
        key: str,
    ) -> tuple[Diagnostic, ...]:
        if self._validate is LoadValidation.NONE:
            return ()
        visible_datatypes, visible_moduletypes, _ = self._visible_definitions(dependencies)
        diagnostics = list(
            validate_basepicture(
                basepicture,
                external_datatypes=visible_datatypes,
                external_moduletype_defs=visible_moduletypes,
            )
        )
        diagnostics.extend(
            self._datecode_conflicts(
                basepicture,
                library=library,
                file_name=file_name,
                visible=self._visible_plan_keys(key),
            )
        )
        scope = self._tentative_scope(key, basepicture)
        return tuple(scope.mark(diagnostics))

    def _versions_in_scope(
        self,
        table: dict[str, dict[int, set[str]]],
        name: str,
        visible: frozenset[str],
    ) -> dict[int, set[str]] | None:
        """Datecodes declared for *name* by programs in *visible*."""
        entry = table.get(fold_identifier(name))
        if not entry:
            return None
        known: dict[int, set[str]] = {}
        for datecode, keys in entry.items():
            in_scope = keys & visible
            if in_scope:
                known[datecode] = {self._labels[key] for key in in_scope if key in self._labels}
        return known or None

    def _datecode_conflicts(
        self,
        basepicture: BasePicture,
        *,
        library: str,
        file_name: str,
        visible: frozenset[str],
    ) -> list[Diagnostic]:
        source_label = f"{library}/{file_name}"
        conflicts: list[Diagnostic] = []
        for moduletype in basepicture.moduletype_defs:
            conflict = _datecode_conflict(
                "moduletype",
                moduletype.name,
                moduletype.datecode,
                self._versions_in_scope(self._moduletype_versions, moduletype.name, visible),
                source_label=source_label,
                span=moduletype.declaration_span,
            )
            if conflict is not None:
                conflicts.append(conflict)
        for datatype in basepicture.datatype_defs:
            conflict = _datecode_conflict(
                "datatype",
                datatype.name,
                datatype.datecode,
                self._versions_in_scope(self._datatype_versions, datatype.name, visible),
                source_label=source_label,
                span=datatype.declaration_span,
            )
            if conflict is not None:
                conflicts.append(conflict)
        return conflicts

    def _remember_definitions(
        self,
        basepicture: BasePicture,
        *,
        library: str,
        file_name: str,
        program_key: str,
    ) -> None:
        self._labels[program_key] = f"{library}/{file_name}"
        for moduletype in basepicture.moduletype_defs:
            if moduletype.datecode is not None:
                self._moduletype_versions.setdefault(fold_identifier(moduletype.name), {}).setdefault(
                    moduletype.datecode, set()
                ).add(program_key)
        for datatype in basepicture.datatype_defs:
            if datatype.datecode is not None:
                self._datatype_versions.setdefault(fold_identifier(datatype.name), {}).setdefault(
                    datatype.datecode, set()
                ).add(program_key)

    def _read_deps(
        self,
        name: str,
        deps_path: Path | None,
        program_name: str,
        dependency: str | None,
    ) -> tuple[str, ...]:
        if deps_path is None:
            return ()
        try:
            return read_dependency_names(deps_path)
        except (OSError, UnicodeError) as exc:
            raise DependencyParseError(
                program_name,
                f"unable to read dependency file {deps_path.name} for {name!r}",
                dependency=dependency,
            ) from exc

    def _load_ast(self, code_path: Path, *, program_name: str, dependency: str | None) -> BasePicture:
        if self._ast_cache is not None:
            cached = self._ast_cache.load(code_path, self._mode.value)
            if cached is not None:
                self._dbg(f"Using cached AST for: {code_path}")
                return cached
        # Capture the source revision before reading it, so the entry written
        # below describes the bytes that were actually parsed.
        snapshot = source_snapshot(code_path)
        self._dbg(f"Parsing: {code_path}")
        try:
            basepicture = parse_source_file(code_path, debug=self._debug)
        except PARSE_FAILURES as exc:
            if dependency is None:
                raise ArtifactLoadError(program_name, f"failed to parse {code_path.name}") from exc
            raise DependencyParseError(
                program_name,
                f"failed to parse dependency {dependency!r}",
                dependency=dependency,
            ) from exc
        if self._ast_cache is not None:
            try:
                self._ast_cache.save(code_path, self._mode.value, basepicture, snapshot=snapshot)
            except OSError as exc:
                # The cache is an optimisation: a failed write must not turn a
                # successful parse into a load failure.
                self._dbg(f"Cache write failed for {code_path}: {exc}")
        return basepicture


def _moduletype_edges(
    programs: dict[str, SattLineProgram],
    visible_keys: frozenset[str],
) -> tuple[list[tuple[str, str]], dict[str, str], dict[str, str]]:
    """The instantiation edges among the definitions visible from one program.

    A node is one definition, identified by its owning program and folded name,
    so two programs may each define a type of the same name without becoming a
    cycle. Returns the edges plus the display name and owning program of every
    node the cycle report needs.
    """
    index: dict[str, list[tuple[str, ModuleTypeDef]]] = {}
    for visible_key in sorted(visible_keys):
        program = programs.get(visible_key)
        if program is None:
            # A planned body that did not assemble contributes no definitions.
            continue
        for moduletype in program.code.moduletype_defs:
            index.setdefault(fold_identifier(moduletype.name), []).append((visible_key, moduletype))
    labels: dict[str, str] = {}
    owners: dict[str, str] = {}
    edges: list[tuple[str, str]] = []

    def node_for(owner_key: str, moduletype: ModuleTypeDef) -> str:
        node = f"{owner_key}\x00{fold_identifier(moduletype.name)}"
        labels.setdefault(node, moduletype.name)
        owners.setdefault(node, programs[owner_key].name)
        return node

    for folded_name in sorted(index):
        for owner_key, moduletype in index[folded_name]:
            node = node_for(owner_key, moduletype)
            for reference in iter_moduletype_refs(moduletype.submodules):
                folded = fold_identifier(reference)
                candidates = index.get(folded, ())
                # A local definition wins, then any visible definition: the
                # check asks whether this closure's definitions instantiate
                # themselves, not whether every edge is load-order legal.
                local = [entry for entry in candidates if entry[0] == owner_key] or candidates
                for target_key, target in local:
                    edges.append((node, node_for(target_key, target)))
    return edges, labels, owners


def _set_origin(basepicture: BasePicture, *, file_name: str, library: str) -> None:
    basepicture.origin_file = file_name
    basepicture.origin_lib = library
    for moduletype in basepicture.moduletype_defs:
        moduletype.origin_file = file_name
        moduletype.origin_lib = library
    for datatype in basepicture.datatype_defs:
        datatype.origin_file = file_name
        datatype.origin_lib = library


def _datecode_conflict(
    kind: str,
    name: str,
    datecode: int | None,
    known: dict[int, set[str]] | None,
    *,
    source_label: str,
    span: SourceSpan | None,
) -> Diagnostic | None:
    if datecode is None or not known:
        return None
    others = {version: labels for version, labels in known.items() if version != datecode}
    if not others:
        return None
    detail = ", ".join(f"{version} in {', '.join(sorted(labels))}" for version, labels in sorted(others.items()))
    return Diagnostic(
        code=DiagnosticCode.DATECODE_CONFLICT,
        message=f"{kind} {name!r} datecode {datecode} in {source_label} conflicts with {detail}",
        span=span,
    )


def _load_graphics(
    debug: Callable[[str], None],
    graphics_path: Path,
    *,
    program_name: str,
    dependency: str | None,
    name: str,
) -> GraphicsModel:
    debug(f"Parsing graphics: {graphics_path}")
    try:
        return parse_graphics_file(graphics_path)
    except (OSError, UnicodeError, GraphicsParseError) as exc:
        if dependency is None:
            raise ArtifactLoadError(
                program_name,
                f"failed to read graphics companion {graphics_path.name} for {name!r}: {exc}",
            ) from exc
        raise DependencyParseError(
            program_name,
            f"failed to read graphics companion for dependency {dependency!r}: {exc}",
            dependency=dependency,
        ) from exc


__all__ = ["ProjectLoader", "read_dependency_names"]
