- **Artifact families no longer mix.** The resolved code body's extension now
  decides the artifact family for the whole unit: a `.s` body pairs only with
  `.l` dependencies, `.g` graphics, and `.p` distribution, and an `.x` body only
  with `.z`, `.y`, and `.q`. Previously the dependency sidecar followed the load
  mode alone, so draft mode could pair a `.s` body with a `.z` sidecar and an
  `.x` body with a `.l` sidecar, and draft bodies fell back to the official
  `.y` and `.q` companions. A sidecar that sits beside the body but in the other
  family is reported as `sidecar-family-mismatch` and is not paired. Code-body
  selection is unchanged: draft mode still prefers `.s` and falls back to `.x`.
