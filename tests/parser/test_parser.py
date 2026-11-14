# pyright: reportPrivateUsage=false
"""Fuzz harness smoke tests and corpus regression checks for the SattLine parser."""

from __future__ import annotations

import pathlib

import pytest

from fuzzing.fuzz_harness import (
    FuzzResult,
    FuzzSummary,
    _is_expected_parse_error,
    assert_no_crashes,
    assert_no_timeouts,
    collect_corpus_inputs,
    fuzz_parse_text,
    generate_random_text,
    run_corpus_regression,
    run_random_fuzz,
)

repo_root = pathlib.Path(__file__).resolve().parents[2]
CORPUS_DIR = repo_root / "tests" / "fixtures" / "corpus"


def _min_fuzz_result(
    input_desc: str = "test",
    *,
    success: bool = True,
    has_result: bool = True,
    has_error: bool = False,
    duration_ms: float = 100.0,
) -> FuzzResult:
    return FuzzResult(
        input_desc=input_desc,
        success=success,
        result=FuzzSummary(root_name="BasePicture", node_count=3) if has_result else None,
        error=ValueError("boom") if has_error else None,
        duration_ms=duration_ms,
    )


class TestFuzzParseText:
    def test_accepts_valid_sattline_program(self):
        corpus_file = CORPUS_DIR / "valid" / "MinimalProgram.s"
        source = corpus_file.read_text(encoding="utf-8")
        result = fuzz_parse_text(source, input_desc="valid-program")
        assert result.success
        assert result.error is None
        assert result.duration_ms > 0
        assert result.result is not None
        assert result.result.root_name == "BasePicture"
        assert result.result.node_count > 0

    def test_reports_no_summary_for_invalid_input(self):
        result = fuzz_parse_text("PROGRAM @@@@\nENDPROGRAM\n", input_desc="malformed")
        assert not result.success
        assert result.error is not None
        assert result.result is None

    def test_rejects_malformed_input_gracefully(self):
        source = "PROGRAM @@@@\nENDPROGRAM\n"
        result = fuzz_parse_text(source, input_desc="malformed")
        assert not result.success
        assert result.error is not None
        assert _is_expected_parse_error(result.error)

    def test_handles_empty_string(self):
        result = fuzz_parse_text("", input_desc="empty")
        assert not result.success
        assert result.error is not None
        assert _is_expected_parse_error(result.error)

    def test_handles_very_long_input(self):
        source = "PROGRAM Long\n" + "x := 1;\n" * 1000 + "ENDPROGRAM\n"
        result = fuzz_parse_text(source, input_desc="long-input", timeout=5.0)
        assert not result.success
        assert result.error is not None
        assert _is_expected_parse_error(result.error)
        assert result.duration_ms > 0


class TestCollectCorpusInputs:
    def test_collects_valid_files(self):
        inputs = collect_corpus_inputs(CORPUS_DIR, include_invalid=False, max_files=5)
        assert len(inputs) > 0
        for file_path, content in inputs[:3]:
            assert isinstance(file_path, str)
            assert isinstance(content, str)
            assert len(content) > 0

    def test_collects_invalid_files(self):
        inputs = collect_corpus_inputs(CORPUS_DIR, include_valid=False, include_invalid=True, max_files=5)
        assert len(inputs) > 0

    def test_respects_max_files(self):
        inputs = collect_corpus_inputs(CORPUS_DIR, max_files=3)
        assert len(inputs) <= 3

    def test_includes_valid_by_default(self):
        inputs = collect_corpus_inputs(CORPUS_DIR, max_files=10)
        paths = [p for p, _ in inputs]
        assert any("valid" in p for p in paths)


class TestRunCorpusRegression:
    def test_runs_without_crashes(self):
        results = run_corpus_regression(CORPUS_DIR, max_files=10, timeout=5.0)
        assert len(results) > 0
        assert_no_crashes(results)

    def test_runs_without_timeouts(self):
        results = run_corpus_regression(CORPUS_DIR, max_files=10, timeout=5.0)
        assert_no_timeouts(results)

    def test_valid_files_parse_successfully(self):
        inputs = collect_corpus_inputs(CORPUS_DIR, include_invalid=False, max_files=5)
        results = [fuzz_parse_text(content, input_desc=file_path) for file_path, content in inputs]
        failures = [f"{r.input_desc}: {r.error}" for r in results if not r.success]
        assert failures == []
        assert len(results) == len(inputs)

    def test_invalid_files_are_classified(self):
        inputs = collect_corpus_inputs(CORPUS_DIR, include_valid=False, include_invalid=True, max_files=20)
        results = [fuzz_parse_text(content, input_desc=file_path) for file_path, content in inputs]
        # An "invalid" fixture may be semantically invalid (it parses, then fails
        # validation) or syntactically invalid (an expected parse error). What it
        # may never do is raise an internal error.
        crashes = [
            f"{r.input_desc}: {type(r.error).__name__}: {r.error}"
            for r in results
            if r.error is not None and not _is_expected_parse_error(r.error)
        ]
        assert crashes == []
        assert all(r.result is not None for r in results if r.success)


class TestGenerateRandomText:
    def test_generates_text_of_correct_length(self):
        text = generate_random_text(length=50)
        # Allow some flexibility - the function tries to get close to the target length
        assert 40 <= len(text) <= 60

    def test_generates_deterministic_output_with_seed(self):
        text1 = generate_random_text(length=100, seed=42)
        text2 = generate_random_text(length=100, seed=42)
        assert text1 == text2

    def test_generates_different_output_without_seed(self):
        text1 = generate_random_text(length=100)
        text2 = generate_random_text(length=100)
        assert text1 != text2


class TestRunRandomFuzz:
    def test_runs_without_crashes(self):
        results = run_random_fuzz(rounds=20, text_length=50, timeout=2.0, seed=123)
        assert len(results) == 20
        assert [r.input_desc for r in results[:2]] == ["random:seed=123", "random:seed=124"]
        assert_no_crashes(results)

    def test_results_have_correct_structure(self):
        results = run_random_fuzz(rounds=10, seed=456)
        for result in results:
            assert isinstance(result, FuzzResult)
            assert isinstance(result.input_desc, str)
            assert isinstance(result.success, bool)
            assert isinstance(result.duration_ms, float)

    def test_seeded_runs_are_replayable(self):
        first = run_random_fuzz(rounds=3, text_length=40, timeout=2.0, seed=99)
        second = run_random_fuzz(rounds=3, text_length=40, timeout=2.0, seed=99)
        assert [(r.input_desc, r.success) for r in first] == [(r.input_desc, r.success) for r in second]

    def test_timeout_protected(self):
        results = run_random_fuzz(rounds=5, text_length=1000, timeout=1.0, seed=789)
        assert [r.input_desc for r in results] == [f"random:seed={789 + i}" for i in range(5)]
        assert all(r.duration_ms < 2000 for r in results)


class TestAssertNoCrashes:
    def test_passes_with_no_crashes(self):
        results = [_min_fuzz_result(f"ok-{i}", success=True) for i in range(3)]
        assert_no_crashes(results)

    def test_raises_on_crash(self):
        results = [
            _min_fuzz_result("ok", success=True),
            _min_fuzz_result("crash", success=False, has_error=True),
        ]
        # Replace ValueError with a custom exception not in _is_expected_parse_error
        results[1].error = RuntimeError("simulated crash")
        with pytest.raises(AssertionError, match="crash"):
            assert_no_crashes(results)


class TestAssertNoTimeouts:
    def test_passes_with_no_timeouts(self):
        results = [_min_fuzz_result(f"ok-{i}", success=True) for i in range(3)]
        assert_no_timeouts(results)

    def test_raises_on_timeout(self):
        from fuzzing.fuzz_harness import FuzzTimeoutError  # noqa: PLC0415

        results = [
            _min_fuzz_result("ok", success=True),
            _min_fuzz_result("timeout", success=False),
        ]
        results[1].error = FuzzTimeoutError("timed out")
        with pytest.raises(AssertionError, match="timeout"):
            assert_no_timeouts(results)
