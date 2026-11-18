# pyright: reportMissingParameterType=false, reportPrivateUsage=false, reportUnknownArgumentType=false, reportUnknownParameterType=false
import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from sattline_parser.api import parse_source_file, parse_source_text
from sattline_parser.models.ast_model import (
    BasePicture,
    DataType,
    Equation,
    FloatLiteral,
    FrameModule,
    IntLiteral,
    MappingSource,
    ModuleCode,
    ModuleDef,
    ModuleTypeDef,
    ModuleTypeInstance,
    ParameterMapping,
    ScalarDatatype,
    Sequence,
    SingleModule,
    SourceSpan,
    Variable,
)
from sattline_parser.models.clauses import ClippingClause
from sattline_parser.models.expressions import Assignment, VarRef

from ._parser_core_test_support import _module_header


def test_ast_model_helpers_cover_reduce_usage_and_string_formats(monkeypatch: pytest.MonkeyPatch):
    span = SourceSpan(start=2, end=3, line=1, column=3)
    int_lit = IntLiteral(7, span)
    float_lit = FloatLiteral(2.5, span)

    assert span.__reduce__() == (SourceSpan, (2, 3, 1, 3))
    assert int_lit.__reduce__() == (IntLiteral, (7, span, False))
    assert float_lit.__reduce__() == (FloatLiteral, (2.5, span, False))
    assert ScalarDatatype.from_any(ScalarDatatype.BOOLEAN) is ScalarDatatype.BOOLEAN
    assert Variable(name="Flag", datatype="BOOLEAN").datatype_text == "boolean"
    assert Variable(name="RecordValue", datatype="CustomRecord").datatype_text == "CustomRecord"
    assert str(Variable(name="Count", datatype="integer", init_value=0)).startswith("Name: 'Count'")

    with pytest.raises(TypeError, match="Expected ScalarDatatype or str"):
        ScalarDatatype.from_any(cast(Any, 123))
    with pytest.raises(TypeError, match="Expected ScalarDatatype or str"):
        Variable(name="Broken", datatype=cast(Any, 123))

    def _raise_value_error(cls, value):
        raise ValueError("bad datatype")

    monkeypatch.setattr(ScalarDatatype, "from_any", classmethod(_raise_value_error))
    with pytest.raises(ValueError, match="bad datatype"):
        Variable(name="Exploded", datatype=cast(Any, object()))

    assert (
        str(
            ParameterMapping(
                target=VarRef("Target"),
                source_type=MappingSource.VARIABLE,
                is_duration=False,
                is_source_global=True,
            )
        )
        == "Target => GLOBAL"
    )
    assert (
        str(
            ParameterMapping(
                target=VarRef("Target"),
                source_type=MappingSource.VARIABLE,
                is_duration=False,
                is_source_global=True,
                source=VarRef("GlobalSrc"),
            )
        )
        == "Target => GLOBAL GlobalSrc"
    )
    assert (
        str(
            ParameterMapping(
                target=VarRef("Target"),
                source_type=MappingSource.VARIABLE,
                is_duration=False,
                source=VarRef("Source"),
                is_source_global=False,
            )
        )
        == "Target => Source"
    )
    assert (
        str(
            ParameterMapping(
                target=VarRef("Target"),
                source_type=MappingSource.VALUE,
                is_duration=False,
                source_literal=42,
                is_source_global=False,
            )
        )
        == "Target => 42"
    )
    assert (
        str(
            ParameterMapping(
                target=VarRef("Target"),
                source_type=MappingSource.VALUE,
                is_duration=False,
                is_source_global=False,
            )
        )
        == "Target => <None>"
    )

    sequence = Sequence(name="SeqA", type="sequence", position=(0.0, 0.0), size=(1.0, 1.0), code=[])
    equation = Equation(name="EqA", position=(1.0, 2.0), size=(3.0, 4.0), code=[])
    module_code = ModuleCode()
    rendered_module_code = ModuleCode(
        sequences=[sequence],
        equationblocks=[
            Equation(
                name="EqStmt",
                position=(1.0, 2.0),
                size=(3.0, 4.0),
                code=[Assignment(VarRef("Out"), IntLiteral(1))],
            )
        ],
    )
    empty_statement_module_code = ModuleCode(
        equationblocks=[
            Equation(
                name="EqEmpty",
                position=(5.0, 6.0),
                size=cast(Any, None),
                code=[],
            )
        ]
    )
    direct_statement_module_code = ModuleCode(
        equationblocks=[
            Equation(
                name="EqDirect",
                position=(7.0, 8.0),
                size=cast(Any, None),
                code=[Assignment(VarRef("Direct"), IntLiteral(2))],
            )
        ]
    )
    module_def = ModuleDef(clipping=ClippingClause(((0.0, 0.0), (1.0, 1.0))), zoomable=True)
    header = _module_header("Parent")
    child = ModuleTypeInstance(header=_module_header("Child"), moduletype_name="ChildType")

    assert "Sequence(name=SeqA" in str(sequence)
    assert "Equation(name=EqA" in str(equation)
    assert "No sequences" in str(module_code)
    assert "Sequence 'SeqA'" in str(rendered_module_code)
    assert "EquationBlock name='EqStmt'" in str(rendered_module_code)
    assert "Out = 1" in str(rendered_module_code)
    assert "EquationBlock name='EqEmpty'" in str(empty_statement_module_code)
    assert "Direct = 2" in str(direct_statement_module_code)
    assert "ClippingBounds" in str(module_def)
    assert "SingleModule{" in str(SingleModule(header=header, moduledef=module_def, modulecode=module_code))
    assert "FrameModule{" in str(FrameModule(header=header, moduledef=module_def, modulecode=module_code))
    assert "ModuleTypeInstance{" in str(child)
    assert "ModuleType{" in str(ModuleTypeDef(name="ChildType", modulecode=module_code, submodules=[child]))
    assert "BasePicture{" in str(BasePicture(header=header, moduledef=module_def, modulecode=module_code))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SingleModule(header=_module_header("Single")),
        lambda: FrameModule(header=_module_header("Frame")),
        lambda: ModuleTypeDef(name="Type"),
        lambda: BasePicture(header=_module_header("Base")),
    ],
)
def test_module_block_fields_are_plain_optional_fields(
    factory: Callable[[], SingleModule | FrameModule | ModuleTypeDef | BasePicture],
) -> None:
    module = factory()
    module_def = ModuleDef()
    module_code = ModuleCode()

    field_names = {dataclass_field.name for dataclass_field in dataclasses.fields(module)}
    assert "moduledef" in field_names
    assert "modulecode" in field_names
    assert "moduledefs" not in field_names
    assert "modulecodes" not in field_names

    assert module.moduledef is None
    assert module.modulecode is None

    module.moduledef = module_def
    module.modulecode = module_code
    assert module.moduledef is module_def
    assert module.modulecode is module_code


def test_datatype_string_formats_its_variables() -> None:
    datatype = DataType(
        name="Payload",
        description="desc",
        datecode=100,
        var_list=[Variable(name="FieldA", datatype="integer")],
        origin_file="Program.s",
        origin_lib="LibHA",
    )

    rendered = str(datatype)

    assert "Variables in datatype" in rendered
    assert "Payload" in rendered


_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"
_HEADER = '"SyntaxVersion"\n"OriginalFileDate"\n"ProgramDate"\n'
_BASE_HEAD = "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
_BASE_TAIL = "ModuleDef\nClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\nENDDEF (*BasePicture*);\n"


def test_record_without_a_description_stores_none_not_the_record_keyword() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "UnCompressedFullGrammar.s")

    record = next(datatype for datatype in picture.datatype_defs if datatype.name == "TestRecord2")

    assert record.description is None
    assert all(datatype.description is None or type(datatype.description) is str for datatype in picture.datatype_defs)


def test_record_with_a_description_stores_the_written_string() -> None:
    picture = parse_source_file(_CORPUS / "valid" / "UnCompressedFullGrammar.s")

    record = next(datatype for datatype in picture.datatype_defs if datatype.name == "TestRecord")

    assert record.description == '"Description of TestRecord"'


def test_frame_module_marker_does_not_leak_into_the_root_datecode() -> None:
    picture = parse_source_file(_CORPUS / "edge_cases" / "FrameModuleInvocation.s")

    assert picture.datecode == 1
    assert type(picture.datecode) is int


def test_frame_submodule_without_a_datecode_stores_none() -> None:
    picture = parse_source_text(
        _HEADER
        + _BASE_HEAD
        + (
            "SUBMODULES\n"
            "   FrameInst Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION (Frame_Module)\n"
            "   ModuleDef\n"
            "   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            "   ENDDEF (*FrameInst*);\n"
        )
        + _BASE_TAIL
    )

    frame = picture.submodules[0]

    assert isinstance(frame, FrameModule)
    assert frame.datecode is None


def test_variable_group_does_not_share_a_mutable_init_payload() -> None:
    picture = parse_source_text(
        _HEADER + _BASE_HEAD + ('LOCALVARIABLES\n   A, B: time := Time_Value "12:00:00";\n') + _BASE_TAIL
    )

    first, second = picture.localvariables
    assert first.init_value == second.init_value == {"Time_Value": "12:00:00"}
    assert first.init_value is not second.init_value

    cast(dict[str, str | None], first.init_value)["Time_Value"] = "01:00:00"
    assert second.init_value == {"Time_Value": "12:00:00"}
