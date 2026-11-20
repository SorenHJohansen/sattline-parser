"""``sattline check`` reports a transformer rejection as a finding, not a crash.

Lark wraps an exception raised inside a transformer rule in ``VisitError``. A
rejection of the source, such as a duplicate singular clause, must reach the CLI
as a parse failure so the run exits with findings instead of an internal error.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode
from sattline_parser.transformer.sl_transformer import SLTransformer

from ._cli_support import VALID_SOURCE, write_source

#: The valid fixture with two ``Layer_`` arguments in its module header.
_DUPLICATE_CLAUSE_SOURCE = VALID_SOURCE.replace(
    "( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 )",
    "( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 Layer_ = 1 Layer_ = 2 )",
)


def test_check_reports_a_transformer_rejection_as_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_source(tmp_path, "Duplicate.s", _DUPLICATE_CLAUSE_SOURCE)

    def reject(self: SLTransformer, items: list[object]) -> NoReturn:
        raise ValueError("module header has more than one Layer_ argument")

    monkeypatch.setattr(SLTransformer, "argument", reject)

    assert main(["check", str(source)]) == ExitCode.FINDINGS

    out = capsys.readouterr().out
    assert f"{source}: module header has more than one Layer_ argument" in out
    assert "Traceback" not in out
