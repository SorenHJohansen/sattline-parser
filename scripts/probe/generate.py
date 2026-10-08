# The synthetic .y bodies copy the real graphics format, which uses trailing
# spaces on its data lines; keep them.

"""Generate the real-parser probe tree under ``probes/``.

Every probe expands to program/library *units*. A unit is a triple in its own
subfolder — ``<unit>.s`` source, ``<unit>.y`` graphics, ``<unit>.z`` dependency
list — because the real tool refuses to parse a program or library unless its
three files are present (verified against a reference library tree, where
``.x``+``.y``+``.z`` triplets ship side by side; the code extension does not
matter to the tool).

Emitted layout:

  ``probes/rules/<id>/<unit>/<unit>.s|.y|.z``   frontier probes
  ``probes/tier0/<id>.s|.y|.z``                  existing corpus inventory sweep
  ``probes/proj/<unit>/<unit>.s|.y|.z``          cross-module project units
  ``probes/MANIFEST.yaml``                       machine-readable probe list
  ``probes/TRANSCRIPT.md``                       operator worksheet (fill in real results)
  ``probes/QA.md``                               our parser's verdict per unit
  ``probes/README.md``                           GUI operator instructions

The graphics (``.y``) is synthetic — the canonical 200-byte "empty" body taken
from reference units (only the date differs) — and its first-line date is copied
from the unit's code by default, so date-parity violations (C-201) shift it and
composite-count violations (C-202) add an object row. The ``.z`` is a minimal
dependency list per unit.

Every ``probes/rules/`` and ``probes/proj/`` unit must parse with our own
parser — failure there is a generator bug and aborts the run. Tier-0 copies of
the corpus are intentionally not gated (``Malformed.s`` and friends are
parser-reject fixtures). Idempotent: writes/overwrites files, never deletes.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from lark import Lark

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules import _HEADER, CORPUS, PROBES, Probe, ProbeFile, _picture

from sattline_parser.api import create_parser, parse_and_validate

PROBES_DIR = Path(__file__).resolve().parents[2] / "probes"
RULES_DIR = PROBES_DIR / "rules"
TIER0_DIR = PROBES_DIR / "tier0"
PROJ_DIR = PROBES_DIR / "proj"

_TERRAIN = ("valid", "edge_cases", "invalid")
_HDR_NAME = {"valid": "t0-valid", "edge_cases": "t0-edge", "invalid": "t0-invalid"}
_EXPECTED = {"valid": "accept", "edge_cases": "accept", "invalid": "reject"}

_FALLBACK_DATE = "2000-01-01-00:00:00.000"
_VERSION = "2.23"


class Row(NamedTuple):
    """One TRANSCRIPT.md table row."""

    id: str
    area: str
    tier: int
    file: str
    kind: str
    expected: str
    real: str
    message: str


# ---------------------------------------------------------------------------
# Graphics (.y) and dependency-list (.z) generation.
# ---------------------------------------------------------------------------

# The canonical empty graphics body observed in reference units (200 bytes, only
# the date varies). Synthesised, not copied from any specific file.
_Y_EMPTY = """\

 5
 None  True   4.00000E-002 5.80000E-001
  2.00000E-001 7.00000E-001
 0
 2
 None 0  Lit 0 2 -1     0
 0 +Info
 None  True
f
           0
"""

_Y_EXTRA_OBJECT = """\

 5
 None  True   4.00000E-002 5.80000E-001
  2.00000E-001 7.00000E-001
 0
 3
 None 0  Lit 0 2 -1     0
 None 0  Lit 5 2 -1     0
 0 +Info
 None  True
f
           0
"""


def _date_of(code: str) -> str:
    m = re.search(r"date:\s*(\d{4}-\d{2}-\d{2}-\d{2}:\d{2}:\d{2}\.\d+)", code)
    return m.group(1) if m else _FALLBACK_DATE


def _shift_date(value: str) -> str:
    dt = datetime.strptime(value, "%Y-%m-%d-%H:%M:%S.%f") + timedelta(days=1)
    return dt.strftime("%Y-%m-%d-%H:%M:%S.%f")[:-3]


def _graphics(code: str, variant: str) -> str:
    date = _shift_date(_date_of(code)) if variant == "shift-date" else _date_of(code)
    body = _Y_EXTRA_OBJECT if variant == "extra-object" else _Y_EMPTY
    return f'" Syntax version {_VERSION}, date: {date} N "\n' + body


def _z_text(libs: tuple[str, ...]) -> str:
    return "\n".join(libs) + "\n"


def _prepend_comment(text: str, marker: str) -> str:
    """Merge the probe marker into the file's first header comment, or add one.

    The grammar allows exactly one comment token in the header region, so a
    fresh ``(* ... *)`` is only added when the base has no header comment at
    all (the inline templates). The header comment always starts on line 4 in
    the corpus; searching only the first four lines keeps module bodies'
    ``ENDDEF (*Name*)`` comments untouched.
    """
    start = "\n".join(text.splitlines()[:4]).find("(*")
    if start != -1:
        end = text.find("*)", start)
        if end != -1:
            original = text[start + 2 : end]
            return text[: start + 2] + "\n" + marker + original + text[end:]
    lines = text.splitlines()
    lines.insert(3, f"(* {marker} *)")
    return "\n".join(lines) + "\n"


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _emit(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _probe_comment(probe: Probe) -> str:
    return f"probe {probe.id}: {probe.summary}"


def _probe_text(probe: Probe, f: ProbeFile) -> str:
    return f.mutate(probe.base_path.read_text()) if probe.base else f.mutate("")


def _probe_qa(parser: Lark, text: str, rel: Path) -> str:
    """QA line for one probe unit: parse status plus our own validation codes."""
    try:
        _pic, diags = parse_and_validate(text, parser=parser, log_failures=False)
    except Exception as exc:  # noqa: BLE001 - reported as QA, then handled by caller
        return f"{rel}: PARSE FAIL: {exc}"
    codes = ", ".join(d.code.value for d in diags) if diags else "clean"
    return f"{rel}: parse ok, validation: {codes}"


def _emit_unit(root: Path, rel_dir: Path, name: str, code: str, y_variant: str, z_libs: tuple[str, ...]) -> None:
    """Write a program/library unit triple into ``root/rel_dir/<name>/``."""
    folder = root / rel_dir / name
    _emit(folder / f"{name}.s", code)
    _emit(folder / f"{name}.y", _graphics(code, y_variant))
    _emit(folder / f"{name}.z", _z_text(z_libs))


# ---------------------------------------------------------------------------
# Frontier rule probes.
# ---------------------------------------------------------------------------


def _write_rule_files(parser: Lark) -> tuple[list[str], list[Row], list[str], list[str]]:
    manifest: list[str] = []
    transcript: list[Row] = []
    qa: list[str] = []
    errors: list[str] = []
    for probe in PROBES:
        manifest.append(f'- id: "{probe.id}"')
        manifest.append(f"  tier: {probe.tier}")
        manifest.append(f'  area: "{probe.area}"')
        manifest.append(f'  summary: "{probe.summary}"')
        manifest.append(f'  base: "{probe.base if probe.base else "(inline template)"}"')
        if probe.note:
            manifest.append(f'  note: "{probe.note}"')
        manifest.append("  files:")
        for f in probe.files:
            code = _prepend_comment(_probe_text(probe, f), _probe_comment(probe))
            _emit_unit(PROBES_DIR, Path("rules") / probe.id, f.name[:-2], code, f.y, f.z)
            rel = Path("rules") / probe.id / (f.name[:-2] + ".s")
            manifest.append(f'    - name: "{f.name}"')
            manifest.append(f'      kind: "{f.kind}"')
            manifest.append(f'      expected: "{f.expected}"')
            manifest.append(f'      y: "{f.y}"')
            transcript.append(Row(probe.id, probe.area, probe.tier, str(rel), f.kind, f.expected, "", ""))
            line = _probe_qa(parser, code, Path("rules") / probe.id / f.name[:-2] / f.name)
            if line.startswith("PARSE FAIL"):
                errors.append(line)
            else:
                qa.append(line)
                if f.kind == "control" and "parse ok, validation: clean" not in line:
                    print(f"NOTE: control {rel} hits our own validation: {line.rsplit(':', 1)[1].strip()}")
    return manifest, transcript, qa, errors


# ---------------------------------------------------------------------------
# Tier-0 corpus sweep.
# ---------------------------------------------------------------------------


def _tier0_files() -> list[tuple[str, str, str, str]]:
    """Yield (id, src_rel, text, expected) for every corpus ``.s`` file."""
    out: list[tuple[str, str, str, str]] = []
    for terrain in _TERRAIN:
        src_dir = CORPUS / terrain
        for src in sorted(src_dir.glob("*.s")):
            stem = src.stem
            ident = f"{_HDR_NAME[terrain]}-{stem}"
            out.append((ident, f"{terrain}/{stem}.s", _read_text(src), _EXPECTED[terrain]))
    return out


def _write_tier0(parser: Lark) -> tuple[list[str], list[Row], list[str]]:
    manifest: list[str] = []
    transcript: list[Row] = []
    qa: list[str] = []
    for ident, src_rel, text, expected in _tier0_files():
        code = _prepend_comment(text, f"tier 0 sweep: {src_rel}")
        _emit_unit(PROBES_DIR, Path("tier0"), ident, code, "default", ("StdLib",))
        rel = Path("tier0") / f"{ident}.s"
        manifest.append(f'- id: "{ident}"')
        manifest.append(f'  src: "{src_rel}"')
        manifest.append(f'  expected: "{expected}"')
        transcript.append(Row(ident, "tier0-sweep", 0, str(rel), "inventory", expected, "", ""))
        qa.append(_probe_qa(parser, code, rel))
    return manifest, transcript, qa


# ---------------------------------------------------------------------------
# Cross-module project (probes/proj/).
# ---------------------------------------------------------------------------

_PROJ_TOP_LOCALVARS = "   TopVar: integer  := 0;\n"


def _modtype(name: str, datacode: int, children: tuple[tuple[str, int], ...], eq_var: str) -> str:
    defs = [
        f"   {name} = MODULEDEFINITION DateCode_ {datacode}\n",
        "   LOCALVARIABLES\n",
        f"      {eq_var}: integer  := 0;\n",
    ]
    if children:
        defs.append("   SUBMODULES\n")
        for child, child_code in children:
            defs.append(
                f"      {child} Invocation\n"
                f"         ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5\n"
                f"          ) : MODULEDEFINITION DateCode_ {child_code};\n"
            )
    defs.append("   ModuleDef\n")
    defs.append("   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n")
    defs.append("   ModuleCode\n")
    defs.append(f"   EQUATIONBLOCK {name}Eq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n")
    defs.append(f"      {eq_var} = {eq_var} + 1;\n")
    defs.append(f"   ENDDEF (*{name}*);\n")
    return "".join(defs)


def _project_payload() -> list[tuple[str, str, str, str, tuple[str, ...], str]]:
    """(unit, kind, expected, area_id, z_libs, code) for every project unit."""
    pump = _modtype("PumpType", 220100, (), "PumpVar")
    aux = _modtype("AuxType", 230100, (("PumpInst", 220100),), "AuxVar")
    unused = _modtype("UnusedType", 240100, (), "UVar")
    loop_a = _modtype("LoopAType", 210100, (("BInst", 210200),), "AVar")
    loop_b = _modtype("LoopBType", 210200, (("AInst", 210100),), "BVar")

    def program(name: str, pic_code: int, instance: tuple[str, int] | None) -> str:
        mods = ""
        if instance:
            mods = (
                f"   {instance[0]} Invocation\n"
                f"      ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
                f"       ) : MODULEDEFINITION DateCode_ {instance[1]}\n"
                "\n"
            )
        return (
            _HEADER.format(name=name)
            + "\n"
            + "BasePicture Invocation\n"
            + "   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0\n"
            + f"    ) : MODULEDEFINITION DateCode_ {pic_code}\n"
            + "\n"
            + "LOCALVARIABLES\n"
            + _PROJ_TOP_LOCALVARS
            + "\n"
            + mods
            + "ModuleDef\n"
            + "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            + "\n"
            + "ENDDEF (*BasePicture*);\n"
        )

    units = [
        ("PumpLib", "library", "accept", ("StdLib",), _picture("PumpLib", pump, _PROJ_TOP_LOCALVARS)),
        ("AuxLib", "library", "accept", ("StdLib", "PumpLib"), _picture("AuxLib", aux, _PROJ_TOP_LOCALVARS)),
        ("UnusedLib", "library", "accept", ("StdLib",), _picture("UnusedLib", unused, _PROJ_TOP_LOCALVARS)),
        ("LoopA", "library", "accept", ("StdLib", "LoopB"), _picture("LoopA", loop_a, _PROJ_TOP_LOCALVARS)),
        ("LoopB", "library", "accept", ("StdLib", "LoopA"), _picture("LoopB", loop_b, _PROJ_TOP_LOCALVARS)),
        ("Prog", "program", "reject", ("StdLib", "LoopA"), program("Prog", 901001, ("LoopAInst", 210100))),
        (
            "ProgBadDep",
            "program",
            "reject",
            ("StdLib", "AuxLib"),
            program("ProgBadDep", 901002, ("PumpInst", 220100)),
        ),
    ]
    return [(u, k, e, f"PRJ-{u}", z, _prepend_comment(c, f"project unit {u}")) for u, k, e, z, c in units]


_PROJECT_README = """\
# Cross-module project units (probes/proj/)

A miniature controller program + library closure, the real SattLine equivalent
of a project. Check this directory together with `rules/` and `tier0/` in the
same GUI session.

- `PumpLib`      defines `PumpType` (leaf moduletype).
- `AuxLib`       defines `AuxType` which instantiates `PumpType` (cross-lib).
- `UnusedLib`    defines `UnusedType`, never instantiated anywhere.
- `LoopA`/`LoopB`  each instantiate the other's moduletype AND list each other
  in their `.z` — a moduletype cycle plus a library-dependency cycle.
- `Prog`         program whose closure pulls in the LoopA/LoopB cycle.
- `ProgBadDep`   program referencing `PumpType` while its `.z` omits `PumpLib`
  (undeclared dependency used).

Expected: the individual libraries are valid (`accept`); `Prog` and
`ProgBadDep` should be `reject` if the real parser walks the dependency
closure. Record the actual outcomes in TRANSCRIPT.md.
"""


def _write_project(parser: Lark) -> tuple[list[str], list[Row], list[str], list[str]]:
    manifest: list[str] = []
    transcript: list[Row] = []
    qa: list[str] = []
    errors: list[str] = []
    for unit, kind, expected, ident, z_libs, code in _project_payload():
        _emit_unit(PROBES_DIR, Path("proj"), unit, code, "default", z_libs)
        rel = Path("proj") / unit / f"{unit}.s"
        manifest.append(f'- id: "{ident}"')
        manifest.append(f'  unit: "{unit}"')
        manifest.append(f'  kind: "{kind}"')
        manifest.append(f'  expected: "{expected}"')
        transcript.append(Row(ident, "cross-module", 3, str(rel), kind, expected, "", ""))
        line = _probe_qa(parser, code, rel)
        if line.startswith("PARSE FAIL"):
            errors.append(f"PROJECT PARSE FAIL {rel}: {line}")
        else:
            qa.append(line)
    _emit(PROJ_DIR / "README.md", _PROJECT_README)
    return manifest, transcript, qa, errors


# ---------------------------------------------------------------------------
# Documents.
# ---------------------------------------------------------------------------


def _write_docs(
    manifest: list[str],
    tier0_manifest: list[str],
    project_manifest: list[str],
    transcript_rows: list[Row],
    qa: list[str],
) -> None:
    header = [
        "version: 1",
        "generated: 2026-09-28",
        'expected: "accept | reject | unknown (real parser decides)"',
        "probes:",
    ]
    body = [*manifest, "tier0:", *tier0_manifest, "project:", *project_manifest]
    _emit(PROBES_DIR / "MANIFEST.yaml", "\n".join([*header, *body]) + "\n")
    tb = [
        "# SattLine real-parser probe transcript",
        "#",
        "# A unit is a program/library triple: `file` is the .s; its .y and .z",
        "# siblings travel with it. Fill `real status` with Accept or Reject per",
        "# unit, and paste the exact message text (or message id) into `message`.",
        "# This file is the input to analyze.py.",
        "#",
        "| id | area | tier | file | kind | expected | real status | message |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in transcript_rows:
        tb.append("| " + " | ".join(str(c) for c in row) + " |")
    _emit(PROBES_DIR / "TRANSCRIPT.md", "\n".join(tb) + "\n")
    _emit(PROBES_DIR / "QA.md", "\n".join(qa) + "\n")
    _emit(
        PROBES_DIR / "README.md",
        "\n".join(
            [
                "# Real-parser probe tree",
                "",
                "Every entry is a **program/library unit**: a `<name>.s` code file",
                "with a `<name>.y` graphics file and a `<name>.z` dependency list",
                "shipped in the same folder. The real tool needs all three before it",
                "will parse a unit.",
                "",
                "Point the real SattLine GUI's check at this whole `probes/`",
                "directory (it supports batch checking of multiple files in one",
                "run). Then fill `TRANSCRIPT.md`: one row per unit — `real status`",
                "is Accept or Reject; `message` is the verbatim diagnostic text or",
                "message id the GUI shows. Save the filled file and hand it back;",
                "`analyze.py` converts it into the committed snapshot.",
                "",
                "- `tier0/`  — existing corpus inventory sweep (accept/reject baseline).",
                "  `t0-invalid-*` files (Malformed/NotSattLine/EncodingStress) are",
                "  expected rejects.",
                "- `rules/`  — the new frontier probes; `expected` is a hypothesis,",
                "  the real parser decides. C-201/C-202 differ only in the `.y`.",
                "- `proj/`   — a miniature program + library closure.",
            ]
        )
        + "\n",
    )
    n = sum(len(p.files) for p in PROBES)
    print(f"wrote {RULES_DIR.name}: {n} rule units across {len(PROBES)} probes")
    print(f"wrote {TIER0_DIR.name}: {len(list(TIER0_DIR.glob('*/*.s')))} corpus triples")
    print(f"wrote {PROJ_DIR.name}: {len(_project_payload())} project units")


def main() -> None:
    parser = create_parser()
    manifest, transcript, qa, errors = _write_rule_files(parser)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    tier0_manifest, tier0_rows, tier0_qa = _write_tier0(parser)
    project_manifest, project_rows, project_qa, project_errors = _write_project(parser)
    errors = [*errors, *project_errors]
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    _write_docs(
        manifest,
        tier0_manifest,
        project_manifest,
        transcript + tier0_rows + project_rows,
        qa + tier0_qa + project_qa,
    )


if __name__ == "__main__":
    main()
