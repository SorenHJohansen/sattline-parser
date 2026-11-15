"""The assembly phase: turn parsed plans into the canonical registry.

Assembly is where a parsed body becomes a :class:`SattLineProgram`: its origin is
stamped, its diagnostics are computed, its definitions are recorded for datecode
conflicts, and its graphics and distribution companions are attached. It runs in
plan order, which is post-order, so every dependency is registered before its
consumer.

Companion loading is injected so a caller can substitute it, and a companion
failure is an artifact failure rather than a load diagnostic: an unreadable file
must never be reported as "no companion".
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from sattline_parser.models.ast_model import BasePicture

from .distribution import (
    DistributionParseError,
    parse_distribution_file,
    resolve_distribution_companion_path,
)
from .errors import ArtifactLoadError, DependencyParseError, ProjectLoadError
from .executor import ParseOutcome, rebuild_parse_failure
from .formats import body_mode
from .graphics_parsing import (
    GraphicsParseError,
    parse_graphics_file,
    resolve_graphics_companion_path,
)
from .models import DistributionData, GraphicsModel, LoadMode, ProgramFormat, SattLineProgram
from .plan import Plan, dependency_of, program_of
from .scope import ProjectValidator

__all__ = ["ProjectAssembler"]


class ProjectAssembler:
    """Build the plan-key registry from parsed bodies and their companions."""

    def __init__(
        self,
        *,
        mode: LoadMode,
        registry: dict[str, SattLineProgram],
        validator: ProjectValidator,
        debug: Callable[[str], None] | None,
        companion_loader: CompanionLoader | None = None,
    ) -> None:
        self._mode = mode
        self._registry = registry
        self._validator = validator
        self._debug = debug
        self._companion_loader = companion_loader or self._load_companion

    def _dbg(self, message: str) -> None:
        if self._debug is not None:
            self._debug(message)

    def assemble(
        self,
        plans: Sequence[Plan],
        *,
        outcomes: Mapping[str, ParseOutcome],
    ) -> None:
        """Attach every parsed plan to the registry, in plan order."""
        for plan in plans:
            self._assemble_one(plan, outcomes[plan.key])

    def _assemble_one(self, plan: Plan, outcome: ParseOutcome) -> None:
        artifact = plan.artifact
        basepicture = outcome.ast
        if basepicture is None:
            error = _parse_failure(program_of(plan), artifact.code_path.name, dependency_of(plan))
            cause = outcome.error
            if cause is None and outcome.failure_record is not None:
                cause = rebuild_parse_failure(outcome.failure_record)
            raise error from (cause or RuntimeError(outcome.failure))
        _set_origin(basepicture, file_name=artifact.code_path.name, library=artifact.library)
        self._assemble_body(plan, basepicture)

    def _assemble_body(self, plan: Plan, basepicture: BasePicture) -> None:
        """Attach diagnostics, definitions, and companions, then register."""
        artifact = plan.artifact
        name = plan.name
        program_name = program_of(plan)
        dependency = dependency_of(plan)
        diagnostics = self._validator.artifact_diagnostics(
            basepicture,
            key=plan.key,
            artifact=artifact,
        )
        self._validator.remember_definitions(
            basepicture,
            library=artifact.library,
            file_name=artifact.code_path.name,
            program_key=plan.key,
        )

        graphics_path, graphics = self._companion_loader(
            artifact.code_path,
            name=name,
            program_name=program_name,
            dependency=dependency,
        )
        distribution_path, distribution = self._load_distribution(
            artifact.code_path,
            name=name,
            program_name=program_name,
            dependency=dependency,
        )
        self._registry[plan.key] = SattLineProgram(
            name=name,
            code=basepicture,
            graphics=graphics,
            dependencies=artifact.dependencies,
            format=ProgramFormat(
                mode=body_mode(artifact.code_path.suffix, self._mode),
                code_ext=artifact.code_path.suffix.lower(),
                graphics_ext=graphics_path.suffix.lower() if graphics_path is not None else None,
                deps_ext=artifact.deps_path.suffix.lower() if artifact.deps_path is not None else None,
                distribution_ext=distribution_path.suffix.lower() if distribution_path is not None else None,
            ),
            source_path=artifact.code_path,
            deps_path=artifact.deps_path,
            sidecar=artifact.sidecar,
            library=artifact.library,
            resolved_base=artifact.resolved_base,
            distribution_path=distribution_path,
            distribution=distribution,
            diagnostics=diagnostics,
        )

    def _load_companion(
        self,
        code_path: Path,
        *,
        name: str,
        program_name: str,
        dependency: str | None,
    ) -> tuple[Path | None, GraphicsModel | None]:
        graphics_path = resolve_graphics_companion_path(code_path, mode=self._mode)
        if graphics_path is None:
            return None, None
        graphics = _load_graphics(
            self._dbg,
            graphics_path,
            program_name=program_name,
            dependency=dependency,
            name=name,
        )
        return graphics_path, graphics

    def _load_distribution(
        self,
        code_path: Path,
        *,
        name: str,
        program_name: str,
        dependency: str | None,
    ) -> tuple[Path | None, DistributionData | None]:
        """Read the distribution companion beside the selected body.

        A missing companion answers "unknown" and stays silent: distribution data
        is optional. A companion that exists but does not parse is an artifact
        failure, because an unreadable file must never be reported as "no
        executing system".
        """
        distribution_path = resolve_distribution_companion_path(code_path, mode=self._mode)
        if distribution_path is None:
            return None, None
        self._dbg(f"Parsing distribution: {distribution_path}")
        try:
            distribution = parse_distribution_file(distribution_path)
        except (OSError, UnicodeError, DistributionParseError) as exc:
            if dependency is None:
                raise ArtifactLoadError(
                    program_name,
                    f"failed to parse distribution companion {distribution_path.name} for {name!r}: {exc}",
                ) from exc
            raise DependencyParseError(
                program_name,
                f"failed to parse distribution companion for dependency {dependency!r}: {exc}",
                dependency=dependency,
            ) from exc
        return distribution_path, distribution


#: The companion callable the assembler uses: the loader's own method by default.
CompanionLoader = Callable[..., tuple[Path | None, "GraphicsModel | None"]]


def _parse_failure(program_name: str, code_name: str, dependency: str | None) -> ProjectLoadError:
    """The load error for a body that did not parse."""
    if dependency is None:
        return ArtifactLoadError(program_name, f"failed to parse {code_name}")
    return DependencyParseError(
        program_name,
        f"failed to parse dependency {dependency!r}",
        dependency=dependency,
    )


def _set_origin(basepicture: BasePicture, *, file_name: str, library: str) -> None:
    basepicture.origin_file = file_name
    basepicture.origin_lib = library
    for moduletype in basepicture.moduletype_defs:
        moduletype.origin_file = file_name
        moduletype.origin_lib = library
    for datatype in basepicture.datatype_defs:
        datatype.origin_file = file_name
        datatype.origin_lib = library


def _load_graphics(
    debug: Callable[[str], None],
    graphics_path: Path,
    *,
    program_name: str,
    dependency: str | None,
    name: str,
) -> GraphicsModel:
    debug(f"Parsing graphics: {graphics_path}")
    try:
        return parse_graphics_file(graphics_path)
    except (OSError, UnicodeError, GraphicsParseError) as exc:
        if dependency is None:
            raise ArtifactLoadError(
                program_name,
                f"failed to read graphics companion {graphics_path.name} for {name!r}: {exc}",
            ) from exc
        raise DependencyParseError(
            program_name,
            f"failed to read graphics companion for dependency {dependency!r}",
            dependency=dependency,
        ) from exc
