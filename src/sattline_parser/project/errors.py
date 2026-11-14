"""Structured errors for the SattLine project/artifact layer.

Every error identifies the affected program and, when known, the dependency
through which the failure surfaced, so the loading layer can produce precise
per-target reports.
"""

from __future__ import annotations

from collections.abc import Sequence


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


class StructuralProjectError(ProjectLoadError):
    """A structural error: the tree has no valid load order."""


class DependencyNotFoundError(ProjectLoadError):
    """A declared dependency could not be resolved under the configured roots."""


class DependencyParseError(ProjectLoadError):
    """A declared dependency exists but could not be parsed into a program."""


class ArtifactLoadError(ProjectLoadError):
    """A required companion artifact for a program could not be loaded."""


class DependencyCycleError(StructuralProjectError):
    """A dependency sidecar chain returns to a program that is still loading."""

    def __init__(self, cycle: Sequence[str]) -> None:
        self.cycle = tuple(cycle)
        super().__init__(self.cycle[0], f"dependency cycle: {' -> '.join(self.cycle)}")

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        """Preserve ``cycle`` across pickling."""
        return (_rebuild_dependency_cycle, (self.cycle,))


class ModuleTypeCycleError(StructuralProjectError):
    """A module type expands into itself through its submodule instances."""

    def __init__(self, program: str, cycle: Sequence[str]) -> None:
        self.cycle = tuple(cycle)
        super().__init__(program, f"module type instantiates itself recursively: {' -> '.join(self.cycle)}")

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        """Preserve ``program`` and ``cycle`` across pickling."""
        return (_rebuild_moduletype_cycle, (self.program, self.cycle))


def _rebuild_dependency_cycle(cycle: tuple[str, ...]) -> DependencyCycleError:
    return DependencyCycleError(cycle)


def _rebuild_moduletype_cycle(program: str, cycle: tuple[str, ...]) -> ModuleTypeCycleError:
    return ModuleTypeCycleError(program, cycle)


__all__ = [
    "ArtifactLoadError",
    "DependencyCycleError",
    "DependencyNotFoundError",
    "DependencyParseError",
    "ModuleTypeCycleError",
    "ProjectLoadError",
    "StructuralProjectError",
]
