"""Tests for the probe-transcript analyzer (``scripts/probe/analyze.py``).

The analyzer is a shipped CLI, so its classification rules are contract, not
incidental. These tests pin the decisions that are easy to get subtly wrong:
crash vocabulary must never degrade into ``pending``, a rejected control must
not hide behind an unanswered violation, and a tier-0 mismatch must be split
into "we also reject" versus "a real grammar gap".
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "probe" / "analyze.py"

HEADER = "| id | area | tier | file | kind | expected | real | message |\n"


def _load_analyzer() -> Any:
    """Import the CLI script by path (it is not an installed package)."""
    spec = importlib.util.spec_from_file_location("probe_analyze", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


A = _load_analyzer()


def _row(
    pid: str,
    file_: str,
    kind: str,
    expected: str,
    real: str,
    message: str = "",
    area: str = "a",
    tier: str = "0",
) -> str:
    return f"| {pid} | {area} | {tier} | {file_} | {kind} | {expected} | {real} | {message} |\n"


def _write(tmp_path: Path, *rows: str) -> Path:
    p = tmp_path / "TRANSCRIPT.md"
    p.write_text(HEADER + "".join(rows), encoding="utf-8")
    return p


def _t0(message: str, real: str = "reject", expected: str = "accept") -> Any:
    return A.Row("t0-x", "a", 0, "f.x", "inventory", expected, real, message)


def _paired(control: str, violation: str) -> list[Any]:
    return [
        A.Row("C-x", "a", 3, "Ctrl.x", "control", "accept", control, ""),
        A.Row("C-x", "a", 3, "Viol.x", "violation", "reject", violation, ""),
    ]


def _analyze(**kwargs: Any) -> int:
    opts: dict[str, Any] = {
        "transcript": None,
        "manifest": None,
        "out_dir": None,
        "gui_version": None,
        "write": False,
    }
    opts.update(kwargs)
    page = io.StringIO()
    rc = A.analyze(**opts, page=page)
    A.LAST_OUTPUT = page.getvalue()
    return rc


# --- status vocabulary -------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["crash", "crashed", "hang", "stall", "stalls", "unresponsive", "terminates"],
)
def test_crash_words_are_terminal_not_pending(value: str) -> None:
    assert A._is_crash(value) is True
    assert A._survey_verdict("accept", A._parse_bool(value), True) == "crashes-tool"


def test_crash_never_degrades_to_pending() -> None:
    assert A._parse_bool("crash") is None
    assert A._classify("accept", None, crashed=True) == "crashes-tool"


def test_empty_real_cell_is_pending_not_crash() -> None:
    assert A._is_crash("") is False
    assert A._classify("accept", None) == "pending"


def test_expected_unknown_records_verbatim() -> None:
    assert A._classify("unknown", True) == "recorded"


def test_prose_in_a_status_cell_still_resolves() -> None:
    assert A._parse_bool("rejected - AliasSym Expected") is False
    assert A._parse_bool("loads cleanly") is None


def test_dash_placeholder_is_pending_not_a_result() -> None:
    assert A._parse_bool("---") is None
    assert A._is_crash("---") is False


# --- single-file classification ---------------------------------------------


@pytest.mark.parametrize(
    ("expected", "real", "want"),
    [
        ("accept", True, "confirmed"),
        ("accept", False, "disputed-accept"),
        ("reject", False, "confirmed"),
        ("reject", True, "not-enforced"),
    ],
)
def test_classify(expected: str, real: bool, want: str) -> None:
    assert A._classify(expected, real) == want


def test_survey_uses_mismatch_and_surprise_not_disputed() -> None:
    assert A._survey_verdict("accept", False) == "survey-mismatch"
    assert A._survey_verdict("reject", True) == "survey-surprise"


# --- tier-0 gap split -------------------------------------------------------


def test_gap_splits_shared_reject_from_real_gap() -> None:
    both_reject = _t0("ours rejects too (lexer stops on the high byte)")
    only_real = _t0("ours accepts")
    assert A._gap(both_reject, False, False) == "wrong-both"
    assert A._gap(only_real, False, False) == "we-too-lenient"


def test_gap_detects_we_too_strict() -> None:
    assert A._gap(_t0("ours rejects with SL-V011", real="accept"), True, False) == "we-too-strict"


def test_gap_agree_when_both_accept_an_expected_accept() -> None:
    assert A._gap(_t0("ours accepts"), True, False) == "agree"


def test_gap_unknown_without_marker_is_not_assumed_agreement() -> None:
    assert A._gap(_t0("Error 76"), False, False) == "unknown"
    assert A._ours(_t0("Error 76")) is None


def test_gap_is_na_for_pending_and_crash() -> None:
    assert A._gap(_t0("", real=""), None, False) == "n/a"
    assert A._gap(_t0("crash", real="crash"), None, True) == "n/a"


# --- transcript parsing ------------------------------------------------------


def test_parse_transcript_skips_separator_and_header(tmp_path: Path) -> None:
    p = _write(tmp_path, _row("t0-a", "A.x", "inventory", "accept", "accept"))
    with p.open("a", encoding="utf-8") as fh:
        fh.write("|---|---|---|---|---|---|---|---|\n")
    assert [r.file for r in A.parse_transcript(p)] == ["A.x"]


def test_parse_transcript_keeps_eight_cell_rows_only(tmp_path: Path) -> None:
    p = _write(tmp_path, _row("t0-a", "A.x", "inventory", "accept", "accept"), "| too | few |\n")
    assert len(A.parse_transcript(p)) == 1


def test_tier0_and_paired_rows_coexist(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        _row("t0-a", "A.x", "inventory", "accept", "accept"),
        _row("C-104", "Ctrl.x", "control", "accept", "accept", area="m", tier="3"),
        _row("C-104", "Viol.x", "violation", "reject", "reject", area="m", tier="3"),
    )
    assert _analyze(transcript=p) == 0
    assert len(A.parse_transcript(p)) == 3


# --- rollup precedence -------------------------------------------------------


def test_rejected_control_is_template_broken_even_with_pending_violation() -> None:
    assert A._rollup(_paired("reject", "")) == "template-broken"


def test_accepted_control_with_pending_violation_is_pending() -> None:
    assert A._rollup(_paired("accept", "")) == "pending"


def test_control_ok_violation_rejected_is_rule_confirmed() -> None:
    assert A._rollup(_paired("accept", "reject")) == "rule-confirmed"


def test_control_ok_violation_accepted_is_not_enforced() -> None:
    assert A._rollup(_paired("accept", "accept")) == "not-enforced"


def test_accepted_control_is_not_counted_as_a_reversal() -> None:
    assert A._reversal("C-104", _paired("accept", "reject")) == []


def test_reversed_watchlisted_violation_names_the_implemented_rule() -> None:
    """Real accepts a construct we reject -> a genuine reversal to report."""
    rows = [A.Row("R-101", "sfc", 1, "V.x", "violation", "accept", "accept", "")]
    out = A._reversal("R-101", rows)
    assert out and out[0]["rule"] == "SL-V022"
    assert "we reject" not in out[0]["detail"]


def test_r101_is_no_longer_a_reversal() -> None:
    """Guards the 2026-10-01 finding: a 2nd SEQINITSTEP is rejected by both.

    The watchlist entry stays so a future regression re-opens the question, but
    with the real tool agreeing with SL-V022 there is nothing to report.
    """
    rows = [A.Row("R-101", "sfc", 1, "ViolSecInit.x", "violation", "accept", "reject", "")]
    assert A._reversal("R-101", rows) == []


def test_unwatchlisted_probe_never_reports_a_reversal() -> None:
    rows = [A.Row("C-999", "a", 3, "V.x", "violation", "reject", "accept", "")]
    assert A._reversal("C-999", rows) == []


def test_pending_watchlisted_violation_reports_nothing() -> None:
    rows = [A.Row("R-102", "sfc", 1, "V.x", "violation", "accept", "", "")]
    assert A._reversal("R-102", rows) == []


def test_watchlist_records_whether_we_reject_the_construct() -> None:
    rule, we_reject = A.WATCHLIST["R-101"]
    assert (rule, we_reject) == ("SL-V022", False)


# --- end-to-end --------------------------------------------------------------


def test_analyze_writes_snapshot_with_gap_field(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        _row("t0-a", "A.x", "inventory", "accept", "reject", "ours accepts - grammar gap"),
        _row("t0-b", "B.x", "inventory", "accept", "reject", "ours rejects too"),
    )
    out = tmp_path / "reports"
    assert _analyze(transcript=p, out_dir=out, gui_version="t", write=True) == 0
    snap = json.loads((out / f"{A.date.today()}-t.json").read_text())
    assert {e["file"]: e["gap"] for e in snap["tier0"]} == {
        "A.x": "we-too-lenient",
        "B.x": "wrong-both",
    }


def test_analyze_skips_write_when_nothing_filled(tmp_path: Path) -> None:
    p = _write(tmp_path, _row("t0-a", "A.x", "inventory", "accept", ""))
    rc = _analyze(transcript=p, out_dir=tmp_path, write=True)
    assert rc == 0
    assert "no real statuses filled yet" in A.LAST_OUTPUT
    assert not list(tmp_path.glob("*.json"))


def test_analyze_returns_2_on_empty_transcript(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text(HEADER, encoding="utf-8")
    assert _analyze(transcript=empty) == 2


def test_no_write_leaves_no_snapshot(tmp_path: Path) -> None:
    p = _write(tmp_path, _row("t0-a", "A.x", "inventory", "accept", "accept"))
    assert _analyze(transcript=p, out_dir=tmp_path, write=False) == 0
    assert not list(tmp_path.glob("*.json"))
