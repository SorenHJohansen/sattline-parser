# pyright: reportUnknownVariableType=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_preprocess_sl_text_injects_modulecode_before_equationblock_when_missing():
    decoded, mapping = preprocess_sl_text("MODULEDEFINITION Demo EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :")

    assert "MODULEDEFINITION Demo ModuleCode EQUATIONBLOCK Main" in decoded
    assert mapping["#84"] == "ModuleCode"
