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

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from sattline_parser.models.ast_model import BasePicture, DataType, ModuleTypeDef, SourceSpan
from sattline_parser.names import fold_identifier
from sattline_parser.validation import validate_basepicture
from sattline_parser.validation.declarations import check_type_references
from sattline_parser.validation.diagnostics import Diagnostic, DiagnosticCode
from sattline_parser.validation.validator import validate_moduletype_definitions

from ._cycles import first_cycle
from .errors import ModuleTypeCycleError
from .models import LoadValidation, SattLineProgram
from .plan import ResolvedArtifact
from .reachability import invoked_moduletypes, iter_moduletype_refs

__all__ = ["ProjectValidator"]

_TYPE_REFERENCE_CODES = frozenset(
    {
        DiagnosticCode.BUILTIN_DATATYPE_TYPO,
        DiagnosticCode.UNKNOWN_DATATYPE_NAME,
        DiagnosticCode.UNKNOWN_MODULETYPE_NAME,
    }
)


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

    def artifact_diagnostics(
        self,
        basepicture: BasePicture,
        *,
        key: str,
        artifact: ResolvedArtifact,
    ) -> tuple[Diagnostic, ...]:
        dependencies = self._resolved_dependencies.get(key, ())
        datatypes, moduletypes = self._visible_definitions(dependencies)
        binding_diagnostics: list[Diagnostic] = []
        check_type_references(
            basepicture,
            binding_diagnostics,
            external_datatypes=datatypes,
            external_moduletype_defs=moduletypes,
        )
        if self._validate is not LoadValidation.INVOKED:
            return (
                *binding_diagnostics,
                *self._program_diagnostics(
                    basepicture,
                    dependencies=dependencies,
                    library=artifact.library,
                    file_name=artifact.code_path.name,
                    key=key,
                ),
            )
        # Module diagnostics need the whole graph. Datecode findings belong to
        # an explicitly selected unit; a library import is not the place to
        # report its own version drift. Ownership comes from the target set, not
        # from discovery order, so a target that was first reached as a
        # dependency still reports its own conflict whatever the target order.
        if key not in self._target_plan_keys:
            return tuple(binding_diagnostics)
        return (
            *binding_diagnostics,
            *tuple(
                self._datecode_conflicts(
                    basepicture,
                    library=artifact.library,
                    file_name=artifact.code_path.name,
                )
            ),
        )

    def assert_no_moduletype_cycles(self) -> None:
        """Reject a module type whose instantiation chain returns to itself.

        A node is one *definition* (owning unit plus folded name), so two
        libraries that reuse a name are two nodes, not one. A reference is
        resolved against the closure of the unit that holds it, never against
        the closure of the unit being checked, because a definition binds to
        what its own file can see. Checking a wrapper therefore cannot make a
        dependency's reference point at the wrapper's same-named type. A local
        definition wins first, then any definition the referencing unit's own
        closure holds.

        Only a cycle whose definitions all lie in the checked unit's closure is
        reported, so an unrelated branch of the registry can never fail this
        unit's load. Only the first cycle matters, and a graph can hold
        exponentially many elementary cycles, so the search stops as soon as it
        finds one.
        """
        edges_by_owner, labels, owners = _moduletype_edges(self._registry, self.visible_plan_keys)
        for key in self._registry:
            visible_keys = self.visible_plan_keys(key)
            edges = [edge for owner_key in sorted(visible_keys) for edge in edges_by_owner.get(owner_key, ())]
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
                visible_datatypes, visible_moduletypes = self._visible_definitions(dependencies)
                module_diagnostics = tuple(
                    diagnostic
                    for diagnostic in validate_moduletype_definitions(
                        program.code,
                        self._invoked_view(program.code, names),
                        external_datatypes=visible_datatypes,
                        external_moduletype_defs=visible_moduletypes,
                    )
                    if diagnostic.code not in _TYPE_REFERENCE_CODES
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
        return tuple(
            diagnostic
            for diagnostic in validate_basepicture(
                code,
                external_datatypes=visible_datatypes,
                external_moduletype_defs=visible_moduletypes,
            )
            if diagnostic.code not in _TYPE_REFERENCE_CODES
        )

    @staticmethod
    def _invoked_view(basepicture: BasePicture, names: set[str]) -> BasePicture:
        """A view for selecting module types and collecting their SFC names."""
        selected = [
            moduletype for moduletype in basepicture.moduletype_defs if fold_identifier(moduletype.name) in names
        ]
        return replace(
            basepicture,
            datatype_defs=[],
            moduletype_defs=selected,
            moduleparameters=[],
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
        diagnostics = list(self._validate_code(basepicture, dependencies=dependencies))
        diagnostics.extend(
            self._datecode_conflicts(
                basepicture,
                library=library,
                file_name=file_name,
            )
        )
        return tuple(diagnostics)

    def _datecode_conflicts(
        self,
        basepicture: BasePicture,
        *,
        library: str,
        file_name: str,
    ) -> list[Diagnostic]:
        """Report a name this unit declares with two different datecodes.

        A declaration shadows a same-named declaration held by a dependency, so
        versions held by other units never conflict with this one. Only the
        unit's own declarations are compared.
        """
        source_label = f"{library}/{file_name}"
        moduletype_versions: dict[str, dict[int, set[str]]] = {}
        for moduletype in basepicture.moduletype_defs:
            if moduletype.datecode is not None:
                moduletype_versions.setdefault(fold_identifier(moduletype.name), {}).setdefault(
                    moduletype.datecode, set()
                ).add(source_label)
        datatype_versions: dict[str, dict[int, set[str]]] = {}
        for datatype in basepicture.datatype_defs:
            if datatype.datecode is not None:
                datatype_versions.setdefault(fold_identifier(datatype.name), {}).setdefault(
                    datatype.datecode, set()
                ).add(source_label)

        conflicts: list[Diagnostic] = []
        reported: set[tuple[str, str]] = set()

        def conflict_for(
            kind: str,
            name: str,
            datecode: int | None,
            versions: dict[str, dict[int, set[str]]],
            span: SourceSpan | None,
        ) -> None:
            key = (kind, fold_identifier(name))
            if key in reported:
                return
            conflict = _datecode_conflict(
                kind,
                name,
                datecode,
                versions.get(fold_identifier(name)),
                source_label=source_label,
                span=span,
            )
            if conflict is not None:
                reported.add(key)
                conflicts.append(conflict)

        for moduletype in basepicture.moduletype_defs:
            conflict_for(
                "moduletype",
                moduletype.name,
                moduletype.datecode,
                moduletype_versions,
                moduletype.declaration_span,
            )
        for datatype in basepicture.datatype_defs:
            conflict_for(
                "datatype",
                datatype.name,
                datatype.datecode,
                datatype_versions,
                datatype.declaration_span,
            )
        return conflicts


def _moduletype_edges(
    programs: Mapping[str, SattLineProgram],
    closure_of: Callable[[str], frozenset[str]],
) -> tuple[dict[str, tuple[tuple[str, str], ...]], dict[str, str], dict[str, str]]:
    """The instantiation edges of every definition, grouped by owning unit.

    A node is one definition, identified by its owning unit and folded name, so
    two units may each define a type of the same name without becoming a
    cycle. Each definition's references are resolved against the closure of the
    unit that holds it (:func:`closure_of`), because a reference binds to what
    its own file can see. Returns the edges grouped by the source definition's
    owner, plus the display name and owning unit of every node the cycle report
    needs. The caller selects the owners that belong to the closure it checks,
    which is what keeps an unrelated closure's cycle out of this unit's result.
    """
    index: dict[str, list[tuple[str, ModuleTypeDef]]] = {}
    for program_key, program in programs.items():
        for moduletype in program.code.moduletype_defs:
            index.setdefault(fold_identifier(moduletype.name), []).append((program_key, moduletype))
    labels: dict[str, str] = {}
    owners: dict[str, str] = {}
    edges_by_owner: dict[str, list[tuple[str, str]]] = {}

    def node_for(owner_key: str, moduletype: ModuleTypeDef) -> str:
        node = f"{owner_key}\x00{fold_identifier(moduletype.name)}"
        labels.setdefault(node, moduletype.name)
        owners.setdefault(node, programs[owner_key].name)
        return node

    def targets_for(owner_key: str, reference: str) -> list[tuple[str, ModuleTypeDef]]:
        candidates = index.get(fold_identifier(reference), ())
        local = [entry for entry in candidates if entry[0] == owner_key]
        if local:
            return local
        visible = closure_of(owner_key)
        return [entry for entry in candidates if entry[0] in visible]

    for owner_key, program in programs.items():
        outgoing = edges_by_owner.setdefault(owner_key, [])
        for moduletype in program.code.moduletype_defs:
            node = node_for(owner_key, moduletype)
            for reference in iter_moduletype_refs(moduletype.submodules):
                for target_key, target in targets_for(owner_key, reference):
                    outgoing.append((node, node_for(target_key, target)))
    return {owner_key: tuple(edges) for owner_key, edges in edges_by_owner.items()}, labels, owners


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
