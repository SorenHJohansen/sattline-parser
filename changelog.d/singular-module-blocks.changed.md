- **Module layout blocks are singular again.** `SingleModule`, `FrameModule`,
  `ModuleTypeDef`, and `BasePicture` store `moduledef` and `modulecode` as
  optional fields. The `moduledefs` and `modulecodes` lists are removed. The
  grammar allows one `ModuleDef` and one optional `ModuleCode` per module body,
  so the lists could never hold more than one entry, and the property views over
  them implied a legacy multi-block shape the language does not have.
  `sattline parse --tree` emits `moduledef` and `modulecode` instead of the two
  lists, the transformer rejects a second block in one body instead of
  overwriting the first, and `FILE_AST_CACHE_VERSION` is `12`, so older AST
  cache entries are discarded.
