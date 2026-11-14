- **Companions cannot be resolved through the ordered roots.**
  `ProjectLookup.find` now raises `ValueError` for `ArtifactKind.GRAPHICS` and
  `ArtifactKind.DISTRIBUTION`. A graphics or distribution companion is anchored
  to the body that owns it, so a root-ordered search could return another unit's
  companion and pollute the source index. Companions are reached only through
  `resolve_graphics_companion_path` and `resolve_distribution_companion_path`.
  Code bodies and dependency sidecars are unaffected.
