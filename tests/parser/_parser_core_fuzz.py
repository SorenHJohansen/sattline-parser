# pyright: reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
import queue
import shutil
import struct
import subprocess

from ._parser_core_test_support import *


def test_fuzz_harness_timeout_and_default_input_description(monkeypatch: pytest.MonkeyPatch):
    sleeping_worker = "import time\nimport sys\nwhile True:\n    time.sleep(3600)\n"
    monkeypatch.setattr(parser_fuzz_harness, "_WORKER_SOURCE", sleeping_worker)
    result = parser_fuzz_harness.fuzz_parse_text("ABC", timeout=0.25)

    assert result.input_desc == "text(3 chars)"
    assert result.success is False
    assert isinstance(result.error, parser_fuzz_harness.TimeoutError)
    assert "timed out" in str(result.error)
    assert result.duration_ms >= 0.0


def test_fuzz_worker_survives_and_reuses_single_process():
    worker = parser_fuzz_harness._FuzzWorker()
    try:
        raw1 = worker.parse("garbage", 5.0)
        raw2 = worker.parse("garbage", 5.0)
        assert raw1.get("ok") is False
        assert raw2.get("ok") is False
        # Same worker process is reused across inputs (no spawn per input).
        assert worker._proc is not None
    finally:
        worker.close()


def test_reconstruct_error_resolves_known_and_unknown_classes():
    from lark.exceptions import UnexpectedToken  # noqa: PLC0415

    token_error = parser_fuzz_harness._reconstruct_error("lark.exceptions.UnexpectedToken", "boom")
    assert isinstance(token_error, UnexpectedToken)
    assert str(token_error) == "boom"
    fallback = parser_fuzz_harness._reconstruct_error("no.such.Cls", "oops")
    assert isinstance(fallback, RuntimeError)
    assert str(fallback) == "oops"
    assert isinstance(parser_fuzz_harness._reconstruct_error("", "msg"), RuntimeError)
    assert isinstance(parser_fuzz_harness._reconstruct_error("OnlyClass", "msg"), RuntimeError)


def test_fuzz_worker_recovers_from_killed_process():
    worker = parser_fuzz_harness._FuzzWorker()
    try:
        assert worker.parse("garbage", 5.0).get("ok") is False
        if worker._proc is not None:
            worker._proc.kill()
        raw = worker.parse("garbage", 5.0)
        assert raw.get("ok") is False
        assert worker._proc is not None  # restarted
    finally:
        worker.close()


def test_fuzz_worker_close_terminates_process_and_reader():
    worker = parser_fuzz_harness._FuzzWorker()
    proc = worker._proc
    reader = worker._reader
    worker.close()
    assert proc is not None and reader is not None
    assert proc.poll() is not None
    assert reader.is_alive() is False


def test_drain_worker_results_handles_eof_truncation_and_results():
    from io import BytesIO  # noqa: PLC0415

    from sattline_parser.fuzz_harness import _drain_worker_results  # noqa: PLC0415

    # A stream with one valid result then EOF.
    stream = BytesIO(struct.pack(">I", 2) + b"{}")
    results: queue.Queue[dict[str, object]] = queue.Queue()
    _drain_worker_results(stream, results)
    assert results.get() == {}

    # A stream that advertises 5 bytes but closes after 2: no crash.
    stream2 = BytesIO(b"\x00\x00\x00\x05ab")
    results2: queue.Queue[dict[str, object]] = queue.Queue()
    _drain_worker_results(stream2, results2)
    assert results2.empty()

    # A stream that advertises 5 bytes but writes nothing before EOF.
    stream3 = BytesIO(b"\x00\x00\x00\x05")
    results3: queue.Queue[dict[str, object]] = queue.Queue()
    _drain_worker_results(stream3, results3)
    assert results3.empty()

    # A corrupt payload (invalid JSON) must be tolerated.
    stream4 = BytesIO(struct.pack(">I", 2) + b"ab")
    results4: queue.Queue[dict[str, object]] = queue.Queue()
    _drain_worker_results(stream4, results4)
    assert results4.empty()


def test_fuzz_worker_restarts_when_process_is_gone_or_pipe_breaks():
    worker = parser_fuzz_harness._FuzzWorker()
    try:
        assert worker.parse("garbage", 5.0).get("ok") is False

        # Lost process -> restart on next parse.
        worker._proc = None
        raw = worker.parse("garbage", 5.0)
        assert raw.get("ok") is False
        assert worker._proc is not None

        # Broken pipe during write -> restart + WorkerError.
        class _BrokenPipe:
            def write(self, _data: bytes) -> None:
                raise BrokenPipeError()

            def flush(self) -> None:
                pass

        assert worker._proc is not None
        worker._proc.stdin = _BrokenPipe()  # type: ignore[assignment]
        raw2 = worker.parse("garbage", 5.0)
        assert raw2.get("ok") is False
        assert worker._proc is not None
    finally:
        worker.close()


def test_as_float_fallback_for_non_numeric_values():
    assert parser_fuzz_harness._as_float(3.5) == 3.5
    assert parser_fuzz_harness._as_float("nope") == 0.0


def test_reconstruct_error_non_exception_class_falls_back_to_runtime_error():
    error = parser_fuzz_harness._reconstruct_error("builtins.int", "not an exception")
    assert isinstance(error, RuntimeError)


def test_run_random_fuzz_without_explicit_seed():
    results = parser_fuzz_harness.run_random_fuzz(rounds=3, text_length=20)
    assert len(results) == 3


def test_fuzz_harness_collect_corpus_inputs_uses_default_dir_and_skips_missing_or_unreadable_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    semantic_dir = tmp_path / "semantic"
    semantic_dir.mkdir()
    good_file = semantic_dir / "good.s"
    bad_file = semantic_dir / "bad.s"
    good_file.write_text("good", encoding="utf-8")
    bad_file.write_text("bad", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == bad_file:
            raise OSError("unreadable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(parser_fuzz_harness, "CORPUS_DIR", tmp_path)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    inputs = parser_fuzz_harness.collect_corpus_inputs(
        None,
        include_valid=False,
        include_invalid=True,
        include_edge_cases=False,
        include_semantic=True,
    )

    assert inputs == [(str(good_file), "good")]


def test_parser_package_root_import_skips_fuzz_harness_outside_repo(tmp_path: Path) -> None:
    package_copy = tmp_path / "sattline_parser"
    shutil.copytree(_repo_path("src", "sattline_parser"), package_copy)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                f"import sys; sys.path.insert(0, {str(tmp_path)!r}); "
                "import sattline_parser; print(sattline_parser.parse_source_text.__name__)"
            ),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "parse_source_text"


def test_parser_package_root_still_reexports_fuzz_harness_symbols() -> None:
    sattline_parser = sys.modules["sattline_parser"]

    assert sattline_parser.fuzz_harness is parser_fuzz_harness
    assert sattline_parser.FuzzResult is parser_fuzz_harness.FuzzResult
    assert sattline_parser.run_random_fuzz is parser_fuzz_harness.run_random_fuzz
