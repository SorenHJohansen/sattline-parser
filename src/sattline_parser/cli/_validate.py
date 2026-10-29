"""Parse+validate helpers shared by ``check``, ``diff`` and ``corpus``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lark.exceptions import UnexpectedInput

from sattline_parser.api import parse_and_validate
from sattline_parser.models.ast_model import BasePicture
from sattline_parser.preprocessing import PreprocessError, is_compressed

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
    except (UnexpectedInput, PreprocessError) as exc:
        return Analysis(
            findings=(finding_from_parse_error(exc, text, file=name, absolute_paths=absolute),),
            summary=None,
        )
    findings = tuple(
        finding_from_diagnostic(diagnostic, file=name, source_text=text, absolute_paths=absolute)
        for diagnostic in diagnostics
    )
    return Analysis(findings=findings, summary=summarise(name, text, picture))


def summarise(name: str, text: str, picture: BasePicture) -> dict[str, Any]:
    """A structural summary of one unit (used by ``parse`` and ``diff``)."""
    moduledef = picture.moduledef
    modulecode = picture.modulecode
    return {
        "file": name,
        "program": picture.program_name,
        "name": picture.name,
        "encoding": "coded" if is_compressed(text) else "plain",
        "counts": {
            "module_types": len(picture.moduletype_defs),
            "submodules": len(picture.submodules),
            "local_variables": len(picture.localvariables),
            "sequences": len(modulecode.sequences or ()) if modulecode is not None else 0,
            "equations": len(modulecode.equations or ()) if modulecode is not None else 0,
            "graph_objects": len(moduledef.graph_objects or ()) if moduledef is not None else 0,
            "interact_objects": len(moduledef.interact_objects or ()) if moduledef is not None else 0,
        },
    }
