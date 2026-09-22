"""The SattLine project/artifact layer.

This subpackage owns the project-level domain model and the loading behavior:
how a set of SattLine artifacts resolves into ``SattLineProgram`` instances with
a ``SattLineProject`` registry and a resolved ``DependencyGraph``.

Phases 1-4 deliver the domain skeleton, file discovery and lookup, the
parser-owned caches, wired ``SattLineProject.load`` with recursive dependency
resolution, and ``.g`` / ``.y`` graphics companion parsing
(see ``PARSER_PROJECT_LAYER_PLAN.md``).
"""

from __future__ import annotations

from .ast_cache import FILE_AST_CACHE_VERSION, FileASTCache
from .discovery import ProjectLookup, SourceIndex, ordered_lookup_bases, shared_lookup_root_for
from .errors import (
    ArtifactLoadError,
    DependencyNotFoundError,
    DependencyParseError,
    ProjectLoadError,
)
from .formats import (
    ArtifactKind,
    candidate_extensions,
    code_ext,
    code_ext_candidates,
    deps_ext,
    deps_ext_candidates,
    graphics_ext,
    graphics_ext_candidates,
    preferred_extension,
)
from .graphics_parsing import parse_graphics_file, parse_graphics_text, resolve_graphics_companion_path
from .loader import ProjectLoader, read_dependency_names
from .lookup_cache import DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL, LOOKUP_CACHE_VERSION, FileLookupCache
from .models import (
    DependencyGraph,
    GraphicsCompositeRecord,
    GraphicsMessage,
    GraphicsModel,
    GraphicsPictureDisplayPathRow,
    GraphicsPictureDisplayRecord,
    LoadMode,
    ProgramFormat,
    SattLineProgram,
)
from .project import SattLineProject

__all__ = [
    "DEFAULT_LOOKUP_CACHE_FLUSH_INTERVAL",
    "FILE_AST_CACHE_VERSION",
    "LOOKUP_CACHE_VERSION",
    "ArtifactKind",
    "ArtifactLoadError",
    "DependencyGraph",
    "DependencyNotFoundError",
    "DependencyParseError",
    "FileASTCache",
    "FileLookupCache",
    "GraphicsCompositeRecord",
    "GraphicsMessage",
    "GraphicsModel",
    "GraphicsPictureDisplayPathRow",
    "GraphicsPictureDisplayRecord",
    "LoadMode",
    "ProgramFormat",
    "ProjectLoadError",
    "ProjectLoader",
    "ProjectLookup",
    "SattLineProgram",
    "SattLineProject",
    "SourceIndex",
    "candidate_extensions",
    "code_ext",
    "code_ext_candidates",
    "deps_ext",
    "deps_ext_candidates",
    "graphics_ext",
    "graphics_ext_candidates",
    "ordered_lookup_bases",
    "parse_graphics_file",
    "parse_graphics_text",
    "preferred_extension",
    "read_dependency_names",
    "resolve_graphics_companion_path",
    "shared_lookup_root_for",
]
