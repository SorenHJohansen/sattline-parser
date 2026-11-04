"""Recursive program loading, dependency resolution, and project validation.

The loader resolves a target across ordered roots, reads its dependency sidecar,
loads dependencies first, parses the body, and (when ``validate=FULL``) runs the
single-file validator with the definitions visible from already-loaded programs.
``validate=INVOKED`` validates each target in full and limits dependency files
to the module types that target invokes, transitively.

Post-order is an invariant: the registry is built dependencies-first, so a
program's diagnostics are computed against a complete prefix of its closure.
The loader asserts that invariant for acyclic loads. Invoked-scope validation
runs after the graph is complete because it needs the whole invocation graph.

``tentative`` marking is owned here. When a non-strict load skips a dependency,
every program whose closure includes that dependency gets tentative findings for
rules that depend on external definitions. Purely local findings stay final.

Strict loading fails fast on missing or unparseable artifacts. Validation
findings never raise; ``strict`` governs load failures only.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from sattline_parser.errors import PARSE_FAILURES
from sattline_parser.models.ast_model import BasePicture, DataType, ModuleTypeDef, SourceSpan
from sattline_parser.names import fold_identifier
from sattline_parser.source_io import parse_source_file, read_text_cp1252
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode

from ._cycles import canonical_cycle, cycle_key
from .ast_cache import FileASTCache
from .discovery import ProjectLookup
from .errors import ArtifactLoadError, DependencyNotFoundError, DependencyParseError, ProjectLoadError
from .graphics_parsing import parse_graphics_file, resolve_graphics_companion_path
from .lookup_cache import FileLookupCache
from .models import (
    GraphicsModel,
    LoadDiagnostic,
    LoadDiagnosticKind,
    LoadMode,
    LoadValidation,
    ProgramFormat,
    SattLineProgram,
    SidecarState,
)
from .reachability import invoked_moduletypes

#: Findings that depend on definitions outside the program itself. They become
#: tentative when a part of the closure failed to load.
_TENTATIVE_CODES = frozenset(
    {
        DiagnosticCode.UNKNOWN_DATATYPE_NAME,
        DiagnosticCode.UNKNOWN_MODULETYPE_NAME,
        DiagnosticCode.PARAM_TRANSFER_TYPE_MISMATCH,
        DiagnosticCode.PARAMETER_MAPPING_TYPE_MISMATCH,
        DiagnosticCode.PARAMETER_MAPPING_TARGET_UNKNOWN,
        DiagnosticCode.DATECODE_CONFLICT,
    }
)


def _mark_tentative(diagnostics: Sequence[Diagnostic]) -> list[Diagnostic]:
    """Mark the findings that depend on an incomplete closure as tentative."""
    return [replace(item, tentative=True) if item.code in _TENTATIVE_CODES else item for item in diagnostics]


def read_dependency_names(deps_path: Path) -> tuple[str, ...]:
    """Read a ``.l`` / ``.z`` dependency file into declared dependency names.

    Each non-blank line is one dependency name; lines are trimmed, blank lines
    are ignored, and declaration order is preserved.
    """
    text = read_text_cp1252(deps_path)
    return tuple(line.strip() for line in text.splitlines() if line.strip())


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
    ) -> None:
        self._lookup_cache = FileLookupCache(cache_dir) if cache_dir is not None else None
        self._ast_cache = FileASTCache(cache_dir) if cache_dir is not None else None
        self._lookup = ProjectLookup(roots, mode, cache=self._lookup_cache, debug=debug)
        self._mode = mode
        self._strict = strict
        self._debug = debug
        self._validate = validate
        self._registry: dict[str, SattLineProgram] = {}
        self._loading: list[str] = []
        self._diagnostics: list[LoadDiagnostic] = []
        self._cycles: list[tuple[str, ...]] = []
        self._cycle_keys: set[tuple[str, ...]] = set()
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

    @property
    def cycles(self) -> tuple[tuple[str, ...], ...]:
        """Dependency cycle paths recorded during this load, in discovery order."""
        return tuple(self._cycles)

    def _diagnose(self, kind: LoadDiagnosticKind, program: str, detail: str, path: Path | None = None) -> None:
        diagnostic = LoadDiagnostic(kind=kind, program=program, detail=detail, path=path)
        if diagnostic not in self._diagnostics:
            self._diagnostics.append(diagnostic)

    def resolve(self, targets: Sequence[str]) -> dict[str, SattLineProgram]:
        try:
            for target in targets:
                self._visit(target, requester_dir=None, declared_by=None)
            if not self._cycles:
                self._assert_registry_post_order()
            if self._validate is LoadValidation.INVOKED:
                self._validate_invoked(targets)
            return self._registry
        finally:
            if self._lookup_cache is not None:
                self._lookup_cache.flush()

    def _assert_registry_post_order(self) -> None:
        """Assert that every loaded dependency precedes its consumer."""
        seen: set[str] = set()
        for key, program in self._registry.items():
            for dependency in program.dependencies:
                dependency_key = dependency.casefold()
                if dependency_key in self._registry and dependency_key not in seen:
                    raise RuntimeError(
                        f"loader registry is not in post-order: {program.name!r} precedes dependency {dependency!r}"
                    )
            seen.add(key)

    def _visit(self, name: str, *, requester_dir: Path | None, declared_by: str | None) -> None:
        key = name.casefold()
        if key in self._registry:
            return
        if key in self._loading:
            # A dependency loop. The loader reports it through its library-error
            # handling and an operator may continue past it, so it becomes a
            # diagnostic and the graph keeps the edge. The path is also recorded
            # as data for consumers that want to display it.
            start = self._loading.index(key)
            cycle = canonical_cycle((*self._loading[start:], key))
            identity = cycle_key(cycle)
            if identity not in self._cycle_keys:
                self._cycle_keys.add(identity)
                self._cycles.append(cycle)
                self._diagnose(
                    LoadDiagnosticKind.DEPENDENCY_CYCLE,
                    declared_by or name,
                    f"dependency cycle: {' -> '.join(cycle)}",
                )
            return
        self._loading.append(key)
        try:
            self._load_one(name, requester_dir=requester_dir, declared_by=declared_by)
        finally:
            self._loading.pop()

    def _load_one(self, name: str, *, requester_dir: Path | None, declared_by: str | None) -> None:
        program_name = declared_by if declared_by is not None else name
        dependency = None if declared_by is None else name
        key = name.casefold()
        try:
            self._dbg(f"Visiting: {name}")
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
                stray = self._lookup.find_deps(name, requester_dir=requester_dir)
                if stray is not None:
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
            dep_requester = deps_path.parent if deps_path is not None else code_path.parent
            dep_names = self._read_deps(name, deps_path, program_name, dependency)
            if deps_path is not None:
                sidecar = SidecarState.PRESENT if dep_names else SidecarState.EMPTY
                if sidecar is SidecarState.EMPTY:
                    self._diagnose(
                        LoadDiagnosticKind.SIDECAR_EMPTY,
                        program_name,
                        f"sidecar {deps_path.name!r} declares no dependencies",
                        deps_path,
                    )
            for dep in dep_names:
                self._visit(dep, requester_dir=dep_requester, declared_by=name)
            if any(dep.casefold() in self._incomplete for dep in dep_names):
                self._incomplete.add(key)

            basepicture = self._load_ast(code_path, program_name=program_name, dependency=dependency)
            _set_origin(basepicture, file_name=code_path.name, library=library)
            if self._validate is LoadValidation.INVOKED:
                # Module diagnostics need the whole graph. Datecode findings
                # belong to an explicitly selected program; a library import is
                # not the place to report its own version drift.
                diagnostics = (
                    ()
                    if declared_by is not None
                    else tuple(
                        self._datecode_conflicts(
                            basepicture,
                            library=library,
                            file_name=code_path.name,
                            visible=self._visible_program_keys(key, dep_names),
                        )
                    )
                )
            else:
                diagnostics = self._program_diagnostics(
                    basepicture,
                    dependencies=dep_names,
                    library=library,
                    file_name=code_path.name,
                    key=key,
                )
            self._remember_definitions(basepicture, library=library, file_name=code_path.name, program_key=key)

            graphics_path = resolve_graphics_companion_path(code_path, mode=self._mode)
            graphics = (
                _load_graphics(self._dbg, graphics_path, program_name=program_name, dependency=dependency, name=name)
                if graphics_path is not None
                else None
            )
            program = SattLineProgram(
                name=name,
                code=basepicture,
                graphics=graphics,
                dependencies=dep_names,
                format=ProgramFormat(
                    mode=self._mode,
                    code_ext=code_path.suffix.lower(),
                    graphics_ext=graphics_path.suffix.lower() if graphics_path is not None else None,
                    deps_ext=deps_path.suffix.lower() if deps_path is not None else None,
                ),
                source_path=code_path,
                deps_path=deps_path,
                sidecar=sidecar,
                library=library,
                resolved_base=resolved_base,
                diagnostics=diagnostics,
            )
            self._registry[key] = program
        except ProjectLoadError as exc:
            if self._strict:
                raise
            # Non-strict loading must not be silent: an agent or a CI job has to
            # be able to tell that a program is missing from the result.
            self._incomplete.add(key)
            self._diagnose(LoadDiagnosticKind.LOAD_SKIPPED, name, f"skipped {name!r}: {exc}")

    def _visible_definitions(
        self, dependencies: tuple[str, ...]
    ) -> tuple[tuple[DataType, ...], tuple[ModuleTypeDef, ...]]:
        """Definitions from this program's transitive dependency closure.

        The registry is dependency-first, so filtering it by the closure keeps
        a deterministic order. Using the whole registry here would let an
        unrelated target's types hide an unknown-name finding.
        """
        closure: set[str] = set()
        pending = [dependency.casefold() for dependency in dependencies]
        while pending:
            key = pending.pop()
            if key in closure:
                continue
            closure.add(key)
            program = self._registry.get(key)
            if program is not None:
                pending.extend(dependency.casefold() for dependency in program.dependencies)
        datatypes: list[DataType] = []
        moduletypes: list[ModuleTypeDef] = []
        for key, program in self._registry.items():
            if key not in closure:
                continue
            datatypes.extend(program.code.datatype_defs)
            moduletypes.extend(program.code.moduletype_defs)
        return tuple(datatypes), tuple(moduletypes)

    def _validate_invoked(self, targets: Sequence[str]) -> None:
        """Add diagnostics for the module types each target actually invokes."""
        target_keys = {target.casefold() for target in targets}
        reachable = invoked_moduletypes(self._registry, targets)
        for key, program in list(self._registry.items()):
            if key in target_keys:
                module_diagnostics = self._validate_code(program.code, dependencies=program.dependencies)
            else:
                names = reachable.get(key)
                if not names:
                    continue
                module_diagnostics = self._validate_code(
                    self._invoked_view(program.code, names),
                    dependencies=program.dependencies,
                )
            diagnostics = [*program.diagnostics, *module_diagnostics]
            if key in self._incomplete:
                diagnostics = _mark_tentative(diagnostics)
            self._registry[key] = replace(program, diagnostics=tuple(diagnostics))

    def _validate_code(self, code: BasePicture, *, dependencies: tuple[str, ...]) -> tuple[Diagnostic, ...]:
        visible_datatypes, visible_moduletypes = self._visible_definitions(dependencies)
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
            parse_tree=None,
        )

    def _program_diagnostics(
        self,
        basepicture: BasePicture,
        *,
        dependencies: tuple[str, ...],
        library: str,
        file_name: str,
        key: str,
    ) -> tuple[Diagnostic, ...]:
        if self._validate is LoadValidation.NONE:
            return ()
        visible_datatypes, visible_moduletypes = self._visible_definitions(dependencies)
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
                visible=self._visible_program_keys(key, dependencies),
            )
        )
        if key in self._incomplete:
            diagnostics = _mark_tentative(diagnostics)
        return tuple(diagnostics)

    def _visible_program_keys(self, key: str, dependencies: Sequence[str]) -> frozenset[str]:
        """Keys of every program *key* can see: itself plus its transitive deps."""
        visible = {key}
        seen = {key}
        pending = [dependency.casefold() for dependency in dependencies]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            program = self._registry.get(current)
            if program is None:
                # A missing dependency makes the caller incomplete; it cannot
                # contribute a definition to the closure.
                continue
            visible.add(current)
            pending.extend(dependency.casefold() for dependency in program.dependencies)
        return frozenset(visible)

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
                self._ast_cache.save(code_path, self._mode.value, basepicture)
            except OSError as exc:
                # The cache is an optimisation: a failed write must not turn a
                # successful parse into a load failure.
                self._dbg(f"Cache write failed for {code_path}: {exc}")
        return basepicture


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
    if datecode is None or not known or datecode in known:
        return None
    detail = ", ".join(f"{version} in {', '.join(sorted(labels))}" for version, labels in sorted(known.items()))
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
    except (OSError, UnicodeError) as exc:
        if dependency is None:
            raise ArtifactLoadError(
                program_name,
                f"failed to read graphics companion {graphics_path.name} for {name!r}",
            ) from exc
        raise DependencyParseError(
            program_name,
            f"failed to read graphics companion for dependency {dependency!r}",
            dependency=dependency,
        ) from exc


__all__ = ["ProjectLoader", "read_dependency_names"]
