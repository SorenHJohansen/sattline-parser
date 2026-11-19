"""The discovery phase: resolve a target set into an ordered plan.

The planner resolves names to files, reads dependency sidecars, and walks into
each dependency on an explicit stack. It never parses a body, so the whole
closure is known before any parse work starts. Plans are appended when a unit
finishes, which makes the plan list post-order, and no chain length can exhaust
the Python call stack.

Identity is explicit here. A plan is keyed by the resolved artifact, and the
active stack holds artifacts, not names. Cycle detection therefore follows
physical files: a name that resolves to a different file is not a cycle, and two
different names that resolve to one file cannot hide one. The diagnostic still
reports the logical names that formed the loop, because that is what a reader can
act on.

A dependency is resolved through the caller's ordered roots, so one name reaches
one body in a load. The stack is keyed by artifact, not name, because two
different names can resolve to one file (an alias or a symlink), which a name
key would miss. Every name that reached a body is recorded, so the loader can
keep an alias as a name for the same unit.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sattline_parser.source_io import read_text_cp1252

from ._cycles import canonical_cycle
from .discovery import ProjectLookup
from .errors import DependencyCycleError, DependencyNotFoundError, DependencyParseError
from .formats import ALL_DEPS_EXTENSIONS, CompanionIndex, code_ext_candidates, find_companion_beside
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


@dataclass(slots=True)
class _Pending:
    """One unit being planned: its artifact and the work still outstanding.

    ``pending`` holds the dependency names not yet visited and ``resolved`` the
    plan keys of the dependencies already planned, in declaration order. A
    stack of these replaces recursion, so a long chain cannot exhaust the Python
    stack.
    """

    name: str
    declared_by: str | None
    artifact: ResolvedArtifact
    identity: ArtifactIdentity
    pending: list[str]
    resolved: list[str]


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
        companions: CompanionIndex | None = None,
    ) -> None:
        self._lookup = lookup
        self._mode = mode
        self._debug = debug
        self._diagnose = diagnose
        self._artifact_resolver = artifact_resolver or self.resolve_artifact
        #: The per-load companion directory index, shared with the assembler so
        #: the sidecar family probe and the two companion roles cost one scan per
        #: directory.
        self._companions = companions if companions is not None else CompanionIndex()
        #: Post-order plans: every dependency precedes its consumer.
        self.plans: list[Plan] = []
        #: Plan key -> the plan keys of its resolved dependencies.
        self.resolved_dependencies: dict[str, tuple[str, ...]] = {}
        #: The plan keys of the explicitly requested units.
        self.target_plan_keys: set[str] = set()
        #: Every spelling that reached a plan, folded view key -> (spelling, plan
        #: key). One body can be reached under several names (an alias or a
        #: symlink), and every spelling is kept so a declared dependency name can
        #: be resolved back to the unit it named.
        self.resolved_names: dict[str, tuple[str, str]] = {}
        self._planned: set[ArtifactIdentity] = set()
        #: The active plan stack: artifact identity -> the name that entered it.
        #: Insertion order is the dependency chain.
        self._loading: dict[ArtifactIdentity, str] = {}

    def _dbg(self, message: str) -> None:
        if self._debug is not None:
            self._debug(message)

    def resolve(self, targets: Sequence[str]) -> None:
        """Plan every target and its transitive dependencies, in post-order."""
        self._report_unusable_names()
        for target in targets:
            self.target_plan_keys.add(self._plan(target, declared_by=None))

    def _report_unusable_names(self) -> None:
        """Report a code file whose stem can never be a unit name.

        The resolver refuses a name outside the identifier charset, so a file
        such as ``Pump.v2.s`` cannot load as a unit however the target was
        chosen. Reporting it as a load diagnostic keeps a whole-tree load alive
        and names the file once, instead of failing the load on a target the
        resolver could only refuse.
        """
        candidates = code_ext_candidates(self._mode)
        for path in self._lookup.unusable_code_files():
            if path.suffix.lower() not in candidates:
                continue
            self._diagnose(
                LoadDiagnosticKind.SKIPPED_FILE,
                path.stem,
                f"{path.name!r} is not a unit name; not loaded as a target",
                path,
            )

    def _plan(self, name: str, *, declared_by: str | None) -> str:
        """Plan one unit and its closure and return its plan key.

        The walk is iterative: each unit is a frame on an explicit stack, so a
        dependency chain of any legal length is planned without growing the
        Python call stack. Plans are appended when a frame finishes, which keeps
        :attr:`plans` post-order.
        """
        root = self._open(name, declared_by=declared_by)
        if isinstance(root, str):
            return root
        stack = [root]
        try:
            while True:
                frame = stack[-1]
                if frame.pending:
                    dependency = frame.pending.pop(0)
                    child = self._open(dependency, declared_by=frame.name)
                    if isinstance(child, str):
                        frame.resolved.append(child)
                    else:
                        stack.append(child)
                    continue
                stack.pop()
                key = self._close(frame)
                if not stack:
                    return key
                stack[-1].resolved.append(key)
        finally:
            # A failed load leaves no active chain behind, so the cycle report of
            # a later visit starts from that visit's own root.
            self._loading.clear()

    def _open(self, name: str, *, declared_by: str | None) -> _Pending | str:
        """Resolve *name* and start its frame, or return an existing plan key.

        The body is resolved before the sidecar, so a spelling that reaches a
        body this load already planned is an alias: its declarations are never
        read, and an unreadable alias sidecar cannot fail a load that the body
        alone survives. The cycle check follows physical files, because a name
        that resolves to a file already on the active stack is a cycle.
        """
        program_name = declared_by if declared_by is not None else name
        dependency = None if declared_by is None else name
        self._dbg(f"Visiting: {name}")
        resolved = self._lookup.find_code_with_base(name)
        if resolved is None:
            raise DependencyNotFoundError(
                program_name,
                f"missing code file for {name!r}",
                dependency=dependency,
            )
        code_path, resolved_base = resolved
        identity = ArtifactIdentity.of(code_path)
        if identity in self._loading:
            # The dependency loop returns to a file already being planned, so it
            # has no finite load order. Report the logical names that formed it.
            chain = list(self._loading.items())
            start = next(index for index, entry in enumerate(chain) if entry[0] == identity)
            cycle = (*tuple(spelling for _, spelling in chain[start:]), name.casefold())
            raise DependencyCycleError(canonical_cycle(cycle))
        if identity in self._planned:
            self._record_name(name, identity.key, code_path)
            self._report_unused_alias(name, code_path)
            return identity.key
        artifact = self._artifact_resolver(
            name,
            program_name=program_name,
            dependency=dependency,
            code_path=code_path,
            resolved_base=resolved_base,
        )
        self._planned.add(identity)
        self._loading[identity] = name.casefold()
        return _Pending(
            name=name,
            declared_by=declared_by,
            artifact=artifact,
            identity=identity,
            pending=list(artifact.dependencies),
            resolved=[],
        )

    def _report_unused_alias(self, name: str, code_path: Path) -> None:
        """Report a sidecar at an alias prefix whose declarations are not read.

        The body is planned once, under the spelling that reached it first, so
        the alias prefix's declarations have no plan to attach to. The sidecar
        path is resolved but never read: a broken file at the alias prefix must
        not fail a load that the body alone survives, and the operator should
        still learn why a declared name is absent from the registry.
        """
        sidecar = self._lookup.find_deps_beside(code_path, name)
        if sidecar is None:
            return
        self._diagnose(
            LoadDiagnosticKind.ALIAS_DECLARATIONS_UNUSED,
            name,
            f"{name!r} resolves to already planned body {code_path.name!r}; "
            f"declarations in {sidecar.name!r} are not used",
            sidecar,
        )

    def _close(self, frame: _Pending) -> str:
        """Finish *frame*: append its plan and return its plan key."""
        key = frame.identity.key
        dependencies = tuple(frame.resolved)
        self.plans.append(
            Plan(
                key=key,
                name=frame.name,
                declared_by=frame.declared_by,
                artifact=frame.artifact,
                dependencies=dependencies,
            )
        )
        self.resolved_dependencies[key] = dependencies
        self._record_name(frame.name, key, frame.artifact.code_path)
        del self._loading[frame.identity]
        return key

    def _record_name(self, spelling: str, plan_key: str, code_path: Path) -> None:
        """Remember that *spelling* reached *plan_key*.

        Two spellings that share a project view key but reach different artifacts
        are an ambiguity the casefolded view cannot represent. The first
        resolution is kept and the pair is reported, because the alternative is
        a unit that disappears without a finding.
        """
        key = spelling.casefold()
        existing = self.resolved_names.get(key)
        if existing is None:
            self.resolved_names[key] = (spelling, plan_key)
            return
        if existing[1] == plan_key:
            return
        self._diagnose(
            LoadDiagnosticKind.FOLDED_NAME_COLLISION,
            spelling,
            f"{existing[0]!r} and {spelling!r} fold to one project key but resolve to different "
            f"artifacts; keeping {existing[0]!r}",
            code_path,
        )

    def resolve_artifact(
        self,
        name: str,
        *,
        program_name: str,
        dependency: str | None,
        code_path: Path,
        resolved_base: Path,
    ) -> ResolvedArtifact:
        """Find the sidecar and declared dependencies of an already resolved body.

        The planner resolves the code body first, so it can recognise a spelling
        that reaches an already planned artifact before any sidecar is read.
        Everything else about the artifact is resolved here.
        """
        library = resolved_base.name
        self._report_collisions(name, program_name, resolved_base)
        # The sidecar belongs to the selected body's prefix; see
        # ProjectLookup.find_deps_beside.
        deps_path = self._lookup.find_deps_beside(code_path, name)
        sidecar = SidecarState.ABSENT
        if deps_path is None:
            # A sidecar in the other family sits at the body's own prefix. Probe
            # for it directly, because a mode-filtered root-ordered search never
            # sees the other family and official mode would report a plain miss.
            same_prefix = find_companion_beside(code_path, sorted(ALL_DEPS_EXTENSIONS), index=self._companions)
            stray = self._lookup.find_deps(name)
            if same_prefix is not None:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_FAMILY_MISMATCH,
                    name,
                    f"sidecar {same_prefix.name!r} does not match the artifact family of body "
                    f"{code_path.name!r}; not paired",
                    same_prefix,
                )
            elif stray is not None:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_ELSEWHERE,
                    name,
                    f"sidecar {stray.name!r} is not beside body {code_path.name!r}; not paired",
                    stray,
                )
            else:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_MISSING,
                    name,
                    f"no dependency sidecar beside {code_path.name!r}",
                    code_path,
                )
        dependencies = self._read_deps(name, deps_path, program_name, dependency)
        if deps_path is not None:
            sidecar = SidecarState.PRESENT if dependencies else SidecarState.EMPTY
            if sidecar is SidecarState.EMPTY:
                self._diagnose(
                    LoadDiagnosticKind.SIDECAR_EMPTY,
                    name,
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

    def _report_collisions(self, name: str, program_name: str, base: Path) -> None:
        """Report files in *base* whose stems fold to *name*'s unit identity."""
        for collision in self._lookup.collisions_for(name, base):
            names = ", ".join(repr(path.name) for path in collision.paths)
            self._diagnose(
                LoadDiagnosticKind.FOLDED_NAME_COLLISION,
                program_name,
                f"{names} fold to one unit name; using {collision.winner.name!r}",
                collision.winner,
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
                path=deps_path,
            ) from exc


#: The artifact resolver the planner uses: the loader's own method by default.
#: It receives the code path and base the planner already resolved, so a
#: spelling that reaches a planned body never causes a sidecar read.
ArtifactResolver = Callable[..., ResolvedArtifact]
