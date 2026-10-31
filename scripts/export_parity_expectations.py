"""Export a golden validation manifest for the parser corpus.

This is a development helper, not shipped package code. It runs the validator
over every corpus fixture and writes ``tests/fixtures/validation/expectations.json``
with one entry per fixture and one record per diagnostic. The parser's test suite
reads the manifest, so a behaviour change is visible as a diff instead of a
silent pass.

Usage::

    python scripts/export_parity_expectations.py
    python scripts/export_parity_expectations.py --validator sattlint
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from sattline_parser.api import parse_source_file
from sattline_parser.validation import validate_basepicture

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_CORPUS: Final[Path] = _ROOT / "tests" / "fixtures" / "corpus"
_OUT: Final[Path] = _ROOT / "tests" / "fixtures" / "validation" / "expectations.json"


def _diagnostics_parser(path: Path) -> list[dict[str, object]]:
    try:
        bp = parse_source_file(path, log_failures=False)
    except Exception as exc:  # noqa: BLE001 - a parse failure is a manifest entry, not a crash
        return [{"parse_error": str(exc)}]
    records: list[dict[str, object]] = []
    for diagnostic in validate_basepicture(bp):
        span = diagnostic.span
        records.append(
            {
                "code": diagnostic.code.value,
                "severity": diagnostic.severity.value,
                "line": None if span is None else span.line,
                "column": None if span is None else span.column,
                "length": None if span is None else max(span.end - span.start, 0),
            }
        )
    return records


def _diagnostics_sattlint(path: Path) -> list[dict[str, object]]:
    from sattlint.validation import (  # noqa: PLC0415 - optional dev dependency
        StructuralValidationError,
        validate_transformed_basepicture,
    )

    try:
        bp = parse_source_file(path, log_failures=False)
    except Exception as exc:  # noqa: BLE001 - a parse failure is a manifest entry, not a crash
        return [{"parse_error": str(exc)}]
    try:
        validate_transformed_basepicture(bp, allow_unresolved_external_datatypes=True)
    except StructuralValidationError as exc:
        return [
            {
                "code": None,
                "severity": "error",
                "message": str(exc),
                "line": exc.line,
                "column": exc.column,
                "length": exc.length,
            }
        ]
    return []


def build(validator: str) -> dict[str, object]:
    collector = _diagnostics_parser if validator == "parser" else _diagnostics_sattlint
    fixtures: dict[str, object] = {}
    for group in ("invalid", "valid", "edge_cases"):
        directory = _CORPUS / group
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.s")):
            fixtures[f"{group}/{path.name}"] = collector(path)
    return {
        "generated_by": "scripts/export_parity_expectations.py",
        "validator": validator,
        "fixtures": fixtures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--validator", choices=("parser", "sattlint"), default="parser")
    args = parser.parse_args(argv)

    document = build(args.validator)
    fixtures = document["fixtures"]
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    count = len(fixtures) if isinstance(fixtures, dict) else 0
    print(f"wrote {_OUT} ({count} fixtures, validator={args.validator})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
