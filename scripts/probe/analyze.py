"""Convert a filled probe transcript into a classified parity snapshot.

Reads ``probes/TRANSCRIPT.md`` (one row per probe file, filled by a human after
a real-parser GUI session), classifies every file against its expected outcome
using the probe table from PARITY_PLAN.md, and writes a JSON golden record to
``tests/real/reports/<date>[-<gui-version>].json``.

Classification per file:

* ``confirmed``        - real outcome matches the expected one
* ``pending``          - ``real status`` cell not filled yet
* ``crashes-tool``     - the real tool crashes/hangs on the file (terminal
  observation, distinct from accept/reject)
* ``not-enforced``     - violation expected ``reject`` but real accepted it
* ``disputed-reject``  - same as not-enforced on a paired probe (strengthen + re-probe)
* ``disputed-accept``  - file expected ``accept`` but real rejected it
* ``recorded``         - expected ``unknown``; verdict recorded verbatim

Per *paired* probe (control + violation) a verdict is rolled up:

* ``template-broken``  - the control itself was rejected (fix the control file)
* ``rule-confirmed``   - control accepted and the rejection violation rejected
* ``not-enforced``     - control accepted but a rejection violation was accepted
* ``surprise-reject``  - a file the real parser is asserted to accept was rejected
* ``pending``          - not all rows answered

Tier-0 sweep rows (no pairs) get ``survey-mismatch`` / ``survey-surprise``
verdicts instead of a rollup. Rows that contradict an already-implemented rule
land on the reversal watchlist (mapped in ``WATCHLIST`` below).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TextIO, cast

REPORTS_DIR = Path("tests/real/reports")

ACCEPT_WORDS = frozenset({"accept", "ok", "valid", "pass", "passes", "true", "yes", "y"})
REJECT_WORDS = frozenset({"reject", "invalid", "bad", "fail", "failed", "error", "false", "no", "n"})

# A crash / hang is a *terminal* observation, distinct from accept or reject: the
# tool dies on the file instead of reporting a diagnostic. It must not degrade
# into ``pending``, which would silently hide a known, reproducible result.
CRASH_WORDS = frozenset(
    {
        "crash",
        "crashed",
        "crashes",
        "hang",
        "hangs",
        "stall",
        "stalls",
        "unresponsive",
        "frozen",
        "freezes",
        "fatal",
        "aborts",
        "aborted",
        "terminates",
    }
)

# Probe id -> implemented rule this probe can contradict (PARITY_PLAN.md s6.4),
# plus whether our current implementation accepts the probed construct.
WATCHLIST: dict[str, tuple[str, bool]] = {
    "R-101": ("SL-V022", False),  # we reject unlimited SEQINITSTEPs
    "R-102": ("SL-V022", False),  # we reject init-after-step placement
    "T1-006": ("SL-V020", False),  # we reject AnyType anywhere
    "T1-006b": ("SL-V020", False),  # we reject AnyType as record field
    "T1-011": ("SFC accessor exemption", True),  # we accept dotted accessors
    "t0-invalid-BadDurationLiteral": ("SL-V011", False),  # we reject 'not-a-duration'
    "t0-invalid-BadTimeLiteral": ("SL-V012", False),  # we reject a bad time literal
    "t0-invalid-InitValueTypeMismatch": ("SL-V008", False),  # we reject str init for integer
    "t0-invalid-SFCInitStepNotFirst": ("SL-V022", False),  # we reject init not first in a sequence
}


# Free-text markers a human writes in the message cell to record what *our*
# parser did with the same file. Kept in the transcript rather than a second
# machine column so the ledger stays the single place a human edits.
OURS_REJECT_MARKERS = ("ours rejects", "ours parse-rejects", "we reject", "we also reject", "matched")
OURS_ACCEPT_MARKERS = ("ours accepts", "we accept", "we never", "known gap", "is skipped")


@dataclass(frozen=True)
class Row:
    probe_id: str
    area: str
    tier: int
    file: str
    kind: str
    expected: str
    real: str
    message: str


def _is_crash(value: str) -> bool:
    folded = value.casefold().strip()
    return bool(folded) and (folded in CRASH_WORDS or "crash" in folded or "hang" in folded)


def _parse_bool(value: str) -> bool | None:
    folded = value.casefold().strip()
    if not folded:
        return None
    if folded in ACCEPT_WORDS:
        return True
    if folded in REJECT_WORDS:
        return False
    if "reject" in folded or "fail" in folded or "error" in folded or "invalid" in folded:
        return False
    if "accept" in folded or "valid" in folded or "pass" in folded or "ok" in folded:
        return True
    return None


def parse_transcript(path: Path) -> list[Row]:
    rows: list[Row] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped.replace("|", "").replace("-", "").strip()) == set():
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 8 or cells[0] == "id":
            continue
        probe_id, area, tier, file_, kind, expected, real, message = cells
        rows.append(
            Row(
                probe_id=probe_id,
                area=area,
                tier=int(tier) if tier.isdigit() else 0,
                file=file_,
                kind=kind,
                expected=expected,
                real=real,
                message=message,
            )
        )
    return rows


def _classify(expected: str, real: bool | None, crashed: bool = False) -> str:
    if crashed:
        return "crashes-tool"
    if real is None:
        return "pending"
    if expected == "unknown":
        return "recorded"
    expected_accept = expected == "accept"
    if real == expected_accept:
        return "confirmed"
    return "disputed-accept" if expected_accept else "not-enforced"


def _survey_verdict(expected: str, real: bool | None, crashed: bool = False) -> str:
    """Single-row verdict for the tier-0 sweep (no control/violation pairing)."""
    if crashed:
        return "crashes-tool"
    if real is None:
        return "pending"
    if real == (expected == "accept"):
        return "confirmed"
    return "survey-mismatch" if expected == "accept" else "survey-surprise"


def _ours(row: Row) -> bool | None:
    """What our own parser did with this file, per the human's message cell.

    ``None`` means the transcript does not say, which is the honest default:
    a missing marker must not be read as agreement.
    """
    text = row.message.lower()
    if any(m in text for m in OURS_REJECT_MARKERS):
        return False
    if any(m in text for m in OURS_ACCEPT_MARKERS):
        return True
    return None


def _gap(row: Row, real: bool | None, crashed: bool) -> str:
    """Classify a tier-0 row by what it means for *our* implementation.

    ``survey-mismatch`` alone conflates two very different situations: a file
    the real tool rejects and we also reject (encoding cases - already correct)
    versus one the real tool rejects and we happily accept (a real grammar gap).
    Only the latter is work to do.
    """
    if crashed or real is None:
        return "n/a"
    ours = _ours(row)
    if ours is None:
        return "unknown"
    if real == ours:
        return "agree" if real == (row.expected == "accept") else "wrong-both"
    return "we-too-lenient" if real is False else "we-too-strict"


def _rollup(file_rows: list[Row]) -> str:
    if any(_is_crash(r.real) for r in file_rows):
        return "crashes-tool"
    # A rejected control is a known, terminal fact about the probe template: report it
    # even while the violation is still unanswered, or the broken control stays hidden.
    if any(r.kind == "control" and _parse_bool(r.real) is False for r in file_rows):
        return "template-broken"
    if not all(r.real.strip() for r in file_rows):
        return "pending"
    parsed = {r.kind: _parse_bool(r.real) for r in file_rows}
    control = parsed.get("control")
    if control is False:
        return "template-broken"
    violations = {r.file: (r, _parse_bool(r.real)) for r in file_rows if r.kind == "violation"}
    if not violations:
        return "confirmed"
    for row, real in violations.values():
        if real is False and row.expected == "reject":
            return "rule-confirmed"
        if real is True and row.expected == "reject":
            return "not-enforced"
        if real is False and row.expected == "accept":
            return "surprise-reject"
        if real is True and row.expected == "accept":
            continue
    return "confirmed"


def _reversal(probe_id: str, file_rows: list[Row]) -> list[dict[str, str]]:
    watch = WATCHLIST.get(probe_id)
    if watch is None:
        return []
    rule, we_accept = watch
    notes: list[dict[str, str]] = []
    for row in file_rows:
        # `we_accept` describes our behavior on the *violation* construct; an accepted
        # control is supposed to be accepted by both sides and is not a contradiction.
        if row.kind == "control":
            continue
        real = _parse_bool(row.real)
        if real is None:
            continue
        contradicted = real is not we_accept
        if contradicted:
            notes.append(
                {"file": row.file, "rule": rule, "detail": f"real={row.real!r}; our parser behavior={we_accept}"}
            )
    return notes


def _summary_counts(probes: list[Mapping[str, object]], tier0: list[Mapping[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in [*probes, *tier0]:
        verdict = str(item["verdict"])
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def _manifest_file_count(path: Path) -> int:
    if not path.exists():
        return -1
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.lstrip().startswith("- name:"))


def _write_json(obj: Mapping[str, object], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _print_summary(counts: dict[str, int], page: TextIO = sys.stdout) -> None:
    print("classification totals:", file=page)
    for verdict in sorted(counts):
        print(f"  {verdict:>18}: {counts[verdict]}", file=page)


def analyze(
    transcript: Path,
    manifest: Path | None,
    out_dir: Path,
    gui_version: str | None,
    write: bool,
    page: TextIO,
) -> int:
    rows = parse_transcript(transcript)
    if not rows:
        print(f"no transcript rows parsed from {transcript}", file=page)
        return 2
    by_probe: dict[str, list[Row]] = {}
    tier0_rows: list[Row] = []
    for row in rows:
        if row.tier == 0 or row.probe_id.startswith("t0-"):
            tier0_rows.append(row)
        else:
            by_probe.setdefault(row.probe_id, []).append(row)
    probes: list[Mapping[str, object]] = [
        {
            "id": pid,
            "area": file_rows[0].area,
            "tier": file_rows[0].tier,
            "verdict": _rollup(file_rows),
            "reversals": _reversal(pid, file_rows),
            "evidence": [vars(r) for r in file_rows],
        }
        for pid, file_rows in sorted(by_probe.items())
    ]
    tier0: list[Mapping[str, object]] = [
        {
            "file": r.file,
            "kind": r.kind,
            "expected": r.expected,
            "real": r.real,
            "message": r.message,
            "verdict": _survey_verdict(r.expected, _parse_bool(r.real), _is_crash(r.real)),
            "gap": _gap(r, _parse_bool(r.real), _is_crash(r.real)),
            "reversals": _reversal(r.probe_id, [r]),
        }
        for r in tier0_rows
    ]
    counts = _summary_counts(probes, tier0)
    reversals = sum(len(cast("list[dict[str, str]]", p["reversals"])) for p in probes) + sum(
        len(cast("list[dict[str, str]]", t["reversals"])) for t in tier0
    )
    manifest_n = _manifest_file_count(manifest) if manifest else -1
    print(
        f"rows: {len(rows)}  probes: {len(probes)}  tier0 files: {len(tier0)}  rule files (manifest): {manifest_n}",
        file=page,
    )
    _print_summary(counts, page)
    gaps: dict[str, int] = {}
    for entry in tier0:
        key = str(entry.get("gap", "n/a"))
        gaps[key] = gaps.get(key, 0) + 1
    print(
        f"tier-0 vs our parser: we-too-lenient {gaps.get('we-too-lenient', 0)}, "
        f"we-too-strict {gaps.get('we-too-strict', 0)}, "
        f"wrong-both {gaps.get('wrong-both', 0)}, "
        f"agree {gaps.get('agree', 0)}, "
        f"unknown {gaps.get('unknown', 0)}",
        file=page,
    )
    filled = sum(1 for r in rows if r.real.strip())
    if filled == 0:
        print("no real statuses filled yet - skipping snapshot write", file=page)
        return 0
    if not write:
        print("write disabled (--no-write); snapshot not written", file=page)
        return 0
    today = str(date.today())
    label = f"{today}-{gui_version}" if gui_version else today
    snapshot: dict[str, object] = {
        "schema": 1,
        "date": today,
        "generated": today,
        "gui_version": gui_version,
        "transcript": str(transcript),
        "summary": {"rev": reversals, **counts},
        "probes": probes,
        "tier0": tier0,
    }
    dest = out_dir / f"{label}.json"
    _write_json(snapshot, dest)
    print(f"wrote {dest}", file=page)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser_obj = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser_obj.add_argument("--transcript", default="probes/TRANSCRIPT.md")
    parser_obj.add_argument("--manifest", default="probes/MANIFEST.yaml")
    parser_obj.add_argument("--out-dir", default=str(REPORTS_DIR))
    parser_obj.add_argument("--gui-version", default=None, help="override/report the GUI version string")
    parser_obj.add_argument("--no-write", action="store_true", help="classify and print only")
    args = parser_obj.parse_args(argv)
    return analyze(
        transcript=Path(args.transcript),
        manifest=Path(args.manifest),
        out_dir=Path(args.out_dir),
        gui_version=args.gui_version,
        write=not args.no_write,
        page=sys.stdout,
    )


if __name__ == "__main__":
    sys.exit(main())
