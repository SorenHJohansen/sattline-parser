"""Atheris-based fuzz harness for the compressed text decoder.

Only expected invalid-input errors (:class:`~sattline_parser.preprocessing.PreprocessError`)
are absorbed; any unexpected exception (e.g. an internal bug in the decoder's
source-map construction) propagates to atheris/ClusterFuzzLite.

``atheris.instrument_all()`` is called before ``Setup`` for Python coverage
feedback; an ``instrument_imports`` block cannot work because the
``sattline_parser`` package is already imported by the time this module body
runs (see ``parser_fuzzer`` for details).
"""

import sys

import atheris  # type: ignore[import-untyped]

from sattline_parser.preprocessing import PreprocessError
from sattline_parser.preprocessing.compressed import preprocess_source


def test_one_input(data: bytes) -> None:
    source = data.decode("utf-8", errors="replace")
    try:
        preprocess_source(source)
    except PreprocessError:
        # Expected malformed compressed input: not a crash.
        return


if __name__ == "__main__":
    atheris.instrument_all()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
