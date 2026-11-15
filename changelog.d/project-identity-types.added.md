- **Dependency cycles follow resolved artifacts.** The planner pushes the
  resolved body identity on its active stack instead of the folded name, so two
  names for one file (a symlink alias, for example) are a cycle even though no
  name repeats, and two units that merely share a spelling are not. The
  diagnostic still reports the logical names that formed the loop, folded.
- **Project identities are named.** `UnitIdentity` (language identity, CP1252
  `fold_identifier`) and `ArtifactIdentity` (filesystem identity, resolved path
  compared with `os.path.normcase`) are exported from `sattline_parser.project`
  so a consumer can apply the same rule as the loader. The project view keeps
  its `str.casefold` registry keys, documented alongside the other two.
