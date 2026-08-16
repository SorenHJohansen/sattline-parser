# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportPrivateUsage=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from ._parser_core_test_support import *


def test_ast_model_helpers_cover_reduce_usage_and_string_formats(monkeypatch: pytest.MonkeyPatch):  # noqa: PLR0915
    span = SourceSpan(start=2, end=3, line=1, column=3)
    int_lit = IntLiteral(7, span)
    float_lit = FloatLiteral(2.5, span)

    assert span.__reduce__() == (SourceSpan, (2, 3, 1, 3))
    assert int_lit.__reduce__() == (IntLiteral, (7, span))
    assert float_lit.__reduce__() == (FloatLiteral, (2.5, span))
    assert Simple_DataType.from_any(Simple_DataType.BOOLEAN) is Simple_DataType.BOOLEAN
    assert Variable(name="Flag", datatype="BOOLEAN").datatype_text == "boolean"
    assert Variable(name="RecordValue", datatype="CustomRecord").datatype_text == "CustomRecord"
    assert str(Variable(name="Count", datatype="integer", init_value=0)).startswith("Name: 'Count'")

    with pytest.raises(TypeError, match="Expected Simple_DataType or str"):
        Simple_DataType.from_any(cast(Any, 123))
    with pytest.raises(TypeError, match="Expected Simple_DataType or str"):
        Variable(name="Broken", datatype=cast(Any, 123))

    def _raise_value_error(cls, value):
        raise ValueError("bad datatype")

    monkeypatch.setattr(Simple_DataType, "from_any", classmethod(_raise_value_error))
    with pytest.raises(ValueError, match="bad datatype"):
        Variable(name="Exploded", datatype=cast(Any, object()))

    usage_path = ["BasePicture"]
    datatype = DataType(
        name="Payload",
        description="desc",
        datecode=100,
        var_list=[Variable(name="FieldA", datatype="integer")],
        origin_file="Program.s",
        origin_lib="LibHA",
    )
    datatype.mark_read(usage_path)
    datatype.mark_written(usage_path)
    usage_path.append("Mutated")

    assert datatype.read is True
    assert datatype.written is True
    assert datatype.usage_locations == [(["BasePicture"], "read"), (["BasePicture"], "write")]
    assert "Variables in datatype" in str(datatype)

    assert (
        str(
            ParameterMapping(
                target=VarRef("Target"),
                source_type=parser_const.TREE_TAG_VARIABLE_NAME,
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
                source_type=parser_const.TREE_TAG_VARIABLE_NAME,
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
                source_type=parser_const.KEY_VALUE,
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
                source_type=parser_const.KEY_VALUE,
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
        equations=[
            Equation(
                name="EqStmt",
                position=(1.0, 2.0),
                size=(3.0, 4.0),
                code=[Assignment(VarRef("Out"), IntLiteral(1))],
            )
        ],
    )
    empty_statement_module_code = ModuleCode(
        equations=[
            Equation(
                name="EqEmpty",
                position=(5.0, 6.0),
                size=cast(Any, None),
                code=[],
            )
        ]
    )
    direct_statement_module_code = ModuleCode(
        equations=[
            Equation(
                name="EqDirect",
                position=(7.0, 8.0),
                size=cast(Any, None),
                code=[Assignment(VarRef("Direct"), IntLiteral(2))],
            )
        ]
    )
    module_def = ModuleDef(clipping_bounds=((0.0, 0.0), (1.0, 1.0)), zoomable=True)
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
    assert "ModulType{" in str(ModuleTypeDef(name="ChildType", modulecode=module_code, submodules=[child]))
    assert "BasePicture{" in str(BasePicture(header=header, moduledef=module_def, modulecode=module_code))
