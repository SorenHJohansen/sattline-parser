"""Parse+validate helpers shared by ``check``, ``diff`` and ``corpus``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sattline_parser.api import parse_and_validate
from sattline_parser.ast import BasePicture, FrameModule, ModuleTypeDef, SingleModule
from sattline_parser.errors import PARSE_FAILURES
from sattline_parser.preprocessing import is_compressed

from ._findings import Finding, finding_from_diagnostic, finding_from_parse_error

__all__ = ["Analysis", "analyse", "summarise"]

_ModuleNode = BasePicture | SingleModule | FrameModule | ModuleTypeDef


def _module_nodes(root: BasePicture) -> list[_ModuleNode]:
    """Every module body in the file, the root and each nested declaration.

    A module-type instance is a reference, not a body, so it contributes to the
    submodule count but is not descended into. A module-type definition is a body
    and is counted, so a template's declarations are not silently skipped.
    """
    nodes: list[_ModuleNode] = []
    stack: list[_ModuleNode] = [root]
    while stack:
        node = stack.pop()
        nodes.append(node)
        if isinstance(node, BasePicture):
            stack.extend(node.moduletype_defs)
        stack.extend(child for child in node.submodules if isinstance(child, (SingleModule, FrameModule)))
    return nodes


@dataclass(frozen=True, slots=True)
class Analysis:
    """What one source produced: its findings and, when it parsed, its summary."""

    findings: tuple[Finding, ...]
    summary: dict[str, Any] | None


def analyse(name: str, text: str, *, absolute: bool) -> Analysis:
    """Parse and validate one source; a failure is one finding, never an exception."""
    try:
        picture, diagnostics = parse_and_validate(text, log_failures=False)
    except PARSE_FAILURES as exc:
        return Analysis(
            findings=(finding_from_parse_error(exc, text, file=name, absolute_paths=absolute),),
            summary=None,
        )
    findings = tuple(
        finding_from_diagnostic(diagnostic, file=name, source_text=text, absolute_paths=absolute)
        for diagnostic in diagnostics
    )
    return Analysis(findings=findings, summary=summarise(name, text, picture))


def summarise(name: str, text: str, picture: BasePicture, *, coded: bool = False) -> dict[str, Any]:
    """A structural summary of one unit (used by ``parse`` and ``diff``).

    The counts cover the whole module tree: nested submodules and module-type
    bodies contribute their declarations, sequences, equation blocks, and
    objects, so the summary agrees with a walk over the picture.
    """
    module_nodes = _module_nodes(picture)
    return {
        "file": name,
        "program": picture.program_name,
        "name": picture.name,
        "encoding": "coded" if coded or is_compressed(text) else "plain",
        "counts": {
            "module_types": sum(isinstance(node, ModuleTypeDef) for node in module_nodes),
            "submodules": sum(len(node.submodules) for node in module_nodes),
            "local_variables": sum(len(node.localvariables) for node in module_nodes),
            "sequences": sum(
                len(node.modulecode.sequences or ()) for node in module_nodes if node.modulecode is not None
            ),
            "equationblocks": sum(
                len(node.modulecode.equationblocks or ()) for node in module_nodes if node.modulecode is not None
            ),
            "graph_objects": sum(
                len(node.moduledef.graph_objects or ()) for node in module_nodes if node.moduledef is not None
            ),
            "interact_objects": sum(
                len(node.moduledef.interact_objects or ()) for node in module_nodes if node.moduledef is not None
            ),
        },
    }
