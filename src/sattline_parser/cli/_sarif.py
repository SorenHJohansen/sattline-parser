"""SARIF 2.1.0 output for CI consumers.

A finding already carries a rule id, a location, and a message, which is most of
a SARIF result. This module maps the CLI finding shape onto a SARIF log so a
code-scanning service can annotate a pull request without a bespoke converter.

The mapping is mechanical and documented rather than clever:

* a validation finding's ``rule`` is the enum name, so its SARIF ``ruleId`` is
  the stable ``SL-V###`` id from the registry, and the registry supplies the
  summary;
* a synthetic finding (parse, decode, project, read) keeps its own id and a
  fixed summary;
* only rules that appear in the report are described, so the log stays small;
* a finding with a file and a line becomes a physical location, and one without
  a location stays a result with a message only.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from urllib.parse import quote

from sattline_parser.validation import Rule, find_rule

from ._findings import (
    DECODE_RULE,
    GRAPHICS_SCAN_RULE,
    PARSE_RULE,
    PROJECT_LOAD_RULE,
    PROJECT_QUERY_RULE,
    READ_RULE,
    Finding,
)
from ._json import dumps

__all__ = ["SARIF_SCHEMA", "SARIF_VERSION", "sarif_document", "sarif_json"]

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_TOOL_URI = "https://github.com/SorenHJohansen/sattline-parser"
_RULE_DOCS_URI = f"{_TOOL_URI}/blob/main/docs/validation.md#diagnostics"
_FINDING_DOCS_URI = f"{_TOOL_URI}/blob/main/docs/cli.md#the-finding-shape"

#: Summaries for the finding ids that are not validation rules.
_SYNTHETIC_RULES: dict[str, str] = {
    PARSE_RULE: "The source does not parse.",
    DECODE_RULE: "The source does not decode.",
    PROJECT_LOAD_RULE: "The project tree does not load.",
    PROJECT_QUERY_RULE: "The project graph has no such subject.",
    READ_RULE: "The source cannot be read.",
    GRAPHICS_SCAN_RULE: "A graphics companion reported a scan message.",
}


def sarif_document(findings: Sequence[Finding], *, version: str) -> dict[str, object]:
    """A SARIF 2.1.0 log for *findings*.

    *version* is the tool version reported in the driver. Results keep the
    finding order, so the document is stable for a stable input.
    """
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "sattline",
                        "informationUri": _TOOL_URI,
                        "version": version,
                        "rules": _rule_descriptors(findings),
                    }
                },
                "columnKind": "unicodeCodePoints",
                "results": [_result(finding) for finding in findings],
            }
        ],
    }


def sarif_json(findings: Sequence[Finding], *, version: str) -> str:
    """The SARIF log for *findings* as JSON text."""
    return dumps(sarif_document(findings, version=version))


def _rule_reference(finding: Finding) -> tuple[str, str, Rule | None]:
    """``(ruleId, summary, registry rule)`` for one finding."""
    rule = find_rule(finding.rule)
    if rule is not None and rule.enabled:
        return rule.id, rule.summary, rule
    summary = _SYNTHETIC_RULES.get(finding.rule, finding.message)
    return finding.rule, summary, None


def _rule_descriptors(findings: Sequence[Finding]) -> list[dict[str, object]]:
    descriptors: dict[str, dict[str, object]] = {}
    for finding in findings:
        rule_id, summary, rule = _rule_reference(finding)
        if rule_id in descriptors:
            continue
        descriptor: dict[str, object] = {
            "id": rule_id,
            "name": rule.name if rule is not None else rule_id,
            "shortDescription": {"text": summary},
            "helpUri": _RULE_DOCS_URI if rule is not None else _FINDING_DOCS_URI,
        }
        if rule is not None and rule.details:  # pragma: no cover - no active rule carries details today
            descriptor["fullDescription"] = {"text": rule.details}
        descriptors[rule_id] = descriptor
    return [descriptors[rule_id] for rule_id in sorted(descriptors)]


def _result(finding: Finding) -> dict[str, object]:
    rule_id, _summary, _rule = _rule_reference(finding)
    result: dict[str, object] = {
        "ruleId": rule_id,
        "level": finding.severity,
        "message": {"text": finding.message},
    }
    if finding.hint is not None:
        text = finding.message
        message: dict[str, object] = {
            "text": f"{text}. Help: {finding.hint}",
            "markdown": f"{text}\n\n**help:** {finding.hint}",
        }
        result["message"] = message
    location = _location(finding)
    if location is not None:
        result["locations"] = [location]
    return result


def _artifact_uri(file: str) -> str:
    """A SARIF artifact URI for a finding path.

    A path under the working directory becomes a repository-relative,
    percent-encoded reference, which is what a code-scanning service maps to a
    tracked file. The path is resolved first, so a relative path that points
    outside the working directory becomes an absolute file URI rather than a
    ``../`` reference the service cannot map.
    """
    path = Path(file).resolve()
    try:
        relative = path.relative_to(Path.cwd().resolve())
    except ValueError:
        return path.as_uri()
    return quote(relative.as_posix(), safe="/")


def _location(finding: Finding) -> dict[str, object] | None:
    if finding.file is None:
        return None
    physical: dict[str, object] = {
        "artifactLocation": {"uri": _artifact_uri(finding.file)},
    }
    if finding.line is not None and finding.line >= 1:
        region: dict[str, object] = {"startLine": finding.line}
        if finding.column is not None and finding.column >= 1:
            region["startColumn"] = finding.column
        physical["region"] = region
    return {"physicalLocation": physical}
