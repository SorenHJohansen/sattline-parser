"""Project-wide definition and usage index.

A loaded project knows every unit it holds, so it can answer two questions a
single file cannot: which loaded unit defines a name, and which loaded unit uses
it. :class:`ProjectIndex` builds both answers once from the parsed trees, keyed
by :func:`sattline_parser.names.fold_identifier`, and returns them in a stable
order.

The index records *where* a name appears, not what it resolves to. A variable
reference is a use even when the variable is a parameter of another unit, and a
module-type instance is a use even when the definition was not loaded. That is
the point: a consumer asks the index which units touch a name, then decides
what the relationship means, or lets validation report a name that resolved
nowhere.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    ModuleTypeDef,
    ModuleTypeInstance,
    SourceSpan,
    Variable,
)
from sattline_parser.models.expressions import VarRef
from sattline_parser.models.walk import walk

from .identity import UnitIdentity
from .models import SattLineProgram

__all__ = ["DefinitionSite", "ProjectIndex", "SymbolKind", "UsageSite"]


class SymbolKind(StrEnum):
    """The kind of definition or use one site records."""

    PROGRAM = "program"
    DATATYPE = "datatype"
    MODULETYPE = "moduletype"
    VARIABLE = "variable"


@dataclass(frozen=True, slots=True)
class DefinitionSite:
    """One place a name is declared.

    ``name`` is the spelling the declaration wrote, ``kind`` what it declares,
    and ``program`` the loaded unit that holds it. ``library`` is the
    unit's library label when the load recorded one. ``span`` is the
    declaration's source range when the node carries one.
    """

    name: str
    kind: SymbolKind
    program: str
    library: str | None
    span: SourceSpan | None


@dataclass(frozen=True, slots=True)
class UsageSite:
    """One place a name is referenced.

    ``name`` is the spelling the reference wrote. ``program`` is the loaded unit
    that holds the reference, and ``library`` its library label when
    known. ``span`` is the reference's source range when the node carries one.
    """

    name: str
    kind: SymbolKind
    program: str
    library: str | None
    span: SourceSpan | None


class ProjectIndex:
    """Definitions and uses across one loaded project.

    Build it from a unit mapping; :attr:`SattLineProject.index` does that on
    first access. Lookups are case-insensitive, using the language's identifier
    folding, and each result is sorted by unit name and then source offset,
    so two runs over the same project return the same tuples.
    """

    def __init__(self, programs: Mapping[str, SattLineProgram]) -> None:
        definitions: dict[str, list[DefinitionSite]] = {}
        usages: dict[str, list[UsageSite]] = {}
        ordered = sorted(programs.values(), key=lambda program: (UnitIdentity.of(program.name).key, program.name))
        for program in ordered:
            library = program.library
            for site in _program_sites(program.code, program=program.name, library=library):
                if isinstance(site, DefinitionSite):
                    definitions.setdefault(UnitIdentity.of(site.name).key, []).append(site)
                else:
                    usages.setdefault(UnitIdentity.of(site.name).key, []).append(site)
        self._definitions = {key: _sorted_definitions(sites) for key, sites in definitions.items()}
        self._usages = {key: _sorted_usages(sites) for key, sites in usages.items()}

    def definitions_of(self, name: str, *, kind: SymbolKind | None = None) -> tuple[DefinitionSite, ...]:
        """Every loaded declaration that writes *name*, in project order.

        Pass ``kind`` to select one declaration kind, such as only
        ``SymbolKind.MODULETYPE`` definitions.
        """
        sites = self._definitions.get(UnitIdentity.of(name).key, ())
        if kind is None:
            return sites
        return tuple(site for site in sites if site.kind is kind)

    def usages_of(self, name: str, *, kind: SymbolKind | None = None) -> tuple[UsageSite, ...]:
        """Every loaded reference that writes *name*, in project order.

        Pass ``kind`` to select one reference kind, such as only
        ``SymbolKind.MODULETYPE`` instances.
        """
        sites = self._usages.get(UnitIdentity.of(name).key, ())
        if kind is None:
            return sites
        return tuple(site for site in sites if site.kind is kind)

    def defined_names(self, *, kind: SymbolKind | None = None) -> tuple[str, ...]:
        """Every defined spelling that has at least one declaration site.

        A name is reported once, under the alphabetically first spelling any
        site wrote, so the result can be fed back into :meth:`definitions_of`.
        Pass ``kind`` to report only names with a declaration of that kind.
        """
        spellings: dict[str, str] = {}
        for sites in self._definitions.values():
            for site in sites:
                if kind is not None and site.kind is not kind:
                    continue
                current = spellings.get(UnitIdentity.of(site.name).key)
                if current is None or site.name < current:
                    spellings[UnitIdentity.of(site.name).key] = site.name
        return tuple(spellings[key] for key in sorted(spellings))


def _program_sites(code: BasePicture, *, program: str, library: str | None) -> Iterable[DefinitionSite | UsageSite]:
    """Every declaration and use site in one program, in a single AST walk.

    Declarations and uses are classified independently, as they were when the
    index walked the tree twice, but one walk now feeds both answers.
    """
    yield DefinitionSite(
        name=program,
        kind=SymbolKind.PROGRAM,
        program=program,
        library=library,
        span=code.header.declaration_span,
    )
    for event in walk(code):
        node = event.node
        if isinstance(node, DataType):
            yield DefinitionSite(node.name, SymbolKind.DATATYPE, program, library, node.declaration_span)
        elif isinstance(node, ModuleTypeDef):
            yield DefinitionSite(node.name, SymbolKind.MODULETYPE, program, library, node.declaration_span)
        elif isinstance(node, Variable):
            yield DefinitionSite(node.name, SymbolKind.VARIABLE, program, library, node.declaration_span)
        if isinstance(node, VarRef):
            yield UsageSite(node.name, SymbolKind.VARIABLE, program, library, node.span)
        elif isinstance(node, ModuleTypeInstance):
            yield UsageSite(
                node.moduletype_name,
                SymbolKind.MODULETYPE,
                program,
                library,
                node.header.declaration_span,
            )


def _sorted_definitions(sites: list[DefinitionSite]) -> tuple[DefinitionSite, ...]:
    unique = {(site.name, site.kind, site.program, site.library, site.span): site for site in sites}
    return tuple(
        sorted(
            unique.values(),
            key=lambda site: (
                UnitIdentity.of(site.program).key,
                _span_start(site.span),
                UnitIdentity.of(site.name).key,
            ),
        )
    )


def _sorted_usages(sites: list[UsageSite]) -> tuple[UsageSite, ...]:
    unique = {(site.name, site.kind, site.program, site.library, site.span): site for site in sites}
    return tuple(
        sorted(
            unique.values(),
            key=lambda site: (
                UnitIdentity.of(site.program).key,
                _span_start(site.span),
                UnitIdentity.of(site.name).key,
            ),
        )
    )


def _span_start(span: SourceSpan | None) -> int:
    return -1 if span is None else span.start
