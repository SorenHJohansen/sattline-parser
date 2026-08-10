# pyright: reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
import shutil
import subprocess

from ._parser_core_test_support import *


def test_fuzz_harness_timeout_and_default_input_description(monkeypatch: pytest.MonkeyPatch):
    class FakeFuture:
        def result(self, timeout: float):
            assert timeout == 0.25
            raise parser_fuzz_harness.concurrent.futures.TimeoutError()

    class FakeExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, source: str, **kwargs):
            assert fn is parser_fuzz_harness.parse_source_text
            assert source == "ABC"
            return FakeFuture()

    monkeypatch.setattr(
        parser_fuzz_harness.concurrent.futures,
        "ThreadPoolExecutor",
        lambda max_workers=1: FakeExecutor(),
    )
    result = parser_fuzz_harness.fuzz_parse_text("ABC", timeout=0.25)

    assert result.input_desc == "text(3 chars)"
    assert result.success is False
    assert isinstance(result.error, parser_fuzz_harness.TimeoutError)
    assert str(result.error) == "Parse timed out after 0.25s"
    assert result.duration_ms >= 0.0


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
