"""The plan types shared by the loader's four collaborating phases.

A load runs discovery, parsing, assembly, and validation in that order. The
values below are the hand-off between them: a :class:`ResolvedArtifact` says
which files and sidecar a name resolved to, and a :class:`Plan` says which
program that is, what requested it, and which plans its dependencies became.

``Plan.key`` is the artifact identity key, so two roots holding a same-named
unit are two plans and one repeated spelling is one plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .identity import ArtifactIdentity
from .models import SidecarState

__all__ = ["Plan", "ResolvedArtifact", "dependency_of", "plan_key", "program_of"]


@dataclass(frozen=True, slots=True)
class ResolvedArtifact:
    """The resolved files and dependency metadata for one unit name."""

    code_path: Path
    resolved_base: Path
    library: str
    deps_path: Path | None
    sidecar: SidecarState
    dependencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Plan:
    """One discovered unit, resolved and ready to parse.

    Discovery fills a plan without parsing anything, so the whole closure is
    known before parse work starts. Assembly consumes plans in plan order,
    which is post-order: every dependency precedes its consumer. ``key`` is the
    resolved code path, so two roots holding a same-named unit are two plans.
    ``dependencies`` holds the plan key of each resolved dependency, in
    declaration order.
    """

    key: str
    name: str
    declared_by: str | None
    artifact: ResolvedArtifact
    dependencies: tuple[str, ...] = ()


def plan_key(code_path: Path) -> str:
    """The unique plan identity for a resolved body: its filesystem identity."""
    return ArtifactIdentity.of(code_path).key


def program_of(plan: Plan) -> str:
    """The logical unit that owns a failure for this plan."""
    return plan.declared_by if plan.declared_by is not None else plan.name


def dependency_of(plan: Plan) -> str | None:
    """The dependency spelling this plan was requested under, or ``None``."""
    return None if plan.declared_by is None else plan.name
