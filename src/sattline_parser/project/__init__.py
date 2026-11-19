"""The SattLine project/artifact layer.

This subpackage owns the project-level domain model and the loading behavior:
how a set of SattLine artifacts resolves into ``SattLineProgram`` instances with
a ``SattLineProject`` registry, a resolved ``DependencyGraph``, and per-program
validation findings.

``SattLineProject.load`` resolves targets across ordered roots, reads dependency
sidecars, loads dependencies first, parses ``.g`` / ``.y`` graphics and ``.p`` /
``.q`` distribution companions, and (with ``validate=INVOKED``, the default)
runs the single-file validator against the definitions visible
from already-loaded dependencies. The loader records library and origin
provenance, reports definition datecode conflicts, and rejects recursive
dependency sidecars and recursive module-type instantiation. A load is all or
nothing: a missing or unparseable artifact raises instead of returning a partial
project.
"""

from __future__ import annotations

from .ast_cache import FILE_AST_CACHE_VERSION, FileASTCache
from .discovery import ProjectLookup, SourceIndex, ordered_lookup_bases, parse_search_path
from .distribution import (
    DistributionParseError,
    parse_distribution_file,
    parse_distribution_text,
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
from .formats import (
    ArtifactKind,
    body_mode,
    candidate_extensions,
    code_ext,
    code_ext_candidates,
    deps_ext,
    deps_ext_candidates,
    deps_extensions_for_code,
    distribution_ext,
    distribution_ext_candidates,
    distribution_extensions_for_code,
    find_companion_beside,
    graphics_ext,
    graphics_ext_candidates,
    preferred_extension,
)
from .graphics_parsing import (
    MAX_GRAPHICS_COMPANION_BYTES,
    GraphicsParseError,
    parse_graphics_file,
    parse_graphics_text,
    resolve_graphics_companion_path,
)
from .identity import ArtifactIdentity, UnitIdentity
from .index import DefinitionSite, ProjectIndex, SymbolKind, UsageSite
from .loader import ProjectLoader, read_dependency_names
from .lookup_cache import DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL, LOOKUP_CACHE_VERSION, FileLookupCache
from .models import (
    DependencyGraph,
    DistributionData,
    DistributionTarget,
    GraphicsBinding,
    GraphicsCompositeRecord,
    GraphicsMessage,
    GraphicsModel,
    GraphicsPathRow,
    GraphicsPictureDisplayRecord,
    LoadDiagnostic,
    LoadDiagnosticKind,
    LoadMode,
    LoadValidation,
    ProgramFormat,
    SattLineProgram,
    SidecarState,
)
from .project import SattLineProject
from .reachability import invoked_moduletypes

__all__ = [
    "DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL",
    "FILE_AST_CACHE_VERSION",
    "LOOKUP_CACHE_VERSION",
    "MAX_GRAPHICS_COMPANION_BYTES",
    "ArtifactIdentity",
    "ArtifactKind",
    "ArtifactLoadError",
    "DefinitionSite",
    "DependencyCycleError",
    "DependencyGraph",
    "DependencyNotFoundError",
    "DependencyParseError",
    "DistributionData",
    "DistributionParseError",
    "DistributionTarget",
    "FileASTCache",
    "FileLookupCache",
    "GraphicsBinding",
    "GraphicsCompositeRecord",
    "GraphicsMessage",
    "GraphicsModel",
    "GraphicsParseError",
    "GraphicsPathRow",
    "GraphicsPictureDisplayRecord",
    "LoadDiagnostic",
    "LoadDiagnosticKind",
    "LoadMode",
    "LoadValidation",
    "ModuleTypeCycleError",
    "ProgramFormat",
    "ProjectIndex",
    "ProjectLoadError",
    "ProjectLoader",
    "ProjectLookup",
    "SattLineProgram",
    "SattLineProject",
    "SidecarState",
    "SourceIndex",
    "StructuralProjectError",
    "SymbolKind",
    "UnitIdentity",
    "UsageSite",
    "body_mode",
    "candidate_extensions",
    "code_ext",
    "code_ext_candidates",
    "deps_ext",
    "deps_ext_candidates",
    "deps_extensions_for_code",
    "distribution_ext",
    "distribution_ext_candidates",
    "distribution_extensions_for_code",
    "find_companion_beside",
    "graphics_ext",
    "graphics_ext_candidates",
    "invoked_moduletypes",
    "ordered_lookup_bases",
    "parse_distribution_file",
    "parse_distribution_text",
    "parse_graphics_file",
    "parse_graphics_text",
    "parse_search_path",
    "preferred_extension",
    "read_dependency_names",
    "resolve_distribution_companion_path",
    "resolve_graphics_companion_path",
]
