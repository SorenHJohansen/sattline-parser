"""``sattline corpus`` — batch triage over a source tree."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .._errors import CliError
from .._exit import ExitCode
from .._json import SCHEMA_PREFIX, dumps
from .._validate import Analysis, analyse
from ._common import add_output_flags

__all__ = ["CorpusRow", "register", "run"]

_SOURCE_SUFFIXES = frozenset({".s", ".x"})


@dataclass(frozen=True, slots=True)
class CorpusRow:
    """The outcome for one file in the tree."""

    file: str
    errors: int
    warnings: int
    rules: tuple[tuple[str, int], ...]

    def to_json(self) -> dict[str, object]:
        return {
            "file": self.file,
            "errors": self.errors,
            "warnings": self.warnings,
            "rules": dict(self.rules),
        }


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("corpus", help="parse and validate a whole tree")
    parser.add_argument("root", metavar="ROOT", help="directory to scan for .s/.x sources")
    add_output_flags(parser)
    parser.add_argument("--jobs", type=_positive_int, default=1, metavar="N", help="files to process at once")
    parser.add_argument("--summary", action="store_true", help="only print the histogram")
    parser.add_argument(
        "--fail-on",
        choices=("error", "any", "never"),
        default="error",
        help="what makes the exit code 1 (default: error)",
    )
    parser.set_defaults(handler=run)


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


def run(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        raise CliError(f"cannot read {root}: not a directory")
    paths = sorted(path for path in root.rglob("*") if path.suffix.lower() in _SOURCE_SUFFIXES)
    rows = _analyse_all(paths, jobs=args.jobs)
    _emit(rows, args=args)
    return int(_exit_code(rows, fail_on=args.fail_on))


def _analyse_all(paths: Sequence[Path], *, jobs: int) -> list[CorpusRow]:
    def one(path: Path) -> CorpusRow:
        try:
            text = path.read_bytes().decode("cp1252")
        except (OSError, UnicodeDecodeError):
            return CorpusRow(file=str(path), errors=1, warnings=0, rules=(("READ_ERROR", 1),))
        analysis: Analysis = analyse(str(path), text, absolute=False)
        rules = Counter(finding.rule for finding in analysis.findings)
        errors = sum(1 for finding in analysis.findings if finding.is_error)
        return CorpusRow(
            file=str(path),
            errors=errors,
            warnings=len(analysis.findings) - errors,
            rules=tuple(sorted(rules.items())),
        )

    if jobs <= 1:
        return [one(path) for path in paths]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(one, paths))


def _emit(rows: Sequence[CorpusRow], *, args: argparse.Namespace) -> None:
    histogram = _histogram(rows)
    summary = {
        "files": len(rows),
        "clean": sum(1 for row in rows if not row.errors and not row.warnings),
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
            if row.errors or row.warnings:
                print(f"  {row.file}: {row.errors} error(s), {row.warnings} warning(s)")


def _histogram(rows: Iterable[CorpusRow]) -> Counter[str]:
    histogram: Counter[str] = Counter()
    for row in rows:
        for rule, count in row.rules:
            histogram[rule] += count
    return histogram


def _exit_code(rows: Sequence[CorpusRow], *, fail_on: str) -> ExitCode:
    if fail_on == "never":
        return ExitCode.OK
    if fail_on == "any":
        return ExitCode.FINDINGS if any(row.errors or row.warnings for row in rows) else ExitCode.OK
    return ExitCode.FINDINGS if any(row.errors for row in rows) else ExitCode.OK
