from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ast_model import (
        BasePicture,
        CodeComment,
        CodeItem,
        DataType,
        Equation,
        FrameModule,
        GraphObject,
        InteractObject,
        ModuleCode,
        ModuleTypeDef,
        ModuleTypeInstance,
        ParameterMapping,
        Sequence,
        SFCBodyItem,
        SingleModule,
        Variable,
    )

#: Values a variable init or parameter-mapping source can hold: a literal, a
#: boolean, or a parsed ``time_value`` dictionary.
type InitValue = bool | int | float | str | dict[str, str | None]


def variable_list() -> list[Variable]:
    return []


def graph_object_list() -> list[GraphObject]:
    return []


def interact_object_list() -> list[InteractObject]:
    return []


def code_comment_list() -> list[CodeComment]:
    return []


def code_item_list() -> list[CodeItem]:
    return []


def sfc_body_list() -> list[SFCBodyItem]:
    return []


def submodule_list() -> list[SingleModule | FrameModule | ModuleTypeInstance]:
    return []


def parameter_mapping_list() -> list[ParameterMapping]:
    return []


def datatype_def_list() -> list[DataType]:
    return []


def moduletype_def_list() -> list[ModuleTypeDef]:
    return []


def render_datatype(datatype: DataType) -> str:
    from ..formatting.formatter import format_list  # noqa: PLC0415

    lines = [
        f"Name       : {datatype.name!r}",
        f"Description: {datatype.description!r}",
        f"Datecode   : {datatype.datecode!r}",
        f"OriginFile : {datatype.origin_file!r}",
        f"OriginLib  : {datatype.origin_lib!r}",
        f"Variables in datatype   : {format_list(datatype.var_list)}",
    ]
    return "Datatype{\n" + textwrap.indent("\n".join(lines), "    ") + "}"


def render_sequence(sequence: Sequence) -> str:
    from ..formatting.formatter import format_list  # noqa: PLC0415

    return (
        f"Sequence(name={sequence.name}, pos={sequence.position}, "
        f"type={sequence.type}, control={sequence.seqcontrol}, timer={sequence.seqtimer},\n"
        f"    code={format_list(sequence.code)})"
    )


def render_equation(equation: Equation) -> str:
    from ..formatting.formatter import format_list  # noqa: PLC0415

    return f"Equation(name={equation.name}, pos={equation.position},\n    code={format_list(equation.code)})"


def render_module_code(module_code: ModuleCode) -> str:
    # Imported at call time: ``formatting`` imports the model expression nodes,
    # so a module-level import here would make the model and formatting layers
    # mutually dependent. These renderers only run from ``__str__``.
    from ..formatting.formatter import format_expr, format_seq_nodes  # noqa: PLC0415

    seq_lines: list[str] = []
    if module_code.sequences:
        for sequence in module_code.sequences:
            size_str = f" with size {sequence.size}" if getattr(sequence, "size", None) is not None else ""
            seq_lines.append(
                f"Sequence {sequence.name!r} at {sequence.position}{size_str} (type={sequence.type})\n"
                f"    Code:\n" + textwrap.indent(format_seq_nodes(sequence.code), "        ")
            )
    else:
        seq_lines.append("No sequences")

    eq_lines: list[str] = []
    if module_code.equationblocks:
        for equation in module_code.equationblocks:
            pretty_code = [format_expr(statement) for statement in equation.code]
            size_str = f" with size {equation.size}" if getattr(equation, "size", None) is not None else ""
            eq_lines.append(
                f"EquationBlock name={equation.name!r} at {equation.position}{size_str}\n"
                f"    Code:\n" + textwrap.indent("\n".join(pretty_code), "        ")
            )

    return (
        "ModuleCode{\n"
        + textwrap.indent("Sequences:\n" + textwrap.indent("\n\n".join(seq_lines), "    "), "    ")
        + "\n\n"
        + textwrap.indent("Equation blocks:\n" + textwrap.indent("\n\n".join(eq_lines), "    "), "    ")
        + "\n}"
    )


def render_single_module(module: SingleModule) -> str:
    from ..formatting.formatter import format_list, format_optional  # noqa: PLC0415

    lines = [
        f"Name            : {module.header.name!r}",
        f"Enable          : {module.header.enable}",
        f"Invoke_coord    : {module.header.invoke_coord!r}",
        f"Datecode        : {module.datecode!r}",
        f"Moduleparameters: {format_list(module.moduleparameters)}",
        f"Localvariables  : {format_list(module.localvariables)}",
        f"Submodules      : {format_list(module.submodules)}",
        f"ModuleDef       : {format_optional(module.moduledef)}",
        f"ModuleCode      : {format_optional(module.modulecode)}",
        f"ParameterMappings: {format_list(module.parametermappings)}",
    ]
    return "SingleModule{\n" + textwrap.indent("\n".join(lines), "    ") + "}"


def render_frame_module(module: FrameModule) -> str:
    from ..formatting.formatter import format_list, format_optional  # noqa: PLC0415

    lines = [
        f"Name         : {module.header.name!r}",
        f"Enable       : {module.header.enable}",
        f"Invoke_coord : {module.header.invoke_coord!r}",
        f"Datecode     : {module.datecode!r}",
        f"Submodules   : {format_list(module.submodules)}",
        f"ModuleDef    : {format_optional(module.moduledef)}",
        f"ModuleCode   : {format_optional(module.modulecode)}",
    ]
    return "FrameModule{\n" + textwrap.indent("\n".join(lines), "    ") + "}"


def render_moduletype_instance(instance: ModuleTypeInstance) -> str:
    from ..formatting.formatter import format_list  # noqa: PLC0415

    lines = [
        f"Name             : {instance.header.name!r}",
        f"Enable           : {instance.header.enable}",
        f"Enable_tail      : {instance.header.enable_tail}",
        f"Invoke_coord     : {instance.header.invoke_coord!r}",
        f"ModuleTypeName   : {instance.moduletype_name!r}",
        f"ParameterMappings: {format_list(instance.parametermappings)}",
    ]
    return "ModuleTypeInstance{\n" + textwrap.indent("\n".join(lines), "    ") + "}"


def render_moduletype_def(moduletype: ModuleTypeDef) -> str:
    from ..formatting.formatter import format_list, format_optional  # noqa: PLC0415

    lines = [
        f"Name            : {moduletype.name!r}",
        f"Datecode        : {moduletype.datecode!r}",
        f"OriginFile      : {moduletype.origin_file!r}",
        f"OriginLib       : {moduletype.origin_lib!r}",
        f"Moduleparameters: {format_list(moduletype.moduleparameters)}",
        f"Localvariables  : {format_list(moduletype.localvariables)}",
        f"Submodules      : {format_list(moduletype.submodules)}",
        f"ModuleDef       : {format_optional(moduletype.moduledef)}",
        f"ModuleCode      : {format_optional(moduletype.modulecode)}",
    ]
    return "ModuleType{\n" + textwrap.indent("\n".join(lines), "    ") + "}"


def render_base_picture(base_picture: BasePicture) -> str:
    from ..formatting.formatter import format_list, format_optional  # noqa: PLC0415

    lines = [
        f"Name: {base_picture.name!r}\n"
        f"Position: {base_picture.position!r}\n\n"
        f"TYPEDEFINITIONS (Records): {format_list(base_picture.datatype_defs)}\n\n"
        f"TYPEDEFINITIONS (Modules): {format_list(base_picture.moduletype_defs)}\n"
        f"Moduleparameters: {format_list(base_picture.moduleparameters)}\n"
        f"Localvariables: {format_list(base_picture.localvariables)}\n\n"
        f"Submodules: {format_list(base_picture.submodules)}\n\n"
        f"ModuleDef: {format_optional(base_picture.moduledef)}\n\n"
        f"ModuleCode: {format_optional(base_picture.modulecode)}\n\n"
    ]
    return "BasePicture{\n" + textwrap.indent("\n  ".join(lines), "    ") + "}"
