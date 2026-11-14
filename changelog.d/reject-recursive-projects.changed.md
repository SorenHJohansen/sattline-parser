- **Recursive projects are rejected.** A `.l`/`.z` dependency chain that
  returns to a program already loading, and a module type that instantiates
  itself directly or through other module types, now raise
  `DependencyCycleError` and `ModuleTypeCycleError` from
  `SattLineProject.load`. Both are structural errors, so `strict=False` and
  `validate=NONE` cannot bypass them. `LoadDiagnosticKind.DEPENDENCY_CYCLE` is
  removed; read the error's `cycle` path instead. `SattLineProject.cycles()`
  remains for a directly built graph, where the loader has not already raised.
