# Cross-module project units (probes/proj/)

A miniature controller program + library closure, the real SattLine equivalent
of a project. Check this directory together with `rules/` and `tier0/` in the
same GUI session.

- `PumpLib`      defines `PumpType` (leaf moduletype).
- `AuxLib`       defines `AuxType` which instantiates `PumpType` (cross-lib).
- `UnusedLib`    defines `UnusedType`, never instantiated anywhere.
- `LoopA`/`LoopB`  each instantiate the other's moduletype AND list each other
  in their `.z` — a moduletype cycle plus a library-dependency cycle.
- `Prog`         program whose closure pulls in the LoopA/LoopB cycle.
- `ProgBadDep`   program referencing `PumpType` while its `.z` omits `PumpLib`
  (undeclared dependency used).

Expected: the individual libraries are valid (`accept`); `Prog` and
`ProgBadDep` should be `reject` if the real parser walks the dependency
closure. Record the actual outcomes in TRANSCRIPT.md.
