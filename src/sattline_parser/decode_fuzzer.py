"""Atheris-based fuzz harness for the compressed text decoder.

Only expected invalid-input errors (:class:`~sattline_parser.preprocessing.PreprocessError`)
are absorbed; any unexpected exception (e.g. an internal bug in the decoder's
source-map construction) propagates to atheris/ClusterFuzzLite.
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
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
