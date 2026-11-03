- **Typed tail and clause nodes.** Coordinate, header, and property tails are
  modelled as frozen dataclasses instead of bare strings, dicts, and Lark
  trees: `VarTail(direction, value)` for `InVar_`/`OutVar_` bindings,
  `LitStringTail` for quoted symbols, and typed clause payloads such as
  `EnableClause`, `AssignClause`, `TailedClause`, `ColourSpec`,
  `ProcedureCall`, and `ModuleArguments`. `ModuleHeader.enable_tail`,
  `ModuleHeader.invoke_coord_tails`, and `ModuleDef.clipping_tails` now hold
  these nodes, and the graph, interact, and module-definition property maps are
  `TypedDict` definitions. Consumers that compared tails to strings or read
  `properties` as an untyped dict need updating.
