"""``sattline corpus`` — batch triage over a source tree."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Sequence
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path

from ...project.formats import ALL_CODE_EXTENSIONS
from ...project.parallel import pool_allowed, process_pool
from .._errors import CliError
from .._exit import ExitCode
from .._findings import READ_RULE
from .._io import read_source_path
from .._json import SCHEMA_PREFIX, dumps
from .._validate import Analysis, analyse
from ._common import add_fail_on, add_output_flags, bounded_positive_int, fails_on

__all__ = ["CorpusRow", "register", "run"]

_LOGGER = getLogger(__name__)

_SOURCE_SUFFIXES = ALL_CODE_EXTENSIONS

#: Upper bound for ``--jobs``: a thread count past this is a resource request
#: the machine cannot service, not a faster scan.
_MAX_JOBS = 32


@dataclass(frozen=True, slots=True)
class CorpusRow:
    """The outcome for one file in the tree."""

    file: str
    errors: int
    rules: tuple[tuple[str, int], ...]

    def to_json(self) -> dict[str, object]:
        return {
            "file": self.file,
            "errors": self.errors,
            "rules": dict(self.rules),
        }


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("corpus", help="parse and validate a whole tree")
    parser.add_argument("root", metavar="ROOT", help="directory to scan for .s/.x sources")
    add_output_flags(parser)
    parser.add_argument(
        "--jobs",
        type=bounded_positive_int(_MAX_JOBS),
        default=1,
        metavar="N",
        help=f"files to process at once (at most {_MAX_JOBS})",
    )
    parser.add_argument("--summary", action="store_true", help="only print the histogram")
    add_fail_on(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        raise CliError(f"cannot read {root}: not a directory")
    paths = sorted(path for path in root.rglob("*") if path.suffix.lower() in _SOURCE_SUFFIXES)
    rows = _analyse_all(paths, jobs=args.jobs)
    _emit(rows, args=args)
    return int(_exit_code(rows, fail_on=args.fail_on))


def _analyse_path(path: Path) -> CorpusRow:
    """Analyse one file. A worker entry point, so it takes and returns plain data."""
    try:
        source = read_source_path(path)
    except CliError:
        return CorpusRow(file=str(path), errors=1, rules=((READ_RULE, 1),))
    analysis: Analysis = analyse(source.name, source.text, absolute=False)
    rules = Counter(finding.rule for finding in analysis.findings)
    errors = sum(1 for finding in analysis.findings if finding.is_error)
    return CorpusRow(
        file=str(path),
        errors=errors,
        rules=tuple(sorted(rules.items())),
    )


def _analyse_all(paths: Sequence[Path], *, jobs: int) -> list[CorpusRow]:
    """Analyse every path, in that many processes when it is safe to start them.

    The samples are independent and each worker returns a plain row, so a
    process pool shares nothing: no parser, no counter, and no source text
    crosses between jobs. Results keep the input order. A pool that cannot start
    or dies mid-run falls back to this process with a warning, because a scan is
    the command's job rather than an optimisation.
    """
    if jobs <= 1 or len(paths) <= 1:
        return [_analyse_path(path) for path in paths]
    if not pool_allowed():
        _LOGGER.warning("a daemonic process cannot start workers; scanning in this process")
        return [_analyse_path(path) for path in paths]
    try:
        pool = process_pool(min(jobs, len(paths)))
    except (OSError, RuntimeError, ValueError) as exc:
        _LOGGER.warning("parallel scan unavailable (%s); scanning in this process", exc)
        return [_analyse_path(path) for path in paths]
    try:
        return list(pool.map(_analyse_path, paths, chunksize=1))
    except (BrokenProcessPool, OSError) as exc:
        pool.shutdown(wait=True, cancel_futures=True)
        _LOGGER.warning("worker pool failed (%s); scanning in this process", exc)
        return [_analyse_path(path) for path in paths]
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)


def _emit(rows: Sequence[CorpusRow], *, args: argparse.Namespace) -> None:
    histogram = _histogram(rows)
    summary = {
        "files": len(rows),
        "clean": sum(1 for row in rows if not row.errors),
        "failing": sum(1 for row in rows if row.errors),
        "rules": dict(histogram),
    }
    if args.json or args.jsonl:
        payload = {
            "schema": f"{SCHEMA_PREFIX}.corpus",
            **summary,
            "results": [] if args.summary else [row.to_json() for row in rows],
        }
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    print(f"files: {summary['files']}  clean: {summary['clean']}  failing: {summary['failing']}")
    for rule, count in histogram.most_common():
        print(f"  {rule}: {count}")
    if not args.summary:
        for row in rows:
            if row.errors:
                print(f"  {row.file}: {row.errors} error(s)")


def _histogram(rows: Iterable[CorpusRow]) -> Counter[str]:
    histogram: Counter[str] = Counter()
    for row in rows:
        for rule, count in row.rules:
            histogram[rule] += count
    return histogram


def _exit_code(rows: Sequence[CorpusRow], *, fail_on: str) -> ExitCode:
    fails = fails_on(sum(row.errors for row in rows), fail_on)
    return ExitCode.FINDINGS if fails else ExitCode.OK
