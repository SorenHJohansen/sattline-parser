"""Domain model for the SattLine project/artifact layer.

LoadMode, ProgramFormat, the graphics companion model, SattLineProgram, and the
DependencyGraph are pure value types. They carry no I/O or loading logic; the
discovery rules live in :mod:`sattline_parser.project.formats` and the loading
behavior in :mod:`sattline_parser.project.loader`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from sattline_parser.models.ast_model import BasePicture, GraphicsBinding, SourceSpan
from sattline_parser.names import fold_identifier
from sattline_parser.validation.diagnostics import Diagnostic

from .errors import ProjectLoadError
from .identity import ArtifactIdentity, UnitIdentity

if TYPE_CHECKING:
    from .project import SattLineProject


class LoadMode(Enum):
    """Source-mode selector deciding which artifacts a program resolves to."""

    DRAFT = "draft"
    OFFICIAL = "official"


class LoadValidation(StrEnum):
    """Choose scoped validation beyond type-reference binding.

    Every scope checks type references in all loaded files, including unused
    declarations, against each containing file's dependency closure.
    ``INVOKED`` additionally validates each target and the dependency module
    types it invokes transitively. ``FULL`` validates every loaded program.
    ``NONE`` skips those additional checks, not type-reference binding.
    """

    NONE = "none"
    FULL = "full"
    INVOKED = "invoked"


class CacheDisabledReason(StrEnum):
    """Why a project cache is not usable for this load.

    ``NOT_CONFIGURED`` means the caller passed no ``cache_dir``.
    ``PRIVACY`` means the supplied directory could not be proven private to
    this user. ``UNAVAILABLE`` means it could not be created or opened, or a
    cache handle was disabled after construction.
    """

    NOT_CONFIGURED = "not-configured"
    PRIVACY = "privacy"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CacheInfo:
    """A snapshot of the project-owned caches for one load.

    ``enabled`` is true only when both the lookup cache and the AST cache could
    be established. The counters describe the work this load actually did:
    ``ast_hits`` and ``ast_misses`` count body parses served from or attempted
    against the AST cache, and ``lookup_hits``/``lookup_misses`` count ordered
    discovery resolutions served from or attempted against the lookup cache.
    A load with no cache reports zero counters.
    """

    enabled: bool = False
    disabled_reason: CacheDisabledReason | None = CacheDisabledReason.NOT_CONFIGURED
    ast_hits: int = 0
    ast_misses: int = 0
    lookup_hits: int = 0
    lookup_misses: int = 0


@dataclass(frozen=True, slots=True)
class ProgramFormat:
    """Which artifacts were resolved for a program, and in which mode.

    Extensions describe the artifacts actually found; each is ``None`` when the
    artifact was not present/loaded. ``code`` is always resolved for a program.

    ``mode`` is the artifact family the resolved body belongs to, not the mode
    the caller requested: a draft load that fell back to an ``.x`` body reports
    ``OFFICIAL``, because the body's suffix decides which sidecars and
    companions can pair with it.
    """

    mode: LoadMode
    code_ext: str | None = None
    graphics_ext: str | None = None
    deps_ext: str | None = None
    distribution_ext: str | None = None


@dataclass(frozen=True, slots=True)
class GraphicsMessage:
    """A validation message produced while parsing a graphics companion file."""

    severity: Literal["error", "warning"]
    message: str
    line: int
    column: int
    length: int = 1


@dataclass(frozen=True, slots=True)
class GraphicsCompositeRecord:
    """A serialized graphics record found in a companion file.

    Records are delimited by a family-code line and a trailing ``0`` line.
    ``start_line`` and ``end_line`` are one-based and inclusive.
    """

    record_index: int
    family_code: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class GraphicsPathRow:
    """One path row inside a picture display record.

    ``kind`` distinguishes a variable reference, a variable reference the
    serialized file marked invalid, and a literal asset path.
    """

    record_index: int
    index_token: str
    index_value: int | None
    kind: Literal["variable", "variable_invalid", "literal"]
    raw_text: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class GraphicsPictureDisplayRecord:
    """A picture display record and the path rows it carries.

    ``start_line`` and ``end_line`` are one-based and inclusive.
    ``path_row_lines`` lists every one-based line in the record's path-row
    section, including rows that did not parse into a ``GraphicsPathRow``, so
    a consumer can tell section rows apart from other binding lines.
    """

    record_index: int
    start_line: int
    end_line: int
    path_rows: tuple[GraphicsPathRow, ...]
    path_row_lines: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphicsModel:
    """The parsed representation of a program's graphics companion file.

    Holds the bindings, the structural records, and the messages the scanner
    produced. Semantic validation against the program, asset verification, and
    correlation against the code picture live in the consumer layer.
    """

    bindings: tuple[GraphicsBinding, ...] = ()
    messages: tuple[GraphicsMessage, ...] = ()
    composite_records: tuple[GraphicsCompositeRecord, ...] = ()
    picture_display_records: tuple[GraphicsPictureDisplayRecord, ...] = ()

    @property
    def errors(self) -> tuple[GraphicsMessage, ...]:
        """Messages with ``severity == "error"``, in parse order."""
        return tuple(message for message in self.messages if message.severity == "error")

    @property
    def warnings(self) -> tuple[GraphicsMessage, ...]:
        """Messages with ``severity == "warning"``, in parse order."""
        return tuple(message for message in self.messages if message.severity == "warning")


class SidecarState(StrEnum):
    """What the dependency sidecar looked like for a loaded program.

    A library is a body *and* a sidecar at one prefix, so the three cases are
    distinct: absent (no file), empty (file, no names) and
    present. Conflating absent with empty would silently drop a dependency chain.
    """

    ABSENT = "absent"
    EMPTY = "empty"
    PRESENT = "present"


class LoadDiagnosticKind(StrEnum):
    """Non-fatal project-load findings a consumer may want to act on."""

    SIDECAR_MISSING = "sidecar-missing"
    SIDECAR_ELSEWHERE = "sidecar-elsewhere"
    SIDECAR_EMPTY = "sidecar-empty"
    #: A sidecar sits beside the body but belongs to the other artifact family,
    #: for example a ``.z`` beside a ``.s`` body. It is never paired.
    SIDECAR_FAMILY_MISMATCH = "sidecar-family-mismatch"
    #: Two files or two spellings fold to one project key. The loader keeps the
    #: first resolution, because a casefolded view can hold only one unit there,
    #: and reports the layout as ambiguous instead of dropping a unit silently.
    FOLDED_NAME_COLLISION = "folded-name-collision"
    #: A spelling reached a body the load had already planned, and a dependency
    #: sidecar sits beside that spelling. The body is planned once, so the
    #: declarations in the alias prefix's sidecar are not read; reporting it
    #: explains why a name the sidecar lists is not in the registry.
    ALIAS_DECLARATIONS_UNUSED = "alias-declarations-unused"
    #: A code file directly under a root has a stem the resolver refuses as a
    #: unit name, so it can never load as a unit. The load reports it and carries
    #: on instead of failing on a target it could only refuse.
    SKIPPED_FILE = "skipped-file"
    #: A companion sits beside the body but belongs to the other artifact family,
    #: for example a ``.y`` beside a ``.s`` body. It is never paired, because a
    #: unit belongs to one family and a silent ignore would leave the answer to
    #: ``has_executing_system`` unavailable with no explanation.
    COMPANION_FAMILY_MISMATCH = "companion-family-mismatch"


@dataclass(frozen=True, slots=True)
class LoadDiagnostic:
    """One non-fatal load finding.

    These are conditions the loader reports and an operator can continue past;
    raising would be stricter than the tool, so they are surfaced instead of
    thrown.
    """

    kind: LoadDiagnosticKind
    program: str
    detail: str
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class TargetLoadResult:
    """The outcome of one target in :meth:`SattLineProject.load_many`.

    Exactly one of ``project`` and ``error`` is set. A successful target owns a
    complete project for its own dependency closure; a failed target reports the
    load error that stopped it. ``target`` is the spelling the caller supplied.
    """

    target: str
    project: SattLineProject | None = None
    error: ProjectLoadError | None = None

    @property
    def ok(self) -> bool:
        """Whether this target loaded completely."""
        return self.project is not None


@dataclass(frozen=True, slots=True)
class DistributionTarget:
    """One entry of a distribution section: a named download target.

    ``kind`` is the section keyword as written (for example ``Controller`` or
    ``OpStation``), ``name`` is the target's ``Name`` string, and
    ``attributes`` holds the trailing ``Keyword Value`` pairs in file order.
    """

    kind: str
    name: str
    attributes: tuple[tuple[str, str], ...] = ()

    @property
    def download(self) -> str | None:
        """The value of the ``Download`` attribute, when the target declares one."""
        for key, value in self.attributes:
            if key.casefold() == "download":
                return value
        return None


@dataclass(frozen=True, slots=True)
class DistributionData:
    """The parsed representation of a program's distribution companion.

    A distribution companion (``.p`` draft, ``.q`` official) records which
    systems the unit is sent to. It is configuration, not proof that the unit is
    running anywhere, and it is not a module type: a program and a library both
    may have one.
    """

    version: str
    source_code_systems: tuple[DistributionTarget, ...] = ()
    executing_systems: tuple[DistributionTarget, ...] = ()

    @property
    def has_executing_system(self) -> bool:
        """Whether at least one executing system is configured."""
        return bool(self.executing_systems)


@dataclass(frozen=True, slots=True)
class SattLineProgram:
    """One loaded source artifact within a project.

    A program is a single ``.x`` or ``.s`` file, not an executable top-level
    program. Loading one target can therefore produce many of these through the
    dependency closure.

    ``name`` is the program identity, ``code`` the parsed SattLine source
    picture, ``graphics`` the parsed companion file (``None`` when absent),
    ``dependencies`` the declared dependency program names, and ``format`` the
    concrete artifact combination this program resolved to. ``dependencies``
    keeps the declared spelling and order. One path order resolves every name,
    so the loader keeps one resolved body per name. ``source_path`` is the
    resolved code file, exposed as provenance for consumer-side diagnostics and
    indexing; the artifact paths themselves remain on ``format`` and are
    otherwise internal to the loader.

    ``library`` is the name of the root directory that resolved the body, and
    ``resolved_base`` is that directory. ``diagnostics`` holds this program's
    validation findings.

    ``distribution_path`` is the resolved distribution companion and
    ``distribution`` its parsed content. Both stay ``None`` when no companion was
    found; a companion that exists but cannot be parsed is a load failure, never
    an empty result.
    """

    name: str
    code: BasePicture
    graphics: GraphicsModel | None = None
    dependencies: tuple[str, ...] = ()
    format: ProgramFormat = ProgramFormat(mode=LoadMode.OFFICIAL)
    source_path: Path | None = None
    #: Resolved dependency sidecar, when one was read at the body prefix.
    deps_path: Path | None = None
    #: Whether that sidecar was absent, empty, or carried dependency names.
    sidecar: SidecarState = SidecarState.ABSENT
    #: Root directory name that resolved the body.
    library: str | None = None
    #: Root directory that resolved the body.
    resolved_base: Path | None = None
    #: Resolved distribution companion, when one was read at the body prefix.
    distribution_path: Path | None = None
    #: Parsed distribution companion; ``None`` when there was no companion.
    distribution: DistributionData | None = None
    #: Validation findings for this program, in emission order.
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def has_executing_system(self) -> bool | None:
        """Whether the unit declares an executing system.

        ``None`` means the question could not be answered because no distribution
        companion was found. ``False`` means a companion was parsed and its
        executing-system list is empty.
        """
        if self.distribution is None:
            return None
        return self.distribution.has_executing_system

    @property
    def identity(self) -> UnitIdentity:
        """The language identity of this unit, folded by the CP1252 name table.

        ``name`` keeps the display spelling. Compare units with this property,
        never with ``str.casefold()`` on the name.
        """
        return UnitIdentity.of(self.name)

    @property
    def artifact_identity(self) -> ArtifactIdentity | None:
        """The filesystem identity of the loaded body, when its path is known.

        This is the platform's comparison of the resolved path, not a language
        name comparison.
        """
        return None if self.source_path is None else ArtifactIdentity.of(self.source_path)


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    """Resolved dependency edges between loaded programs.

    ``nodes`` and the edge endpoints are view keys: the program name casefolded,
    except the units of a shared casefold key, which use their language identity
    instead. Each method resolves a name by its exact node key first, then by the
    casefolded spelling, then by the language identity, so ``STRASSE`` reaches
    the unit keyed by that identity rather than a same-key unit.
    """

    nodes: tuple[str, ...] = ()
    edges: tuple[tuple[str, str], ...] = ()

    def _node(self, name: str) -> str:
        """The node key *name* designates, or its folded spelling when unknown."""
        if name in self.nodes:
            return name
        key = name.casefold()
        if key in self.nodes:
            return key
        identity = fold_identifier(name)
        for node in self.nodes:
            if fold_identifier(node) == identity:
                return node
        return key

    def dependencies_of(self, name: str) -> tuple[str, ...]:
        """Direct dependencies (outgoing edges) of ``name``, in graph order."""
        key = self._node(name)
        return tuple(dependency for dependent, dependency in self.edges if dependent == key)

    def dependents_of(self, name: str) -> tuple[str, ...]:
        """Direct dependents (incoming edges) of ``name``, in graph order."""
        key = self._node(name)
        return tuple(dependent for dependent, dependency in self.edges if dependency == key)


__all__ = [
    "CacheDisabledReason",
    "CacheInfo",
    "DependencyGraph",
    "DistributionData",
    "DistributionTarget",
    "GraphicsBinding",
    "GraphicsCompositeRecord",
    "GraphicsMessage",
    "GraphicsModel",
    "GraphicsPathRow",
    "GraphicsPictureDisplayRecord",
    "LoadDiagnostic",
    "LoadDiagnosticKind",
    "LoadMode",
    "LoadValidation",
    "ProgramFormat",
    "SattLineProgram",
    "SidecarState",
    "TargetLoadResult",
]
