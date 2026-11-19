"""SattLine artifact discovery across an ordered search path.

Per-root indexing, ordered lookup, the per-artifact draft→official fallback, and
the parser-owned file-lookup cache integration. The caller's root order is the
lookup order: an earlier root wins, exactly like the path list a SattLine
installation searches. This is the file-discovery layer; program loading and
dependency resolution build on it.
"""

from __future__ import annotations

import ntpath
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import regex

from sattline_parser.grammar import constants as grammar_constants
from sattline_parser.names import fold_identifier

from .errors import ProjectLoadError
from .formats import (
    ALL_CODE_EXTENSIONS,
    ALL_DEPS_EXTENSIONS,
    ArtifactKind,
    candidate_extensions,
    deps_extensions_for_code,
)
from .identity import ArtifactIdentity, UnitIdentity
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
    """The filesystem identity of *path*, for comparing two directories.

    This is filesystem identity, not language identity: two roots are the same
    root when the platform says their resolved paths are the same. On a
    case-sensitive filesystem ``/lib`` and ``/Lib`` are different directories,
    so the key must not case-fold; on Windows the platform comparison is
    case-insensitive. Identifier comparison is a separate question and always
    uses :func:`sattline_parser.names.fold_identifier`.
    """
    return ArtifactIdentity.of(path).key


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


def _is_allowed_base(roots: Sequence[Path], base: Path) -> bool:
    allowed = {_lookup_path_key(root) for root in roots}
    return _lookup_path_key(base) in allowed


#: A dependency name is a bare unit name, never a path. The stat fallback and
#: the sidecar lookup build ``base / f"{name}{ext}"``, so the name is validated
#: against the language's own identifier character set rather than a short
#: blacklist. That rejects separators, drive/ADS colons, UNC prefixes, parent
#: references, control characters, and the Windows-invalid filename characters
#: in one rule.
#:
#: The length of a declared identifier is a language rule reported by
#: ``SL-V038`` at the declaration, not a resolution rule. Capping it here made a
#: unit whose name is 21 characters unresolvable, so this guard covers the
#: character set and the Windows device names only.
_NAME_CHARSET = grammar_constants.GRAMMAR_CHARSET_NAME
_UNIT_NAME_RE = regex.compile(rf"[{_NAME_CHARSET}]+\Z")
_IS_WINDOWS = os.name == "nt"
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
    }
)


def is_unit_name(name: str) -> bool:
    """Whether *name* is a bare unit name that can resolve inside a lookup base.

    The resolver and default target discovery share this one rule, so a file
    whose stem cannot be a unit name is never offered as a target. The same
    predicate refuses separators, drive or alternate-stream colons, UNC
    prefixes, parent references, control characters, and the Windows-invalid
    filename characters on every platform.
    """
    if _UNIT_NAME_RE.fullmatch(name) is None:
        return False
    # Windows reserves device names even when the identifier itself is legal.
    # A POSIX unit named CON is a normal file and must keep resolving there.
    return not _IS_WINDOWS or name.upper() not in _WINDOWS_RESERVED_NAMES


@dataclass(frozen=True, slots=True)
class NameCollision:
    """Two or more files in one root that the language considers one unit.

    A collision means the filesystem holds more than one artifact for one unit
    name and extension. ``paths`` is in the index's deterministic order, so
    ``paths[0]`` is the file that resolves and the rest are unreachable through
    the index.
    """

    base: Path
    folded: str
    extension: str
    paths: tuple[Path, ...]

    @property
    def winner(self) -> Path:
        """The file the index resolves for this name."""
        return self.paths[0]


class SourceIndex:
    """Per-root artifact index of ``fold_identifier(stem) -> {ext -> Path}``.

    Only code and dependency extensions are indexed. Graphics companions are
    resolved via their code path and never appear here.

    The key is language identity (:func:`sattline_parser.names.fold_identifier`),
    not Unicode case folding. ``Straße`` and ``STRASSE`` are two entries, so a
    request for one never returns the other even though ``str.casefold`` equates
    them. Case differences the language folds, such as ``Util`` and ``UTIL``,
    do share one entry; when a root holds both files, the first in sorted name
    order wins and the pair is recorded as a :class:`NameCollision`.
    """

    INDEXED_EXTENSIONS = ALL_CODE_EXTENSIONS | ALL_DEPS_EXTENSIONS

    def __init__(self, roots: Sequence[Path]) -> None:
        self._roots = tuple(Path(root) for root in roots)
        self._indexes: dict[Path, dict[str, dict[str, Path]]] = {}
        self._collisions: dict[Path, dict[tuple[str, str], NameCollision]] = {}
        self._unusable: dict[Path, tuple[Path, ...]] = {}

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    @property
    def collisions(self) -> tuple[NameCollision, ...]:
        """Every recorded name collision, in base then name order."""
        return tuple(
            collision for base in sorted(self._collisions) for _key, collision in sorted(self._collisions[base].items())
        )

    def _get_base_index(self, base: Path) -> dict[str, dict[str, Path]]:
        if base in self._indexes:
            return self._indexes[base]
        index: dict[str, dict[str, Path]] = {}
        collisions: dict[tuple[str, str], NameCollision] = {}
        unusable: list[Path] = []
        try:
            present = base.exists() and base.is_dir()
            # Sorted so the collision winner does not depend on directory order.
            entries = sorted(base.iterdir(), key=lambda entry: entry.name) if present else []
        except OSError as exc:
            # A configured root that cannot be read is an input problem, not an
            # internal error: report it as a load failure about that root.
            raise ProjectLoadError(
                base.name or str(base),
                f"cannot read {base}: {exc.strerror or exc}",
            ) from exc
        for entry in entries:
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in self.INDEXED_EXTENSIONS:
                continue
            if ext in ALL_CODE_EXTENSIONS and not is_unit_name(entry.stem):
                # The resolver refuses this name, so the file can never be a
                # target. Keep the path so the planner can report it as a
                # skipped file instead of failing the load on it.
                unusable.append(entry)
            folded = UnitIdentity.of(entry.stem).key
            bucket = index.setdefault(folded, {})
            existing = bucket.get(ext)
            if existing is None:
                bucket[ext] = entry
                continue
            previous = collisions.get((folded, ext))
            paths = (*previous.paths, entry) if previous is not None else (existing, entry)
            collisions[(folded, ext)] = NameCollision(base=base, folded=folded, extension=ext, paths=paths)
        self._indexes[base] = index
        self._collisions[base] = collisions
        self._unusable[base] = tuple(unusable)
        return index

    def find_in_index(self, *, base: Path, name: str, extensions: Sequence[str]) -> Path | None:
        entries = self._get_base_index(base).get(UnitIdentity.of(name).key)
        if not entries:
            return None
        for ext in extensions:
            path = entries.get(ext)
            if path is not None:
                return path
        return None

    def collisions_for_base(self, base: Path, name: str) -> tuple[NameCollision, ...]:
        """Name collisions recorded for *name* in *base*, one per extension."""
        self._get_base_index(base)
        folded = UnitIdentity.of(name).key
        return tuple(
            collision
            for (folded_name, _ext), collision in sorted(self._collisions.get(base, {}).items())
            if folded_name == folded
        )

    def unusable_code_files(self, base: Path) -> tuple[Path, ...]:
        """Code files in *base* whose stems are not unit names, in name order.

        The resolver refuses such a name on every platform, so the file can
        never resolve as a unit. It is recorded here rather than raised, because
        the load reports it as a skipped file and carries on.
        """
        self._get_base_index(base)
        return self._unusable.get(base, ())

    def add(self, *, base: Path, name: str, path: Path) -> None:
        index = self._get_base_index(base)
        index.setdefault(UnitIdentity.of(name).key, {})[path.suffix.lower()] = path


def ordered_lookup_bases(roots: Sequence[Path]) -> tuple[Path, ...]:
    """The lookup path, in the caller's order, with each library present once.

    Earlier entries win. A repeated root is dropped, keeping its first position,
    so ``[A, B, A]`` searches ``A`` then ``B``. A root whose directory name
    matches an earlier root under the language name table is dropped as a
    whole, because the SattLine loading path holds one library per name: the
    first library of a given name is the only one the session can open. Its
    units are not merged with the shadowed root, so a later library contributes
    nothing, including units the earlier one does not define. A root with no
    directory name, such as a filesystem or drive root, is compared by path
    only.
    """
    ordered: list[Path] = []
    seen_paths: set[str] = set()
    seen_names: set[str] = set()
    for resolved in (path for root in roots if (path := _resolved(root)) is not None):
        key = _lookup_path_key(resolved)
        if key in seen_paths:
            continue
        name = resolved.name
        if name:
            name_key = fold_identifier(name)
            if name_key in seen_names:
                continue
            seen_names.add(name_key)
        seen_paths.add(key)
        ordered.append(resolved)
    return tuple(ordered)


def parse_search_path(text: str, *, base: Path | None = None) -> tuple[Path, ...]:
    """Parse a comma-separated search path into an ordered tuple of roots.

    Entries are trimmed, empty entries are ignored, and ``\\`` is accepted as the
    separator the Windows-style path list uses. A relative entry is resolved
    under *base* when one is given, otherwise under the current directory. The
    result keeps the written order and drops duplicates; an empty path raises
    ``ValueError``.
    """
    roots: list[Path] = []
    for raw in text.split(","):
        entry = raw.strip()
        if not entry:
            continue
        if os.name != "nt" and ntpath.splitdrive(entry)[0]:
            raise ValueError(f"search path entry {entry!r} is a Windows path; use a POSIX path on this platform")
        path = Path(entry.replace("\\", "/"))
        if base is not None and not path.is_absolute():
            path = base / path
        roots.append(path.resolve())
    if not roots:
        raise ValueError("search path has no entries")
    return ordered_lookup_bases(roots)


class ProjectLookup:
    """Resolves a program's artifacts across ordered roots.

    The mode selects candidate extensions; each artifact falls back per artifact
    (``.s`` → ``.x`` etc. in draft mode) and across roots in the caller's order.
    Path order dominates extension preference: earlier roots are scanned before
    any later root is considered. A root whose directory name repeats an earlier
    root is shadowed and never searched, because the loading path holds one
    library per name. An optional parser-owned ``FileLookupCache``
    short-circuits the ordered scan: a cached resolution is trusted only when
    its base is still a configured root, is still present in the current ordered
    bases, and the artifact still exists, and after confirming no
    higher-precedence base holds it. Misses fall through to the full ordered
    scan, which refreshes the cache.

    Only code bodies and dependency sidecars resolve through the ordered roots.
    Graphics and distribution companions are anchored to the body that owns
    them, so a root-ordered search for either is refused rather than answered
    with another unit's companion.
    """

    #: Artifact kinds that must never resolve through the ordered roots.
    _BODY_ANCHORED_KINDS = frozenset({ArtifactKind.GRAPHICS, ArtifactKind.DISTRIBUTION})

    def __init__(
        self,
        roots: Sequence[Path],
        mode: LoadMode,
        *,
        index: SourceIndex | None = None,
        cache: FileLookupCache | None = None,
        debug: Callable[[str], None] | None = None,
    ) -> None:
        #: The effective roots. A later root with a name an earlier root already
        #: holds is shadowed and never searched.
        self._roots = ordered_lookup_bases(roots)
        #: The lookup path. It does not depend on the requester, so one lookup
        #: resolves every name in the same order.
        self._ordered = self._roots
        self._mode = mode
        self._index = index if index is not None else SourceIndex(self._roots)
        self._cache = cache
        self._debug = debug

    def _dbg(self, message: str) -> None:
        if self._debug is not None:
            self._debug(message)

    def _find_in_base(self, name: str, extensions: Sequence[str], base: Path, *, kind: str) -> Path | None:
        """Resolve ``name`` against a single base via its index, then a stat fallback."""
        if not is_unit_name(name):
            self._dbg(f"Refusing {kind} name {name!r}: a unit name may not carry a path")
            return None
        indexed = self._index.find_in_index(base=base, name=name, extensions=extensions)
        if indexed is not None and indexed.is_file():
            self._dbg(f"Using ordered lookup file: {indexed}")
            self._remember(kind, name, base, indexed.suffix.lower())
            return indexed
        for ext in extensions:
            candidate = base / f"{name}{ext}"
            # Only a regular file is an artifact: a directory or a FIFO named
            # like a body must not shadow a real body in a later root, and a
            # FIFO must never be opened. The parent must stay inside the base,
            # so a traversal spelling is still refused when the name guard is
            # bypassed. The candidate itself may be a symlink to a body outside
            # the base; that is a deliberate layout and both lookup paths accept
            # it.
            if candidate.is_file() and _is_relative_to(candidate.parent, base):
                self._dbg(f"Using ordered lookup file: {candidate}")
                self._remember(kind, name, base, ext)
                self._index.add(base=base, name=name, path=candidate)
                return candidate
        return None

    def collisions_for(self, name: str, base: Path) -> tuple[NameCollision, ...]:
        """Files in *base* whose stems fold to *name*'s unit identity."""
        return self._index.collisions_for_base(base, name)

    def unusable_code_files(self) -> tuple[Path, ...]:
        """Code files in every effective root whose stems are not unit names.

        Each root is indexed once here, so the answer is complete regardless of
        which targets the caller asked for. A shadowed root contributes
        nothing, because it is not on the loading path.
        """
        files: list[Path] = []
        for base in self._roots:
            files.extend(self._index.unusable_code_files(base))
        return tuple(files)

    def _find_in_cached_base(
        self,
        kind: str,
        name: str,
        extensions: Sequence[str],
        *,
        ordered: Sequence[Path],
    ) -> tuple[Path, Path] | None:
        """Trust a cached resolution only when it still holds under current ordering.

        The cached base must be a configured root that is still present in the
        ordered bases, and no higher-precedence (earlier) base may hold the
        artifact. This preserves path precedence while skipping the scan of
        every base after the cached one. On any failure the entry is forgotten
        and the caller falls through to the full ordered scan.
        """
        if self._cache is None:
            return None
        cached = self._cache.get(kind, name, self._mode.value)
        if not cached:
            return None
        base = Path(cached["base_dir"])
        if not cached["base_dir"] or not _is_allowed_base(self._roots, base):
            self._cache.forget(kind, name, self._mode.value)
            return None
        base_key = _lookup_path_key(base)
        position = next(
            (index for index, resolved in enumerate(ordered) if _lookup_path_key(resolved) == base_key),
            None,
        )
        if position is None:
            self._cache.forget(kind, name, self._mode.value)
            return None
        for outranking in ordered[:position]:
            found = self._find_in_base(name, extensions, outranking, kind=kind)
            if found is not None:
                return found, outranking
        # Extension *preference* wins over the extension recorded in the cache:
        # an artifact that appeared after the cache was written must not be
        # shadowed by the cached one, or a warm lookup would disagree with a cold
        # one. The name is resolved through the same case-insensitive
        # index the cold scan uses, because a literal path check would miss a
        # file whose case differs from the dependency spelling and silently
        # fall through to a coarser extension. A stale index only costs a full
        # ordered scan: the caller forgets the entry and rescans.
        found = self._index.find_in_index(base=base, name=name, extensions=extensions)
        if found is not None and found.is_file():
            self._dbg(f"Using cached {kind} file: {found}")
            self._remember(kind, name, base, found.suffix.lower())
            return found, base
        self._cache.forget(kind, name, self._mode.value)
        return None

    def _remember(self, kind: str, name: str, base: Path, ext: str) -> None:
        if self._cache is not None:
            self._cache.set(kind, name, self._mode.value, base, ext)

    def _find_with_base(self, name: str, kind: ArtifactKind) -> tuple[Path, Path] | None:
        """Resolve ``name`` and return ``(path, resolving_base)``, or ``None``."""
        if kind in self._BODY_ANCHORED_KINDS:
            raise ValueError(
                f"{kind.value} companions are resolved beside the body that owns them, "
                f"not through the ordered roots; use the companion resolver for the body"
            )
        extensions = candidate_extensions(kind, self._mode)
        kind_value = kind.value
        cached = self._find_in_cached_base(kind_value, name, extensions, ordered=self._ordered)
        if cached is not None:
            return cached
        for base in self._ordered:
            found = self._find_in_base(name, extensions, base, kind=kind_value)
            if found is not None:
                return found, base
        self._dbg(f"No {kind_value} file found for {name!r} in mode={self._mode.value}")
        return None

    def find(self, name: str, kind: ArtifactKind) -> Path | None:
        """Resolve ``name`` of ``kind`` across the ordered roots, or ``None``.

        The cache is consulted first (when present) so a stable layout skips the
        ordered scan entirely; only on a miss is the full ordered scan run, and
        every successful resolution refreshes the cache.

        Raises ``ValueError`` for a graphics or distribution companion, which has
        no root-ordered meaning.
        """
        result = self._find_with_base(name, kind)
        return None if result is None else result[0]

    def find_code(self, name: str) -> Path | None:
        return self.find(name, ArtifactKind.CODE)

    def find_code_with_base(self, name: str) -> tuple[Path, Path] | None:
        """Resolve a code file and the root directory that resolved it."""
        return self._find_with_base(name, ArtifactKind.CODE)

    def find_deps_beside(self, code_path: Path, name: str) -> Path | None:
        """Resolve the dependency sidecar at the selected body's own prefix.

        A SattLine library is a body plus a sidecar at *one* prefix.
        Resolving the sidecar through the whole ordered root list can pair a
        body with an unrelated library's sidecar, so the body prefix decides.
        :meth:`find_deps` keeps the ordered-root search for a caller that wants
        it.

        The body's own suffix selects the artifact family, so a ``.s`` body
        looks only for ``.l`` and an ``.x`` body only for ``.z``. A sidecar from
        the other family is never paired. A name that carries a path separator
        or a parent reference is refused rather than resolved beside the body.
        """
        if not is_unit_name(name):
            self._dbg(f"Refusing deps name {name!r}: a unit name may not carry a path")
            return None
        extensions = deps_extensions_for_code(code_path.suffix, self._mode)
        return self._find_in_base(name, extensions, code_path.parent, kind=ArtifactKind.DEPS.value)

    def find_deps(self, name: str) -> Path | None:
        return self.find(name, ArtifactKind.DEPS)


__all__ = [
    "NameCollision",
    "ProjectLookup",
    "SourceIndex",
    "is_unit_name",
    "ordered_lookup_bases",
    "parse_search_path",
]
