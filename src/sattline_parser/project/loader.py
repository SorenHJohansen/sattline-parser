"""Recursive program loading and dependency resolution (plan §3-§7).

Phase 3 wires ``SattLineProject.load`` onto the parser layers:

* ``read_dependency_names`` parses ``.l`` / ``.z`` dependency files: each line
  is one declared dependency name (trimmed, blank lines ignored).
* A recursive visitor resolves dependencies requester-relative to the directory
  of the declaring dependency file.
* An identity registry keyed by casefolded names guarantees every program is
  visited, parsed, and memoized exactly once per load.
* Cycles are represented as edges in the derived dependency graph, never raised.
* Strict loading fails fast; non-strict loading records the failing program as
  absent and continues.

Phase 4 additionally wires each program's ``.g`` / ``.y`` graphics companion
(resolved as a same-directory sibling of the code file and parsed into a
``GraphicsModel``); companion-read failures map onto load errors with the same
strict/non-strict behavior.

The optional ``cache_dir`` enables the parser-owned ``FileLookupCache`` and
``FileASTCache`` so discovery and parsed ASTs survive across loads.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from lark.exceptions import LarkError

from sattline_parser.api import parse_source_file, read_text_with_fallback
from sattline_parser.models.ast_model import BasePicture

from .ast_cache import FileASTCache
from .discovery import ProjectLookup
from .errors import ArtifactLoadError, DependencyNotFoundError, DependencyParseError, ProjectLoadError
from .graphics_parsing import parse_graphics_file, resolve_graphics_companion_path
from .lookup_cache import FileLookupCache
from .models import GraphicsModel, LoadMode, ProgramFormat, SattLineProgram

_PARSE_FAILURES = (
    LarkError,  # grammar/matcher/framework/transform failures
    ValueError,  # preprocess and transformer value errors
    TypeError,
    AttributeError,
    RuntimeError,
    LookupError,
    UnicodeError,
    OSError,
)


def read_dependency_names(deps_path: Path) -> tuple[str, ...]:
    """Read a ``.l`` / ``.z`` dependency file into declared dependency names.

    Each non-blank line is one dependency name; lines are trimmed, blank lines
    are ignored, and declaration order is preserved.
    """
    text = read_text_with_fallback(deps_path)
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
    ) -> None:
        self._lookup_cache = FileLookupCache(cache_dir) if cache_dir is not None else None
        self._ast_cache = FileASTCache(cache_dir) if cache_dir is not None else None
        self._lookup = ProjectLookup(roots, mode, cache=self._lookup_cache, debug=debug)
        self._mode = mode
        self._strict = strict
        self._debug = debug
        self._registry: dict[str, SattLineProgram] = {}
        self._loading: set[str] = set()

    def _dbg(self, message: str) -> None:
        if self._debug is not None:
            self._debug(message)

    def resolve(self, targets: Sequence[str]) -> dict[str, SattLineProgram]:
        for target in targets:
            self._visit(target, requester_dir=None, declared_by=None)
        if self._lookup_cache is not None:
            self._lookup_cache.flush()
        return self._registry

    def _visit(self, name: str, *, requester_dir: Path | None, declared_by: str | None) -> None:
        key = name.casefold()
        if key in self._registry or key in self._loading:
            return
        self._loading.add(key)
        try:
            self._load_one(name, requester_dir=requester_dir, declared_by=declared_by)
        finally:
            self._loading.discard(key)

    def _load_one(self, name: str, *, requester_dir: Path | None, declared_by: str | None) -> None:
        program_name = declared_by if declared_by is not None else name
        dependency = None if declared_by is None else name
        try:
            self._dbg(f"Visiting: {name}")
            code_path = self._lookup.find_code(name, requester_dir=requester_dir)
            if code_path is None:
                raise DependencyNotFoundError(
                    program_name,
                    f"missing code file for {name!r}",
                    dependency=dependency,
                )
            deps_path = self._lookup.find_deps(name, requester_dir=requester_dir)
            dep_requester = deps_path.parent if deps_path is not None else requester_dir
            dep_names = self._read_deps(name, deps_path, program_name, dependency)
            for dep in dep_names:
                self._visit(dep, requester_dir=dep_requester, declared_by=name)
            basepicture = self._load_ast(code_path, program_name=program_name, dependency=dependency)
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
            )
            self._registry[name.casefold()] = program
        except ProjectLoadError:
            if self._strict:
                raise

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
        except OSError as exc:
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
        except _PARSE_FAILURES as exc:
            if dependency is None:
                raise ArtifactLoadError(program_name, f"failed to parse {code_path.name}") from exc
            raise DependencyParseError(
                program_name,
                f"failed to parse dependency {dependency!r}",
                dependency=dependency,
            ) from exc
        if self._ast_cache is not None:
            self._ast_cache.save(code_path, self._mode.value, basepicture)
        return basepicture


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
    except OSError as exc:
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
