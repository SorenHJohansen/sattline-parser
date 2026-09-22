"""SattLine artifact discovery across ordered search roots.

Phase 2 (plan §5): per-root indexing, requester-relative ordered lookup, the
per-artifact draft→official fallback, and the parser-owned file-lookup cache
integration. This is the parser's file-discovery layer; program loading and
dependency resolution build on it in later phases.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from .formats import ArtifactKind, candidate_extensions
from .lookup_cache import FileLookupCache
from .models import LoadMode


def _resolved(path: Path | None) -> Path | None:
    if path is None:
        return None
    try:
        return path.resolve()
    except OSError:
        return path


def _lookup_path_key(path: Path) -> str:
    return str(_resolved(path)).casefold()


def _is_relative_to(path: Path | None, root: Path | None) -> bool:
    resolved_path = _resolved(path)
    resolved_root = _resolved(root)
    if resolved_path is None or resolved_root is None:
        return False
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return False
    return True


def _first_branch_under(root: Path, path: Path | None) -> str | None:
    resolved_root = _resolved(root)
    resolved_path = _resolved(path)
    if resolved_root is None or resolved_path is None:
        return None
    try:
        relative_parts = resolved_path.relative_to(resolved_root).parts
    except ValueError:
        return None
    return relative_parts[0] if relative_parts else None


def _is_allowed_base(roots: Sequence[Path], base: Path) -> bool:
    allowed = {_lookup_path_key(root) for root in roots}
    return _lookup_path_key(base) in allowed


class SourceIndex:
    """Per-root artifact index of ``stem.casefold() -> {ext -> Path}``.

    Only code and dependency extensions are indexed — the same set SattLint
    indexes. Graphics companions are resolved via their code path (Phase 4) and
    never appear here.
    """

    INDEXED_EXTENSIONS = frozenset({".s", ".x", ".l", ".z"})

    def __init__(self, roots: Sequence[Path]) -> None:
        self._roots = tuple(Path(root) for root in roots)
        self._indexes: dict[Path, dict[str, dict[str, Path]]] = {}

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def _get_base_index(self, base: Path) -> dict[str, dict[str, Path]]:
        if base in self._indexes:
            return self._indexes[base]
        index: dict[str, dict[str, Path]] = {}
        if not base.exists() or not base.is_dir():
            self._indexes[base] = index
            return index
        for entry in base.iterdir():
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in self.INDEXED_EXTENSIONS:
                continue
            stem = entry.stem.casefold()
            index.setdefault(stem, {})[ext] = entry
        self._indexes[base] = index
        return index

    def find_in_index(self, *, base: Path, name: str, extensions: Sequence[str]) -> Path | None:
        entries = self._get_base_index(base).get(name.casefold())
        if not entries:
            return None
        for ext in extensions:
            path = entries.get(ext)
            if path is not None:
                return path
        return None

    def add(self, *, base: Path, name: str, path: Path) -> None:
        index = self._get_base_index(base)
        index.setdefault(name.casefold(), {})[path.suffix.lower()] = path

    def prime(self) -> None:
        for base in self._roots:
            self._get_base_index(base)


def shared_lookup_root_for(requester_dir: Path | None, roots: Sequence[Path]) -> Path | None:
    """The shared cluster root hosting the requester and >= 2 sibling roots.

    Walks up from the requester to the highest ancestor under which at least two
    other roots land in distinct first-level branches; ``None`` when no such
    cluster exists. Mirrors SattLint's ``_shared_lookup_root_for``
    (loader_lookup.py).
    """
    requester = _resolved(requester_dir)
    if requester is None:
        return None
    candidate_dirs = [resolved for root in roots if (resolved := _resolved(root)) is not None and resolved != requester]
    current = requester
    while True:
        branches: set[str] = set()
        for source_dir in candidate_dirs:
            if not _is_relative_to(source_dir, current):
                continue
            branch = _first_branch_under(current, source_dir)
            if branch is None:
                continue
            branches.add(branch)
            if len(branches) > 1:
                return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def ordered_lookup_bases(roots: Sequence[Path], requester_dir: Path | None) -> tuple[Path, ...]:
    """Ordered lookup bases honoring the requester and shared-cluster order.

    Precedence: the requester itself (when it is a configured root), then roots
    sharing the requester's cluster — same branch before sibling branches — then
    every remaining root in configured order. The terminal (last) root acts as
    the fallback library and is always tried last, mirroring how SattLint keeps
    the ABB library terminal (loader_lookup.py).
    """
    resolved_roots = [resolved for root in roots if (resolved := _resolved(root)) is not None]
    requester = _resolved(requester_dir)
    ordered: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = _lookup_path_key(path)
        if key in seen:
            return
        seen.add(key)
        ordered.append(path)

    if requester is not None and _is_allowed_base(resolved_roots, requester):
        add(requester)

    terminal_root = resolved_roots[-1] if resolved_roots else None
    cluster_root = shared_lookup_root_for(requester, resolved_roots) if requester is not None else None
    if cluster_root is not None and requester is not None:
        requester_branch = _first_branch_under(cluster_root, requester)
        same_branch: list[Path] = []
        sibling_branch: list[Path] = []
        for resolved in resolved_roots:
            if resolved == requester or (terminal_root is not None and resolved == terminal_root):
                continue
            if not _is_relative_to(resolved, cluster_root):
                continue
            branch = _first_branch_under(cluster_root, resolved)
            if requester_branch is not None and branch == requester_branch:
                same_branch.append(resolved)
            else:
                sibling_branch.append(resolved)
        for source_dir in sorted(same_branch, key=_lookup_path_key):
            add(source_dir)
        for source_dir in sorted(sibling_branch, key=_lookup_path_key):
            add(source_dir)

    for resolved in resolved_roots:
        add(resolved)
    return tuple(ordered)


class ProjectLookup:
    """Resolves a program's artifacts across ordered roots.

    The mode selects candidate extensions; each artifact falls back per artifact
    (``.s`` → ``.x`` etc. in draft mode) and across roots in
    ``ordered_lookup_bases`` order. An optional parser-owned ``FileLookupCache``
    records resolutions and is consulted after the ordered scan.
    """

    def __init__(
        self,
        roots: Sequence[Path],
        mode: LoadMode,
        *,
        index: SourceIndex | None = None,
        cache: FileLookupCache | None = None,
        debug: Callable[[str], None] | None = None,
    ) -> None:
        self._roots = tuple(Path(root) for root in roots)
        self._mode = mode
        self._index = index if index is not None else SourceIndex(self._roots)
        self._cache = cache
        self._debug = debug

    def _dbg(self, message: str) -> None:
        if self._debug is not None:
            self._debug(message)

    def _find_in_ordered_bases_without_cache(
        self,
        name: str,
        extensions: Sequence[str],
        *,
        requester_dir: Path | None,
        kind: str,
    ) -> Path | None:
        for base in ordered_lookup_bases(self._roots, requester_dir):
            indexed = self._index.find_in_index(base=base, name=name, extensions=extensions)
            if indexed is not None:
                self._dbg(f"Using ordered lookup file: {indexed}")
                self._remember(kind, name, base, indexed.suffix.lower())
                return indexed
            for ext in extensions:
                candidate = base / f"{name}{ext}"
                if candidate.exists():
                    self._dbg(f"Using ordered lookup file: {candidate}")
                    self._remember(kind, name, base, ext)
                    self._index.add(base=base, name=name, path=candidate)
                    return candidate
        return None

    def _find_in_cached_base(
        self,
        kind: str,
        name: str,
        extensions: Sequence[str],
        *,
        base_allowed: Callable[[Path], bool],
    ) -> Path | None:
        if self._cache is None:
            return None
        cached = self._cache.get(kind, name, self._mode.value)
        if not cached:
            return None
        base = Path(cached["base_dir"])
        if not base or not base_allowed(base):
            self._cache.forget(kind, name, self._mode.value)
            return None
        cached_ext = cached["ext"]
        ordered_exts = [cached_ext] if cached_ext in extensions else []
        ordered_exts.extend(ext for ext in extensions if ext != cached_ext)
        for ext in ordered_exts:
            path = base / f"{name}{ext}"
            if path.exists():
                self._dbg(f"Using cached {kind} file: {path}")
                return path
        self._cache.forget(kind, name, self._mode.value)
        return None

    def _remember(self, kind: str, name: str, base: Path, ext: str) -> None:
        if self._cache is not None:
            self._cache.set(kind, name, self._mode.value, base, ext)

    def find(self, name: str, kind: ArtifactKind, *, requester_dir: Path | None = None) -> Path | None:
        """Resolve ``name`` of ``kind`` across the ordered roots, or ``None``."""
        extensions = candidate_extensions(kind, self._mode)
        kind_value = kind.value
        ordered = self._find_in_ordered_bases_without_cache(
            name, extensions, requester_dir=requester_dir, kind=kind_value
        )
        if ordered is not None:
            return ordered
        cached = self._find_in_cached_base(
            kind_value, name, extensions, base_allowed=lambda base: _is_allowed_base(self._roots, base)
        )
        if cached is not None:
            return cached
        for base in self._roots:
            indexed = self._index.find_in_index(base=base, name=name, extensions=extensions)
            if indexed is not None:
                self._dbg(f"Using {kind_value} file: {indexed}")
                self._remember(kind_value, name, base, indexed.suffix.lower())
                return indexed
            for ext in extensions:
                path = base / f"{name}{ext}"
                if path.exists():
                    self._dbg(f"Using {kind_value} file: {path}")
                    self._remember(kind_value, name, base, ext)
                    self._index.add(base=base, name=name, path=path)
                    return path
        self._dbg(f"No {kind_value} file found for {name!r} in mode={self._mode.value}")
        return None

    def find_code(self, name: str, *, requester_dir: Path | None = None) -> Path | None:
        return self.find(name, ArtifactKind.CODE, requester_dir=requester_dir)

    def find_deps(self, name: str, *, requester_dir: Path | None = None) -> Path | None:
        return self.find(name, ArtifactKind.DEPS, requester_dir=requester_dir)


__all__ = [
    "ProjectLookup",
    "SourceIndex",
    "ordered_lookup_bases",
    "shared_lookup_root_for",
]
