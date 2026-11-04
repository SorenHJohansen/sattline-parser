- **Annotation-tail traversal.** The public walker now descends into
  `GraphObject.properties`, `InteractObject.properties`, and
  `ModuleDef.properties`, and emits the typed clause and tail payloads
  (`EnableClause`, `ColourSpec`, `TailedClause`, `AssignClause`, `FlagClause`,
  `ProcedureCall`, `PickButton`, `ScaleSelector`, `VarTail`, `LitStringTail`).
  Property keys are visited in a documented order, and a tail shared with the
  flat `properties["tails"]` view is emitted once through its owning clause.
- **Annotation-tail validation.** Expression tails in headers, graphics,
  interact objects, and module layout are checked for undefined variables
  (`SL-V019`). An `Enable_` expression tail must be boolean (`SL-V030`), and
  `ModuleDef` coordinate tails keep `SL-V032`. Bound `InVar_`/`OutVar_` names
  stay undiagnosed.
- **Annotation-tail references.** `sattline query --what references` reports
  variable uses in header and object annotation tails. Bound tails appear with
  detail `unresolved`; text-object `VarName` and `IntObjPickButton` references
  are reported too.
