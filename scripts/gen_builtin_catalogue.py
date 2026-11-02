"""Regenerate ``src/sattline_parser/builtins/catalogue.json``.

The catalogue is a transcription of the public SattLine builtin function
documentation. The source table lives in ``builtin_catalogue_source.json``
next to this script; this script validates it, adds the provenance header, and
writes the shipped catalogue. It is the only writer of
``builtins/catalogue.json``.

Provenance
----------

The signatures are transcribed from the following public manuals:

* SattLine Language User manual, System Version 3.1, chapter 2
  "System procedures and functions" (sections 2.6-2.35).
* SattLine I/O and Communication User manual, System Version 3.1.
* SattLine General and Graphics User manual, System Version 3.1.
* SattLine 3.1 Additional features, System Version 3.1-2.

The generated header records the documented total, the sources cited, and the
reason for every name the catalogue does not document. Two buckets sit beside
the documented set:

* ``not_located``: names the source table carries but no public manual in the
  reference set documents.
* ``internal``: registrations the system exposes to compiled programs but does
  not publish as language built-ins. They are carried so calls in existing
  sources keep their arity and argument constraints.

Neither bucket is part of ``documented_total``.

Usage::

    python scripts/gen_builtin_catalogue.py          # write the catalogue
    python scripts/gen_builtin_catalogue.py --check  # fail if out of date
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final, cast

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SOURCE_PATH: Final[Path] = _ROOT / "scripts" / "builtin_catalogue_source.json"
_OUT_PATH: Final[Path] = _ROOT / "src" / "sattline_parser" / "builtins" / "catalogue.json"

_DIRECTIONS: Final[frozenset[str]] = frozenset({"in", "in var", "out", "inout"})
_SORTING: Final[frozenset[str]] = frozenset({"RS", "WS", "RS/WS", "NoS"})
_OWNERSHIP: Final[frozenset[str]] = frozenset({"RO", "WO", "RO/WO", "NoO"})
_KINDS: Final[frozenset[str]] = frozenset({"function", "procedure"})


def _require(condition: object, message: str) -> None:
    if not condition:
        raise SystemExit(f"invalid builtin catalogue source: {message}")


def _validate_parameter(name: str, parameter: object) -> dict[str, object]:
    _require(isinstance(parameter, dict), f"{name}: parameter is not an object")
    entry = cast("dict[str, object]", parameter)
    for key in ("name", "datatype", "direction", "sorting", "ownership"):
        _require(isinstance(entry.get(key), str) and entry[key], f"{name}: parameter is missing {key}")
    _require(entry["direction"] in _DIRECTIONS, f"{name}: unknown direction {entry['direction']!r}")
    _require(entry["sorting"] in _SORTING, f"{name}: unknown sorting {entry['sorting']!r}")
    _require(entry["ownership"] in _OWNERSHIP, f"{name}: unknown ownership {entry['ownership']!r}")
    optional = entry.get("optional", False)
    _require(isinstance(optional, bool), f"{name}: parameter optional must be a boolean")
    validated: dict[str, object] = {
        "name": entry["name"],
        "datatype": entry["datatype"],
        "direction": entry["direction"],
        "sorting": entry["sorting"],
        "ownership": entry["ownership"],
    }
    if optional:
        validated["optional"] = True
    return validated


def _validate_function(name: str, raw: object) -> dict[str, object]:
    _require(isinstance(raw, dict), f"{name}: entry is not an object")
    entry = cast("dict[str, object]", raw)
    kind = entry.get("kind")
    _require(kind in _KINDS, f"{name}: unknown kind {kind!r}")
    typed = entry.get("typed")
    _require(isinstance(typed, bool), f"{name}: typed must be a boolean")
    return_type = entry.get("return_type")
    _require(return_type is None or isinstance(return_type, str), f"{name}: return_type must be a string or null")
    precision_scangroup = entry.get("precision_scangroup")
    _require(isinstance(precision_scangroup, bool), f"{name}: precision_scangroup must be a boolean")
    parameters = entry.get("parameters")
    _require(isinstance(parameters, list), f"{name}: parameters must be a list")
    raw_parameters = cast("list[object]", parameters)
    validated_parameters = [_validate_parameter(name, parameter) for parameter in raw_parameters]
    optional_seen = False
    for parameter in validated_parameters:
        if parameter.get("optional") is True:
            optional_seen = True
        elif optional_seen:
            _require(False, f"{name}: required parameter {parameter['name']!r} follows an optional parameter")
    return {
        "kind": kind,
        "return_type": return_type,
        "precision_scangroup": precision_scangroup,
        "typed": typed,
        "parameters": validated_parameters,
    }


def build(source: dict[str, object]) -> dict[str, object]:
    """Build the shipped catalogue document from a validated source table."""
    primary_source = source.get("primary_source")
    _require(isinstance(primary_source, dict), "primary_source is missing")
    additional_sources = source.get("additional_sources", [])
    _require(isinstance(additional_sources, list), "additional_sources must be a list")
    not_located = source.get("not_located", [])
    _require(isinstance(not_located, list), "not_located must be a list")
    internal = source.get("internal", [])
    _require(isinstance(internal, list), "internal must be a list")
    aliases = source.get("aliases", {})
    _require(isinstance(aliases, dict), "aliases must be an object")
    functions = source.get("functions")
    _require(isinstance(functions, dict), "functions must be an object")

    function_table = cast("dict[str, object]", functions)
    catalogue_functions: dict[str, object] = {}
    for name in sorted(function_table):
        _require(name == name.casefold(), f"{name}: catalogue keys must be casefolded")
        catalogue_functions[name] = _validate_function(name, function_table[name])

    not_located_names = sorted(cast("list[str]", not_located))
    for name in not_located_names:
        _require(name in catalogue_functions, f"{name}: listed as not_located but absent from functions")

    internal_names = sorted(cast("list[str]", internal))
    for name in internal_names:
        _require(name == name.casefold(), f"{name}: internal names must be casefolded")
        _require(name in catalogue_functions, f"{name}: listed as internal but absent from functions")
        _require(name not in not_located_names, f"{name}: listed as both internal and not_located")

    alias_table = cast("dict[str, str]", aliases)
    for alias, target in alias_table.items():
        _require(target in catalogue_functions, f"{alias}: alias target {target!r} is absent")

    undocumented = len(not_located_names) + len(internal_names)
    documented_total = len(catalogue_functions) - undocumented
    typed_entries = sum(1 for entry in catalogue_functions.values() if cast("dict[str, object]", entry)["typed"])
    untyped_entries = len(catalogue_functions) - typed_entries

    return {
        "meta": {
            "generated_by": "scripts/gen_builtin_catalogue.py",
            "documented_total": documented_total,
            "carried_total": len(catalogue_functions),
            "typed_entries": typed_entries,
            "untyped_entries": untyped_entries,
            "omissions": [],
            "primary_source": primary_source,
            "additional_sources": additional_sources,
            "not_located": {
                "count": len(not_located_names),
                "names": not_located_names,
                "reason": (
                    "Carried from the transcribed table so arity checks keep working for them; "
                    "no public manual in the reference set documents these names."
                ),
            },
            "internal": {
                "count": len(internal_names),
                "names": internal_names,
                "reason": (
                    "Registrations the system binds for compiled programs but does not publish as "
                    "language built-ins. Carried so arity and argument checks keep working for "
                    "sources that call them; they are not part of the documented total."
                ),
            },
            "aliases": alias_table,
        },
        "functions": catalogue_functions,
    }


def _render(document: dict[str, object]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if the committed catalogue is out of date")
    args = parser.parse_args(argv)

    source = cast("dict[str, object]", json.loads(_SOURCE_PATH.read_text(encoding="utf-8")))
    document = build(source)
    rendered = _render(document)

    if args.check:
        current = _OUT_PATH.read_text(encoding="utf-8") if _OUT_PATH.exists() else ""
        if current != rendered:
            print(f"{_OUT_PATH} is out of date; run python scripts/gen_builtin_catalogue.py", file=sys.stderr)
            return 1
        print(f"{_OUT_PATH} is up to date")
        return 0

    _OUT_PATH.write_text(rendered, encoding="utf-8")
    meta = cast("dict[str, object]", document["meta"])
    not_located = cast("dict[str, object]", meta["not_located"])
    print(
        f"wrote {_OUT_PATH} ({meta['carried_total']} entries, "
        f"{meta['documented_total']} documented, {not_located['count']} not located)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
