"""Parse+validate helpers shared by ``check``, ``diff`` and ``corpus``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sattline_parser.api import parse_and_validate
from sattline_parser.ast import BasePicture
from sattline_parser.errors import PARSE_FAILURES
from sattline_parser.preprocessing import is_compressed

from ._findings import Finding, finding_from_diagnostic, finding_from_parse_error

__all__ = ["Analysis", "analyse", "summarise"]


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
    """A structural summary of one unit (used by ``parse`` and ``diff``)."""
    return {
        "file": name,
        "program": picture.program_name,
        "name": picture.name,
        "encoding": "coded" if coded or is_compressed(text) else "plain",
        "counts": {
            "module_types": len(picture.moduletype_defs),
            "submodules": len(picture.submodules),
            "local_variables": len(picture.localvariables),
            "sequences": sum(len(code.sequences or ()) for code in picture.modulecodes),
            "equationblocks": sum(len(code.equationblocks or ()) for code in picture.modulecodes),
            "graph_objects": sum(len(module_def.graph_objects or ()) for module_def in picture.moduledefs),
            "interact_objects": sum(len(module_def.interact_objects or ()) for module_def in picture.moduledefs),
        },
    }
