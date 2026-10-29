# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""``sattline query``: structural questions over one unit."""

from __future__ import annotations

import json

from sattline_parser.cli import main
from sattline_parser.cli._exit import ExitCode

from ._cli_support import PARSE_ERROR_SOURCE, VALID_SOURCE, write_source

_MODULE_SOURCE = (
    '"Syntax version 2.23, date: 2026-10-28-00:00:00.000 N"\n'
    '"Original file date: ---"\n'
    '"Program date: 2026-10-28-00:00:00.000, name: Query"\n'
    "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
    "TYPEDEFINITIONS\n"
    "   Child = MODULEDEFINITION DateCode_ 2\n"
    "   LOCALVARIABLES\n"
    "      Inner: integer := 0;\n"
    "   ModuleDef\n"
    "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "   GraphObjects :\n"
    '      TextObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 ) "Hi" Layer_ = 3\n'
    "   InteractObjects :\n"
    "      ComBut_ ( 0.0 , 0.0 ) ( 1.0 , 1.0 )\n"
    "         Bool_Value\n"
    "   ENDDEF (*Child*);\n"
    "LOCALVARIABLES\n"
    "   Flag: boolean := False;\n"
    "SUBMODULES\n"
    "   Sub Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 3\n"
    "   LOCALVARIABLES\n"
    "      Deep: integer := 0;\n"
    "   ModuleDef\n"
    "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "   ENDDEF (*Sub*) ;\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ModuleCode\n"
    "SEQUENCE Demo COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
    "   FreeWord1 Iteration\n"
    "      SEQSTEP Run\n"
    "      SEQTRANSITION Gate WAIT_FOR Flag\n"
    "   FreeWord2\n"
    "   FreeWord3\n"
    "   SEQINITSTEP Start\n"
    "   SEQTRANSITION Go WAIT_FOR Flag\n"
    "ENDSEQUENCE\n"
    "EQUATIONBLOCK Calc COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
    "   Flag = True;\n"
    "   Helper(Flag);\n"
    "ENDDEF (*BasePicture*);\n"
)


_FULL_SOURCE = (
    '"Syntax version 2.23, date: 2026-10-28-00:00:00.000 N"\n'
    '"Original file date: ---"\n'
    '"Program date: 2026-10-28-00:00:00.000, name: Full"\n'
    "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
    "TYPEDEFINITIONS\n"
    "   Child = MODULEDEFINITION DateCode_ 2\n"
    "   MODULEPARAMETERS\n"
    "      Setpoint: real := 0.0;\n"
    "   LOCALVARIABLES\n"
    "      Inner: integer := 0;\n"
    "   ModuleDef\n"
    "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "   ENDDEF (*Child*);\n"
    "LOCALVARIABLES\n"
    "   Flag: boolean := False;\n"
    "   Count: integer := 0;\n"
    "   Total: integer := 0;\n"
    "SUBMODULES\n"
    "   Inst Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : Child ;\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ModuleCode\n"
    "SEQUENCE Flow COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
    "   SEQINITSTEP Init\n"
    "      ENTERCODE\n"
    "         Total = 0;\n"
    "   SEQTRANSITION TrStart WAIT_FOR Flag\n"
    "   SEQSTEP StepOne\n"
    "      ACTIVECODE\n"
    "         Total = Total + 1;\n"
    "   SUBSEQTRANSITION TrSub\n"
    "      SEQTRANSITION EnterSub WAIT_FOR True\n"
    "      SEQSTEP InSub\n"
    "   ENDSUBSEQTRANSITION\n"
    "   PARALLELSEQ\n"
    "      SEQSTEP ParA\n"
    "   PARALLELBRANCH\n"
    "      SEQSTEP ParB\n"
    "   ENDPARALLEL\n"
    "   ALTERNATIVESEQ\n"
    "      SEQTRANSITION AltA WAIT_FOR Flag\n"
    "      SEQSTEP AltStepA\n"
    "   ALTERNATIVEBRANCH\n"
    "      SEQTRANSITION AltB WAIT_FOR Flag\n"
    "      SEQSTEP AltStepB\n"
    "   ENDALTERNATIVE\n"
    "   SUBSEQUENCE Work\n"
    "      SEQSTEP WorkStep\n"
    "   ENDSUBSEQUENCE\n"
    "   SUBSEQSTEP Group\n"
    "      SEQSTEP Grouped\n"
    "   ENDSUBSEQSTEP\n"
    "   FreeWord1 Repeat\n"
    "      SEQSTEP LoopStep\n"
    "   FreeWord2 Flag\n"
    "      SEQSTEP ElseStep\n"
    "   FreeWord3\n"
    "ENDSEQUENCE\n"
    "EQUATIONBLOCK Calc COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
    "   Total = -Count;\n"
    "   Flag = NOT Flag AND ( Count > 1 ) OR Flag;\n"
    "   Total = IF Flag THEN Count + 1 ELSE Count - 1 ENDIF;\n"
    "   Wrapped(Outer(Flag), Count);\n"
    "   IF Flag THEN\n"
    "      Total = 1;\n"
    "   ELSIF Count > 2 THEN\n"
    "      Total = 2;\n"
    "   ELSE\n"
    "      Total = 3;\n"
    "   ENDIF\n"
    "ENDDEF (*BasePicture*);\n"
)


def test_module_parameters_and_type_instances(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Full.s", _FULL_SOURCE)

    assert main(["query", str(source), "--what", "symbols"]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "parameter Setpoint [Child]" in out
    assert "module_instance Inst" in out


def test_every_sfc_construct_is_walked(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Full.s", _FULL_SOURCE)

    assert main(["query", str(source), "--what", "symbols"]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "step StepOne" in out
    assert "transition TrSub" in out
    assert "step ParA" in out and "step ParB" in out
    assert "step AltStepA" in out and "step AltStepB" in out
    assert "subsequence Work" in out
    assert "substep Group" in out
    assert "loop Repeat" in out
    assert "step LoopStep" in out and "step ElseStep" in out


def test_statements_and_expressions_are_walked(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Full.s", _FULL_SOURCE)

    assert main(["query", str(source), "--what", "writers"]) == ExitCode.OK
    out = capsys.readouterr().out
    # Top-level statements, the loop condition and both IfStmt branches.
    assert out.count("writers Total") >= 6

    assert main(["query", str(source), "--what", "references", "--name", "Count"]) == ExitCode.OK
    out = capsys.readouterr().out
    # UnaryOp, BoolOp/Compare, TernaryOp, FuncCall arguments and IfStmt conditions.
    assert out.count("references Count") == 6

    assert main(["query", str(source), "--what", "callers"]) == ExitCode.OK
    out = capsys.readouterr().out
    assert "callers Wrapped" in out
    assert "callers Outer" in out


def test_symbols_cover_every_declaration_kind(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Query.s", _MODULE_SOURCE)

    assert main(["query", str(source), "--what", "symbols"]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "module_type Child" in out
    assert "submodule Sub" in out
    assert "variable Flag" in out
    assert "variable Inner [Child]" in out
    assert "loop Iteration" in out
    assert "step Run" in out
    assert "transition Gate" in out


def test_name_module_and_limit_filters(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Query.s", _MODULE_SOURCE)

    assert main(["query", str(source), "--what", "symbols", "--name", "inner"]) == ExitCode.OK
    assert "Inner" in capsys.readouterr().out

    assert main(["query", str(source), "--what", "symbols", "--module", "Sub"]) == ExitCode.OK
    out = capsys.readouterr().out
    assert "Deep" in out
    assert "Flag" not in out

    assert main(["query", str(source), "--what", "symbols", "--limit", "1"]) == ExitCode.OK
    assert len(capsys.readouterr().out.strip().splitlines()) == 1


def test_sequences_report_the_sfc_structure(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Query.s", _MODULE_SOURCE)

    assert main(["query", str(source), "--what", "sequences"]) == ExitCode.OK

    out = capsys.readouterr().out
    assert "sequences Demo" in out
    assert "3 element(s)" in out


def test_definitions_is_an_alias_for_symbols(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Query.s", _MODULE_SOURCE)

    assert main(["query", str(source), "--what", "definitions", "--name", "Gate"]) == ExitCode.OK
    assert "transition Gate" in capsys.readouterr().out


def test_references_writers_and_callers(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Query.s", _MODULE_SOURCE)

    assert main(["query", str(source), "--what", "references", "--name", "Flag"]) == ExitCode.OK
    assert capsys.readouterr().out.count("references Flag") == 3

    assert main(["query", str(source), "--what", "writers", "--name", "Flag"]) == ExitCode.OK
    assert "writers Flag" in capsys.readouterr().out

    assert main(["query", str(source), "--what", "callers"]) == ExitCode.OK
    assert "callers Helper" in capsys.readouterr().out


def test_graph_and_interact_objects(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Query.s", _MODULE_SOURCE)

    assert main(["query", str(source), "--what", "graph-objects"]) == ExitCode.OK
    assert "graph-objects TextObject (layer 3) [Child]" in capsys.readouterr().out

    assert main(["query", str(source), "--what", "interact-objects"]) == ExitCode.OK
    assert "interact-objects ComBut_ [Child]" in capsys.readouterr().out


def test_json_and_jsonl_rows(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Query.s", VALID_SOURCE)

    assert main(["query", str(source), "--what", "symbols", "--json"]) == ExitCode.OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "sattline.v1.query"
    assert payload["file"] == str(source)
    assert any(row["name"] == "Init" and row["kind"] == "symbols" for row in payload["rows"])

    assert main(["query", str(source), "--what", "symbols", "--jsonl"]) == ExitCode.OK
    lines = capsys.readouterr().out.splitlines()
    assert lines and json.loads(lines[0])["kind"] == "symbols"


def test_no_match_is_a_finding_exit(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Query.s", VALID_SOURCE)

    assert main(["query", str(source), "--what", "references", "--name", "Nowhere"]) == ExitCode.FINDINGS
    assert capsys.readouterr().out == ""


def test_query_on_a_broken_source_reports_the_parse_error(tmp_path, capsys) -> None:
    source = write_source(tmp_path, "Broken.s", PARSE_ERROR_SOURCE)

    assert main(["query", str(source), "--what", "symbols"]) == ExitCode.FINDINGS
    assert "unexpected end of file" in capsys.readouterr().out


def test_companions_and_bad_limits_are_refused(tmp_path, capsys) -> None:
    companion = tmp_path / "M.y"
    companion.write_text("", encoding="utf-8")
    assert main(["query", str(companion)]) == ExitCode.USAGE
    assert "graphics companion" in capsys.readouterr().err

    source = write_source(tmp_path, "Query.s", VALID_SOURCE)
    assert main(["query", str(source), "--limit", "0"]) == ExitCode.USAGE
    assert "must be 1 or greater" in capsys.readouterr().err

    assert main(["query", str(source), "--limit", "lots"]) == ExitCode.USAGE
    assert "expected an integer" in capsys.readouterr().err
