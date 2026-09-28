# Real-parser probe tree

Every entry is a **program/library unit**: a `<name>.s` code file
with a `<name>.y` graphics file and a `<name>.z` dependency list
shipped in the same folder. The real tool needs all three before it
will parse a unit.

Point the real SattLine GUI's check at this whole `probes/`
directory (it supports batch checking of multiple files in one
run). Then fill `TRANSCRIPT.md`: one row per unit — `real status`
is Accept or Reject; `message` is the verbatim diagnostic text or
message id the GUI shows. Save the filled file and hand it back;
`analyze.py` converts it into the committed snapshot.

- `tier0/`  — existing corpus inventory sweep (accept/reject baseline).
  `t0-invalid-*` files (Malformed/NotSattLine/EncodingStress) are
  expected rejects.
- `rules/`  — the new frontier probes; `expected` is a hypothesis,
  the real parser decides. C-201/C-202 differ only in the `.y`.
- `proj/`   — a miniature program + library closure.
