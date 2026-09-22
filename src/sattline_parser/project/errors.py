"""Structured errors for the SattLine project/artifact layer.

Every error identifies the affected program and, when known, the dependency
through which the failure surfaced, so the loading layer can produce precise
per-target reports.
"""

from __future__ import annotations


class ProjectLoadError(Exception):
    """Base error for project loading failures.

    ``program`` is the affected program name; ``dependency`` is the dependency
    involved when the failure was observed through an edge of the graph.
    """

    program: str
    dependency: str | None

    def __init__(self, program: str, message: str, *, dependency: str | None = None) -> None:
        self.program = program
        self.dependency = dependency
        prefix = f"{program}: {message}"
        super().__init__(prefix if dependency is None else f"{prefix} (dependency {dependency!r})")


class DependencyNotFoundError(ProjectLoadError):
    """A declared dependency could not be resolved under the configured roots."""


class DependencyParseError(ProjectLoadError):
    """A declared dependency exists but could not be parsed into a program."""


class ArtifactLoadError(ProjectLoadError):
    """A required companion artifact for a program could not be loaded."""


__all__ = ["ArtifactLoadError", "DependencyNotFoundError", "DependencyParseError", "ProjectLoadError"]
