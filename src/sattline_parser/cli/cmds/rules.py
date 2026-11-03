"""``sattline rules``: list the validator rule registry."""

from __future__ import annotations

import argparse

from sattline_parser.validation.rules import RULES, Rule, UnknownRuleError, require_rule

from .._errors import CliError
from .._exit import ExitCode
from .._json import SCHEMA_PREFIX, dumps
from ._common import add_output_flags

__all__ = ["register", "run"]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "rules", help="list validator rules by id, name, severity and status"
    )
    parser.add_argument(
        "rule",
        nargs="?",
        metavar="RULE",
        help="show one rule by SL-V### id or enum name (case-insensitive)",
    )
    parser.add_argument(
        "--include-retired",
        action="store_true",
        help="include retired rules in the listing (a single lookup always sees them)",
    )
    add_output_flags(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    rules = _select(args.rule, include_retired=args.include_retired)
    _emit(rules, args=args)
    return int(ExitCode.OK)


def _select(value: str | None, *, include_retired: bool) -> list[Rule]:
    if value is not None:
        try:
            return [require_rule(value)]
        except UnknownRuleError as exc:
            raise CliError(f"{exc} (run 'sattline rules' to list rule ids)") from exc
    selected = [rule for rule in RULES if include_retired or not rule.retired]
    return selected


def _emit(rules: list[Rule], *, args: argparse.Namespace) -> None:
    if args.json:
        print(
            dumps(
                {
                    "schema": f"{SCHEMA_PREFIX}.rules",
                    "count": len(rules),
                    "rules": [rule.to_json() for rule in rules],
                }
            )
        )
        return
    if args.jsonl:
        for rule in rules:
            print(dumps(rule.to_json(), compact=True))
        print(
            dumps(
                {"schema": f"{SCHEMA_PREFIX}.rules", "summary": True, "count": len(rules)},
                compact=True,
            )
        )
        return
    if len(rules) == 1:
        _print_rule(rules[0])
        return
    for rule in rules:
        print(f"{rule.id:7} {rule.name:38} {rule.status.value:13} {rule.summary}")


def _print_rule(rule: Rule) -> None:
    print(f"{rule.id}  {rule.name}")
    print(f"  status:   {rule.status.value}")
    print(f"  severity: {rule.severity.value}")
    print(f"  scope:    {rule.scope.value}")
    print(f"  summary:  {rule.summary}")
    if rule.details is not None:
        print(f"  details:  {rule.details}")
