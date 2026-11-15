"""The validation phase: what a loaded project says is wrong.

This module owns validation scope and finding aggregation, and nothing about
discovery, parsing, or companion attachment. It reads the assembled registry,
so it is constructed with references to the containers the planner and
assembler fill.

The registry is a live mapping: assembly fills it in post-order, and
``validate_invoked`` rewrites an entry in place after the whole graph exists.
The validator never creates or removes entries.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from sattline_parser.models.ast_model import BasePicture, DataType, ModuleTypeDef, SourceSpan
from sattline_parser.names import fold_identifier
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode

from ._cycles import first_cycle
from .errors import ModuleTypeCycleError
from .models import LoadValidation, SattLineProgram
from .plan import ResolvedArtifact
from .reachability import invoked_moduletypes, iter_moduletype_refs

__all__ = ["ProjectValidator"]


class ProjectValidator:
    """Resolve the validation scope and aggregate one project's findings.

    ``registry`` maps plan key to assembled unit; ``resolved_dependencies`` maps
    a plan key to its dependency keys; ``target_plan_keys`` is the set of units
    the caller explicitly asked for. The three containers are owned by the
    loader orchestration and shared by reference.
    """

    def __init__(
        self,
        *,
        validate: LoadValidation,
        registry: dict[str, SattLineProgram],
        resolved_dependencies: Mapping[str, tuple[str, ...]],
        target_plan_keys: set[str],
    ) -> None:
        self._validate = validate
        self._registry = registry
        self._resolved_dependencies = resolved_dependencies
        self._target_plan_keys = target_plan_keys
        self._moduletype_versions: dict[str, dict[int, set[str]]] = {}
        self._datatype_versions: dict[str, dict[int, set[str]]] = {}
        self._labels: dict[str, str] = {}

    def artifact_diagnostics(
        self,
        basepicture: BasePicture,
        *,
        key: str,
        artifact: ResolvedArtifact,
    ) -> tuple[Diagnostic, ...]:
        if self._validate is not LoadValidation.INVOKED:
            return self._program_diagnostics(
                basepicture,
                dependencies=self._resolved_dependencies.get(key, ()),
                library=artifact.library,
                file_name=artifact.code_path.name,
                key=key,
            )
        # Module diagnostics need the whole graph. Datecode findings belong to
        # an explicitly selected unit; a library import is not the place to
        # report its own version drift. Ownership comes from the target set, not
        # from discovery order, so a target that was first reached as a
        # dependency still reports its own conflict whatever the target order.
        if key not in self._target_plan_keys:
            return ()
        return tuple(
            self._datecode_conflicts(
                basepicture,
                library=artifact.library,
                file_name=artifact.code_path.name,
                visible=self.visible_plan_keys(key),
            )
        )

    def remember_definitions(
        self,
        basepicture: BasePicture,
        *,
        library: str,
        file_name: str,
        program_key: str,
    ) -> None:
        self._labels[program_key] = f"{library}/{file_name}"
        for moduletype in basepicture.moduletype_defs:
            if moduletype.datecode is not None:
                self._moduletype_versions.setdefault(fold_identifier(moduletype.name), {}).setdefault(
                    moduletype.datecode, set()
                ).add(program_key)
        for datatype in basepicture.datatype_defs:
            if datatype.datecode is not None:
                self._datatype_versions.setdefault(fold_identifier(datatype.name), {}).setdefault(
                    datatype.datecode, set()
                ).add(program_key)

    def assert_no_moduletype_cycles(self) -> None:
        """Reject a module type whose instantiation chain returns to itself.

        Each unit is checked against its visible closure, and a node is one
        *definition* (owning unit plus folded name), so two libraries that
        reuse a name are two nodes, not one. A reference resolves to the
        referencing file's own definition first, then to any definition in the
        checked unit's closure, which keeps a library that shadows a
        dependency's type name from looking recursive. Only the first cycle
        matters, and a graph can hold exponentially many elementary cycles, so
        the search stops as soon as it finds one.
        """
        for key in self._registry:
            visible_keys = self.visible_plan_keys(key)
            edges, labels, owners = _moduletype_edges(self._registry, visible_keys)
            cycle = first_cycle(edges)
            if cycle is not None:
                display = tuple(labels[node] for node in cycle)
                raise ModuleTypeCycleError(owners[cycle[0]], display)

    def validate_invoked(self) -> None:
        """Add diagnostics for the module types each target actually invokes."""
        reachable = invoked_moduletypes(
            self._registry,
            self._target_plan_keys,
            closure_of=self.visible_plan_keys,
        )
        for key, program in list(self._registry.items()):
            dependencies = self._resolved_dependencies.get(key, ())
            if key in self._target_plan_keys:
                module_diagnostics = self._validate_code(program.code, dependencies=dependencies)
            else:
                names = reachable.get(key)
                if not names:
                    continue
                module_diagnostics = self._validate_code(
                    self._invoked_view(program.code, names),
                    dependencies=dependencies,
                )
            diagnostics = [*program.diagnostics, *module_diagnostics]
            self._registry[key] = replace(program, diagnostics=tuple(diagnostics))

    def closure(self, dependencies: Sequence[str]) -> frozenset[str]:
        """Plan keys of every unit a set of resolved dependencies reaches."""
        closure: set[str] = set()
        pending = list(dependencies)
        while pending:
            key = pending.pop()
            if key in closure:
                continue
            closure.add(key)
            pending.extend(self._resolved_dependencies.get(key, ()))
        return frozenset(closure)

    def visible_plan_keys(self, key: str) -> frozenset[str]:
        """Keys of every unit *key* can see: itself plus its transitive deps."""
        return frozenset({key}) | self.closure(self._resolved_dependencies.get(key, ()))

    def _visible_definitions(
        self, dependencies: Sequence[str]
    ) -> tuple[tuple[DataType, ...], tuple[ModuleTypeDef, ...]]:
        """Definitions from this unit's transitive dependency closure.

        The registry is dependency-first, so filtering it by the closure keeps
        a deterministic order. Using the whole registry here would let an
        unrelated target's types hide an unknown-name finding.
        """
        closure = self.closure(dependencies)
        datatypes: list[DataType] = []
        moduletypes: list[ModuleTypeDef] = []
        for key, program in self._registry.items():
            if key not in closure:
                continue
            datatypes.extend(program.code.datatype_defs)
            moduletypes.extend(program.code.moduletype_defs)
        return tuple(datatypes), tuple(moduletypes)

    def _validate_code(self, code: BasePicture, *, dependencies: Sequence[str]) -> tuple[Diagnostic, ...]:
        visible_datatypes, visible_moduletypes = self._visible_definitions(dependencies)
        return validate_basepicture(
            code,
            external_datatypes=visible_datatypes,
            external_moduletype_defs=visible_moduletypes,
        )

    @staticmethod
    def _invoked_view(basepicture: BasePicture, names: set[str]) -> BasePicture:
        """A copy that contains only the invoked module types from one file."""
        selected = [moduletype for moduletype in basepicture.moduletype_defs if moduletype.name.casefold() in names]
        return replace(
            basepicture,
            moduletype_defs=selected,
            submodules=[],
            moduledef=None,
            modulecode=None,
            localvariables=[],
        )

    def _program_diagnostics(
        self,
        basepicture: BasePicture,
        *,
        dependencies: Sequence[str],
        library: str,
        file_name: str,
        key: str,
    ) -> tuple[Diagnostic, ...]:
        if self._validate is LoadValidation.NONE:
            return ()
        visible_datatypes, visible_moduletypes = self._visible_definitions(dependencies)
        diagnostics = list(
            validate_basepicture(
                basepicture,
                external_datatypes=visible_datatypes,
                external_moduletype_defs=visible_moduletypes,
            )
        )
        diagnostics.extend(
            self._datecode_conflicts(
                basepicture,
                library=library,
                file_name=file_name,
                visible=self.visible_plan_keys(key),
            )
        )
        return tuple(diagnostics)

    def _versions_in_scope(
        self,
        table: dict[str, dict[int, set[str]]],
        name: str,
        visible: frozenset[str],
    ) -> dict[int, set[str]] | None:
        """Datecodes declared for *name* by units in *visible*."""
        entry = table.get(fold_identifier(name))
        if not entry:
            return None
        known: dict[int, set[str]] = {}
        for datecode, keys in entry.items():
            in_scope = keys & visible
            if in_scope:
                known[datecode] = {self._labels[key] for key in in_scope if key in self._labels}
        return known or None

    def _datecode_conflicts(
        self,
        basepicture: BasePicture,
        *,
        library: str,
        file_name: str,
        visible: frozenset[str],
    ) -> list[Diagnostic]:
        source_label = f"{library}/{file_name}"
        conflicts: list[Diagnostic] = []
        for moduletype in basepicture.moduletype_defs:
            conflict = _datecode_conflict(
                "moduletype",
                moduletype.name,
                moduletype.datecode,
                self._versions_in_scope(self._moduletype_versions, moduletype.name, visible),
                source_label=source_label,
                span=moduletype.declaration_span,
            )
            if conflict is not None:
                conflicts.append(conflict)
        for datatype in basepicture.datatype_defs:
            conflict = _datecode_conflict(
                "datatype",
                datatype.name,
                datatype.datecode,
                self._versions_in_scope(self._datatype_versions, datatype.name, visible),
                source_label=source_label,
                span=datatype.declaration_span,
            )
            if conflict is not None:
                conflicts.append(conflict)
        return conflicts


def _moduletype_edges(
    programs: dict[str, SattLineProgram],
    visible_keys: frozenset[str],
) -> tuple[list[tuple[str, str]], dict[str, str], dict[str, str]]:
    """The instantiation edges among the definitions visible from one unit.

    A node is one definition, identified by its owning unit and folded name, so
    two units may each define a type of the same name without becoming a
    cycle. Returns the edges plus the display name and owning unit of every
    node the cycle report needs.
    """
    index: dict[str, list[tuple[str, ModuleTypeDef]]] = {}
    for visible_key in sorted(visible_keys):
        program = programs[visible_key]
        for moduletype in program.code.moduletype_defs:
            index.setdefault(fold_identifier(moduletype.name), []).append((visible_key, moduletype))
    labels: dict[str, str] = {}
    owners: dict[str, str] = {}
    edges: list[tuple[str, str]] = []

    def node_for(owner_key: str, moduletype: ModuleTypeDef) -> str:
        node = f"{owner_key}\x00{fold_identifier(moduletype.name)}"
        labels.setdefault(node, moduletype.name)
        owners.setdefault(node, programs[owner_key].name)
        return node

    for folded_name in sorted(index):
        for owner_key, moduletype in index[folded_name]:
            node = node_for(owner_key, moduletype)
            for reference in iter_moduletype_refs(moduletype.submodules):
                folded = fold_identifier(reference)
                candidates = index.get(folded, ())
                # A local definition wins, then any visible definition: the
                # check asks whether this closure's definitions instantiate
                # themselves, not whether every edge is load-order legal.
                local = [entry for entry in candidates if entry[0] == owner_key] or candidates
                for target_key, target in local:
                    edges.append((node, node_for(target_key, target)))
    return edges, labels, owners


def _datecode_conflict(
    kind: str,
    name: str,
    datecode: int | None,
    known: dict[int, set[str]] | None,
    *,
    source_label: str,
    span: SourceSpan | None,
) -> Diagnostic | None:
    if datecode is None or not known:
        return None
    others = {version: labels for version, labels in known.items() if version != datecode}
    if not others:
        return None
    detail = ", ".join(f"{version} in {', '.join(sorted(labels))}" for version, labels in sorted(others.items()))
    return Diagnostic(
        code=DiagnosticCode.DATECODE_CONFLICT,
        message=f"{kind} {name!r} datecode {datecode} in {source_label} conflicts with {detail}",
        span=span,
    )
