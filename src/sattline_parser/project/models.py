"""Domain model for the SattLine project/artifact layer (Phase 1 skeleton).

LoadMode, ProgramFormat, the graphics companion model, SattLineProgram, and the
DependencyGraph are pure value types. They carry no I/O or loading logic; the
artifact-discovery rules and loading behavior land in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from sattline_parser.models.ast_model import BasePicture, GraphicsBinding, SourceSpan


class LoadMode(Enum):
    """Source-mode selector deciding which artifacts a program resolves to."""

    DRAFT = "draft"
    OFFICIAL = "official"


@dataclass(frozen=True, slots=True)
class ProgramFormat:
    """Which artifacts were resolved for a program, and in which mode.

    Extensions describe the artifacts actually found; each is ``None`` when the
    artifact was not present/loaded. ``code`` is always resolved for a program.
    """

    mode: LoadMode
    code_ext: str | None = None
    graphics_ext: str | None = None
    deps_ext: str | None = None


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
    """A ``GRAPHICS`` composite (``9030`` family) record from a companion file."""

    record_index: int
    record_start_line: int
    record_end_line: int
    family_code: str


@dataclass(frozen=True, slots=True)
class GraphicsPictureDisplayPathRow:
    """A single indexed row inside a ``PICTUREDISPLAY`` (``9031``) record."""

    record_index: int
    index_token: str
    index_value: int | None
    kind: Literal["literal", "variable", "variable_invalid"]
    raw_text: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class GraphicsPictureDisplayRecord:
    """A ``PICTUREDISPLAY`` (``9031``) record from a graphics companion file."""

    record_index: int
    record_start_line: int
    record_end_line: int
    subtype: str = "2"
    path_row_lines: tuple[int, ...] = ()
    path_rows: tuple[GraphicsPictureDisplayPathRow, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphicsModel:
    """The parsed representation of a program's graphics companion file.

    Holds the parse result only (bindings, messages, and record families);
    semantic validation against the program and asset-path warnings live in the
    consumer layer.
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


@dataclass(frozen=True, slots=True)
class SattLineProgram:
    """A fully loaded SattLine program within a project.

    ``name`` is the program identity, ``code`` the parsed SattLine source
    picture, ``graphics`` the parsed companion file (``None`` when absent),
    ``dependencies`` the declared dependency program names, and ``format`` the
    concrete artifact combination this program resolved to. ``source_path`` is
    the resolved code file, exposed as provenance for consumer-side
    diagnostics and indexing; the artifact paths themselves remain on
    ``format`` and are otherwise internal to the loader.
    """

    name: str
    code: BasePicture
    graphics: GraphicsModel | None = None
    dependencies: tuple[str, ...] = ()
    format: ProgramFormat = ProgramFormat(mode=LoadMode.OFFICIAL)
    source_path: Path | None = None


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    """Resolved dependency edges between loaded programs.

    Both ``nodes`` and the edge endpoints use canonical identities (the program
    name casefolded) so lookups are case-insensitive and deterministic.
    """

    nodes: tuple[str, ...] = ()
    edges: tuple[tuple[str, str], ...] = ()

    def dependencies_of(self, name: str) -> tuple[str, ...]:
        """Direct dependencies (outgoing edges) of ``name``, in graph order."""
        key = name.casefold()
        return tuple(dependency for dependent, dependency in self.edges if dependent == key)

    def dependents_of(self, name: str) -> tuple[str, ...]:
        """Direct dependents (incoming edges) of ``name``, in graph order."""
        key = name.casefold()
        return tuple(dependent for dependent, dependency in self.edges if dependency == key)


__all__ = [
    "DependencyGraph",
    "GraphicsCompositeRecord",
    "GraphicsMessage",
    "GraphicsModel",
    "GraphicsPictureDisplayPathRow",
    "GraphicsPictureDisplayRecord",
    "LoadMode",
    "ProgramFormat",
    "SattLineProgram",
]
