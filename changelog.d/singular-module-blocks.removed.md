- **Singular module block fields.** `SingleModule`, `FrameModule`,
  `ModuleTypeDef` and `BasePicture` no longer store `moduledef` and
  `modulecode`. The names remain as read-only properties returning the last
  entry of `moduledefs` / `modulecodes`, so reading them still works and the two
  views cannot disagree. Construction through the singular keyword arguments,
  assignment to the properties, and the corresponding `moduledef` /
  `modulecode` keys in `sattline parse --tree` output are removed; use the
  block lists instead.
