"""Regenerate ``validation/builtin_catalogue.json`` from a native export.

Usage::

    python scripts/gen_builtin_catalogue.py path/to/builtin_signatures.json

The export is the 504-registration table extracted from the workstation build
(``builtin_signatures.json``, SHA-256 ``<pinned in validation/builtins.py>``).
Each registration keeps only what the validator needs: the call arity and the
1-based positions whose descriptor mode is write-like, derived with the
recovered mode mapping (``00711af0``: subtract 100 while >100, then 50 while
>50; ``1,2,22→0x01; 4,24→0x02; 6,26→0x03; 8,28→0x08; 9,29→0x04; 10,30→0x0C;
11,31→0x10``; a write-like parameter has mask bit 0x02 or 0x08).

Registrations without parameters are skipped: a signature with no argument
information would only produce false arity errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_OUT = Path(__file__).resolve().parents[1] / "src" / "sattline_parser" / "validation" / "builtin_catalogue.json"

_MASKS = {
    1: 0x01,
    2: 0x01,
    22: 0x01,
    4: 0x02,
    24: 0x02,
    6: 0x03,
    26: 0x03,
    8: 0x08,
    28: 0x08,
    9: 0x04,
    29: 0x04,
    10: 0x0C,
    30: 0x0C,
    11: 0x10,
    31: 0x10,
}


def step_mask(mode: int) -> int:
    """Map a descriptor mode enum to its dependency mask."""
    reduced = mode
    if reduced > 100:
        reduced -= 100
    if reduced > 50:
        reduced -= 50
    return _MASKS.get(reduced, 0)


def build(registrations: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    catalogue: dict[str, dict[str, object]] = {}
    for entry in registrations:
        name = entry.get("name")
        kind = entry.get("kind")
        parameters = entry.get("parameters") or []
        if not isinstance(name, str) or not isinstance(kind, str) or not isinstance(parameters, list):
            continue
        if not parameters:
            continue
        writes = [
            index
            for index, parameter in enumerate(parameters, start=1)
            if isinstance(parameter, dict) and step_mask(int(parameter.get("mode_code", 0))) & 0x0A
        ]
        catalogue[name] = {"kind": kind, "args": len(parameters), "write": writes}
    return dict(sorted(catalogue.items()))


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv)[1:]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    source = Path(args[0])
    registrations = json.loads(source.read_text(encoding="utf-8"))
    catalogue = build(registrations)
    _OUT.write_text(json.dumps(catalogue, indent=0) + "\n", encoding="utf-8")
    print(f"wrote {_OUT} ({len(catalogue)} entries from {source.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
