"""Profile the SattLine parse pipeline on real files.

Drives the parser pipeline stage-by-stage on one or more source files and
reports per-stage wall time (and optionally memory), so hotspots can be
attributed to I/O, preprocessing, the Lark parse, source remapping, or the
SLTransformer.

Usage:
    python scripts/profile_parse.py PATH [PATH ...] [--repeat N] [--memory]
    python scripts/profile_parse.py PATH --profile out.prof

Stages mirror ``parse_source_file`` (api.py): decode -> preprocess -> parse ->
remap -> transform. The Lark parser is built once and reused across repeats so
grammar-compile time is never counted.
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import cast

from sattline_parser import api
from sattline_parser.preprocessing import decode_coded_stream, is_coded
from sattline_parser.source_document import SourceDocument, remap_tree_to_original
from sattline_parser.transformer.sl_transformer import SLTransformer

STAGE_NAMES = ("read_decode", "preprocess", "parse", "remap", "transform", "total")


def _load_text(path: Path) -> str:
    """Mirror parse_source_file's decode path: coded bytes or text fallback."""
    raw = path.read_bytes()
    if is_coded(raw):
        return decode_coded_stream(raw)
    return api.read_text_with_fallback(path)


def _timed(fn: Callable[[], object]) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def _profile_once(
    path: Path,
    parser: api.Lark,
    *,
    transform_only: bool,
) -> dict[str, float]:
    """Run a single staged pass and return per-stage seconds."""
    results: dict[str, float] = {}
    text = _load_text(path)

    results["read_decode"] = 0.0  # attributed once per file below

    doc_holder: dict[str, object] = {}

    def do_preprocess_holder() -> None:
        doc_holder["doc"] = api.preprocess_source(text)

    tree_holder: dict[str, object] = {}

    def do_parse() -> None:
        doc = cast(SourceDocument, doc_holder["doc"])
        tree_holder["tree"] = parser.parse(doc.normalized_text)

    def do_remap() -> None:
        doc = cast(SourceDocument, doc_holder["doc"])
        tree = tree_holder["tree"]
        remap_tree_to_original(tree, doc)

    transformer = SLTransformer()

    def do_transform() -> None:
        tree = tree_holder["tree"]
        transformer.transform(tree)

    if transform_only:
        # Time read+decode separately from the single shared preprocess result.
        results["read_decode"] = _timed(lambda: _load_text(path))
        results["preprocess"] = _timed(do_preprocess_holder)
        results["parse"] = _timed(do_parse)
        results["remap"] = _timed(do_remap)
        results["transform"] = _timed(do_transform)
        results["total"] = (
            results["read_decode"] + results["preprocess"] + results["parse"] + results["remap"] + results["transform"]
        )
        return results

    # Full-pipeline timing for the total; each stage individually.
    results["read_decode"] = _timed(lambda: _load_text(path))
    results["preprocess"] = _timed(do_preprocess_holder)
    results["parse"] = _timed(do_parse)
    results["remap"] = _timed(do_remap)
    results["transform"] = _timed(do_transform)
    results["total"] = sum(results[name] for name in ("read_decode", "preprocess", "parse", "remap", "transform"))
    return results


def _profile_file(
    path: Path,
    parser: api.Lark,
    *,
    repeat: int,
    memory: bool,
    transform_only: bool,
) -> dict[str, list[float]]:
    collected: dict[str, list[float]] = {name: [] for name in STAGE_NAMES}

    if memory:
        tracemalloc.start()

    for _ in range(repeat):
        res = _profile_once(path, parser, transform_only=transform_only)
        for name in STAGE_NAMES:
            collected[name].append(res[name])

    peak = tracemalloc.get_traced_memory()[1] if memory else 0
    if memory:
        tracemalloc.stop()
    collected["_peak_memory"] = [float(peak)]

    # read_decode is reloaded on every repeat; drop it from total for the total
    # measurement to avoid double counting I/O that is not part of the parse.
    return collected


def _fmt_seconds(value: float) -> str:
    if value >= 60:
        return f"{value / 60:.1f}m"
    return f"{value:.3f}s"


def _report(path: Path, collected: dict[str, list[float]]) -> None:
    print(f"\n== {path} ({_load_text(path).__len__() * 1e-6:.1f} MB) ==")
    header = f"{'stage':<14}{'min':>12}{'median':>12}{'share(med)':>12}"
    print(header)
    print("-" * len(header))
    total_med = statistics.median(collected["total"])
    for name in STAGE_NAMES:
        if name == "total":
            continue
        values = collected[name]
        med = statistics.median(values)
        share = f"{med / total_med * 100:.1f}%" if total_med else "-"
        print(f"{name:<14}{_fmt_seconds(min(values)):>12}{_fmt_seconds(med):>12}{share:>12}")
    print(f"{'total':<14}{_fmt_seconds(min(collected['total'])):>12}{_fmt_seconds(total_med):>12}")
    if "_peak_memory" in collected:
        peak = max(collected["_peak_memory"])
        print(f"peak memory: {peak / 1e6:.1f} MB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="source files to profile")
    parser.add_argument("--repeat", type=int, default=3, help="timing repeats per file")
    parser.add_argument("--memory", action="store_true", help="track peak memory (tracemalloc)")
    parser.add_argument("--profile", type=Path, default=None, help="dump a cProfile pstats file of the full pipeline")
    parser.add_argument(
        "--transform-only",
        action="store_true",
        help="time read+decode only once and share one preprocess result across stages",
    )
    args = parser.parse_args(argv)

    build_start = time.perf_counter()
    parser = api.build_lark_parser()
    print(f"lark parser built in {time.perf_counter() - build_start:.3f}s (not counted in stages)")

    if args.profile is not None:
        profiler = cProfile.Profile()
        profiler.enable()
        for path in args.paths:
            _profile_once(path, parser, transform_only=args.transform_only)
        profiler.disable()
        args.profile.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(args.profile))
        pstats.Stats(str(args.profile)).sort_stats("cumulative").print_stats(30)
        return 0

    for path in args.paths:
        if not path.is_file():
            print(f"skip: {path} is not a file")
            continue
        collected = _profile_file(
            path, parser, repeat=args.repeat, memory=args.memory, transform_only=args.transform_only
        )
        _report(path, collected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
