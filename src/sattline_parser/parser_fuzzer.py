"""Atheris-based fuzz harness for the SattLine parser.

ClusterFuzzLite uses atheris-based fuzz targets.

This target parses input directly and lets **unexpected** exceptions escape so
atheris/ClusterFuzzLite reports them. Only expected invalid-input errors
(Lark ``UnexpectedInput`` and :class:`~sattline_parser.preprocessing.PreprocessError`)
are absorbed; an internal ``ValueError``/``TypeError``/``KeyError`` from the
transformer or parser internals is treated as a fuzz failure.
"""

import sys

import atheris  # type: ignore[import-untyped]
from lark.exceptions import UnexpectedInput

from sattline_parser.api import parse_source_text
from sattline_parser.preprocessing import PreprocessError


def test_one_input(data: bytes) -> None:
    source = data.decode("utf-8", errors="replace")
    try:
        parse_source_text(source, log_failures=False)
    except (UnexpectedInput, PreprocessError):
        # Expected invalid SattLine input: not a crash.
        return


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
