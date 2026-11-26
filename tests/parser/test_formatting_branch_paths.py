# pyright: reportPrivateUsage=false
"""Branch coverage for formatter paths that rendered sources do not reach."""

from __future__ import annotations

from sattline_parser.ast import (
    ModuleCode,
    ModuleHeader,
    ModuleInViewClause,
    ModuleTypeDef,
    SingleModule,
)
from sattline_parser.formatting import formatter
from sattline_parser.formatting import source as fmt


def test_format_list_without_alignment_puts_each_item_on_its_own_line() -> None:
    assert formatter.format_list(["A", "B"], align_variables=False) == "[\n    A\n    B]"


def test_a_module_type_without_a_module_definition_still_emits_its_code() -> None:
    printer = fmt._Printer()
    moduletype = ModuleTypeDef(name="Child", moduledef=None, modulecode=ModuleCode())

    fmt._emit_moduletype(printer, moduletype, 0)

    text = printer.render()
    assert "Child = MODULEDEFINITION" in text
    assert "ModuleCode" in text
    assert "ENDDEF" in text


def test_a_submodule_without_a_module_definition_still_emits_its_code() -> None:
    printer = fmt._Printer()
    submodule = SingleModule(
        header=ModuleHeader(name="Sub", invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0)),
        moduledef=None,
        modulecode=ModuleCode(),
    )

    fmt._emit_submodule(printer, submodule, 0)

    text = printer.render()
    assert "Sub Invocation" in text
    assert "ModuleCode" in text
    assert "ENDDEF" in text


def test_a_module_in_view_clause_without_a_tail_is_the_value_alone() -> None:
    assert fmt._module_in_view_text(ModuleInViewClause(in_view=False)) == "Module_In_View = False"
