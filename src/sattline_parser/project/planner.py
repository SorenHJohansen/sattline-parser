"""The discovery phase: resolve a target set into an ordered plan.

The planner resolves names to files, reads dependency sidecars, and recurses
into each dependency. It never parses a body, so the whole closure is known
before any parse work starts. Plans are appended after their dependencies,
which makes the plan list post-order.

Identity is explicit here. A plan is keyed by the resolved artifact, and the
active recursion stack holds artifacts, not names. Cycle detection therefore
follows physical files: a name that resolves to a different file is not a
cycle, and two different names that resolve to one file cannot hide one. The
diagnostic still reports the logical names that formed the loop, because that
is what a reader can act on.

A dependency is resolved through the caller's ordered roots, so one name reaches
one body in a load. The stack is keyed by artifact, not name, because two
different names can resolve to one file (an alias or a symlink), which a name
key would miss.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from sattline_parser.source_io import read_text_cp1252

from ._cycles import canonical_cycle
from .discovery import ProjectLookup
from .errors import DependencyCycleError, DependencyNotFoundError, DependencyParseError
from .formats import ALL_DEPS_EXTENSIONS, find_companion_beside
from .identity import ArtifactIdentity
from .models import LoadDiagnosticKind, LoadMode, SidecarState
from .plan import Plan, ResolvedArtifact

__all__ = ["ProjectPlanner", "read_dependency_names"]


def read_dependency_names(deps_path: Path) -> tuple[str, ...]:
    """Read a ``.l`` / ``.z`` dependency file into declared dependency names.

    Each non-blank line is one dependency name; lines are trimmed, blank lines
    are ignored, and declaration order is preserved.
    """
    text = read_text_cp1252(deps_path)
    return tuple(line.strip() for line in text.splitlines() if line.strip())


class ProjectPlanner:
    """Resolve a target set into post-order plans without parsing anything."""

    def __init__(
        self,
        *,
        lookup: ProjectLookup,
        mode: LoadMode,
        debug: Callable[[str], None] | None,
        diagnose: Callable[..., None],
        artifact_resolver: ArtifactResolver | None = None,
    ) -> None:
        self._lookup = lookup
        self._mode = mode
        self._debug = debug
        self._diagnose = diagnose
        self._artifact_resolver = artifact_resolver or self.resolve_artifact
        #: Post-order plans: every dependency precedes its consumer.
        self.plans: list[Plan] = []
        #: Plan key -> the plan keys of its resolved dependencies.
        self.resolved_dependencies: dict[str, tuple[str, ...]] = {}
        #: The plan keys of the explicitly requested units.
        self.target_plan_keys: set[str] = set()
        self._planned: set[ArtifactIdentity] = set()
        #: The active recursion stack: artifact identity -> the name that
        #: entered it. Insertion order is the dependency chain.
        self._loading: dict[ArtifactIdentity, str] = {}

    def _dbg(self, message: str) -> None:
        if self._debug is not None:
            self._debug(message)

    def resolve(self, targets: Sequence[str]) -> None:
        """Plan every target and its transitive dependencies, in post-order."""
        for target in targets:
            self.target_plan_keys.add(self._visit(target, declared_by=None))

    def _visit(self, name: str, *, declared_by: str | None) -> str:
        """Plan one unit and return its plan key."""
        return self._discover(name, declared_by=declared_by)

    def _discover(self, name: str, *, declared_by: str | None) -> str:
        """Resolve one unit's artifacts and recurse into its dependencies.

        The plan is appended after the recursion, which makes :attr:`plans` the
        post-order sequence the assembly phase needs. A name that resolves to a
        body this load already planned reuses that plan.
        """
        program_name = declared_by if declared_by is not None else name
        dependency = None if declared_by is None else name
        self._dbg(f"Visiting: {name}")
        artifact = self._artifact_resolver(
            name,
            program_name=program_name,
            dependency=dependency,
        )
        identity = ArtifactIdentity.of(artifact.code_path)
        if identity in self._loading:
            # The dependency loop returns to a file already being planned, so it
            # has no finite load order. Report the logical names that formed it.
            stack = list(self._loading.items())
            start = next(index for index, entry in enumerate(stack) if entry[0] == identity)
            cycle = (*tuple(spelling for _, spelling in stack[start:]), name.casefold())
            raise DependencyCycleError(canonical_cycle(cycle))
        if identity in self._planned:
            return identity.key
        self._planned.add(identity)
        self._loading[identity] = name.casefold()
        try:
            resolved = tuple(self._visit(declared, declared_by=name) for declared in artifact.dependencies)
        finally:
            del self._loading[identity]
        key = identity.key
        self.plans.append(
            Plan(
                key=key,
                name=name,
                declared_by=declared_by,
                artifact=artifact,
                dependencies=resolved,
            )
        )
        self.resolved_dependencies[key] = resolved
        return key

    def resolve_artifact(
        self,
        name: str,
        *,
        program_name: str,
        dependency: str | None,
    ) -> ResolvedArtifact:
        """Find the body, its sidecar, and the declared dependencies."""
        resolved = self._lookup.find_code_with_base(name)
        if resolved is None:
            raise DependencyNotFoundError(
                program_name,
                f"missing code file for {name!r}",
                dependency=dependency,
            )
        code_path, resolved_base = resolved
        library = resolved_base.name
        # The sidecar belongs to the selected body's prefix; see
        # ProjectLookup.find_deps_beside.
        deps_path = self._lookup.find_deps_beside(code_path, name)
        sidecar = SidecarState.ABSENT
        if deps_path is None:
            # A sidecar in the other family sits at the body's own prefix. Probe
            # for it directly, because a mode-filtered root-ordered search never
            # sees the other family and official mode would report a plain miss.
            same_prefix = find_companion_beside(code_path, sorted(ALL_DEPS_EXTENSIONS))
            stray = self._lookup.find_deps(name)
            if same_prefix is not None:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_FAMILY_MISMATCH,
                    program_name,
                    f"sidecar {same_prefix.name!r} does not match the artifact family of body "
                    f"{code_path.name!r}; not paired",
                    same_prefix,
                )
            elif stray is not None:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_ELSEWHERE,
                    program_name,
                    f"sidecar {stray.name!r} is not beside body {code_path.name!r}; not paired",
                    stray,
                )
            else:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_MISSING,
                    program_name,
                    f"no dependency sidecar beside {code_path.name!r}",
                    code_path,
                )
        dependencies = self._read_deps(name, deps_path, program_name, dependency)
        if deps_path is not None:
            sidecar = SidecarState.PRESENT if dependencies else SidecarState.EMPTY
            if sidecar is SidecarState.EMPTY:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_EMPTY,
                    program_name,
                    f"sidecar {deps_path.name!r} declares no dependencies",
                    deps_path,
                )
        return ResolvedArtifact(
            code_path=code_path,
            resolved_base=resolved_base,
            library=library,
            deps_path=deps_path,
            sidecar=sidecar,
            dependencies=dependencies,
        )

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
        except (OSError, UnicodeError) as exc:
            raise DependencyParseError(
                program_name,
                f"unable to read dependency file {deps_path.name} for {name!r}",
                dependency=dependency,
            ) from exc


#: The artifact resolver the planner uses: the loader's own method by default.
ArtifactResolver = Callable[..., ResolvedArtifact]
