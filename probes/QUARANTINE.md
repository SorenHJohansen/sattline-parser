# Quarantined probes

Six programs crash or hang the real SattLine tool. A further two became
crashers once their encoding was repaired. All eight are **excluded from
`probes-safe.k` and `probes-batch.k`** and must not be added back into a GUI
test batch.

| Program | Real result | Recorded at |
| --- | --- | --- |
| `EdgeFrameModInvoc` | crash | `TRANSCRIPT.md` |
| `BadEncodingStress` | crash | `TRANSCRIPT.md` |
| `BadMalformed` | crash | `TRANSCRIPT.md` |
| `BadModCodeWithMod` | crash | `TRANSCRIPT.md` |
| `BadNotSattLine` | crash | `TRANSCRIPT.md` |
| `BadOversizeInput` | stall | `TRANSCRIPT.md` |
| `ValidUnComprFull` | crash | `TRANSCRIPT.md` |
| `ValidComprFull` | crash | `TRANSCRIPT.md` |

## Why `ValidUnComprFull` / `ValidComprFull` are on this list

These two are a special case, and the reason is worth recording.

They originally produced a plain parse error (`Error 76`), which is harmless.
The cause was that the **probe files had been saved as UTF-8 instead of
cp1252**: they contained byte `0x86`, which is undefined in Windows-1252, and
read as cp1252 their `formål` decoded to `formÃ¥l` — a `¥` currency symbol
where a letter was required. Our own decoder reproduced the tool's failure at
exactly the same line, which is how the encoding defect was identified.

After re-encoding both files to cp1252 the tool could finally read them, and
then **crashed**. So repairing the encoding did not fix these probes — it
revealed that the tool dies on something inside the ~50 KB of full-grammar
source. The likely candidate is the graph-object enable tail
`Enable_ = True : ( NOT EnableVar)`, which is why `EdgePropParenTail.x` exists
and is worth running early. That is a hypothesis, not a confirmed cause.

## Why the `.x` files are still on disk

They are evidence. Each one documents a real failure mode of the host tool, and
that evidence is already reflected in the transcript. Deleting the files would
throw away the only record that these inputs kill SattLine rather than merely
being rejected by it — a meaningfully different result from a parse error.

## Which project file to use

- **`probes.k`** — 173 programs, includes all eight. Only open this if you
  specifically want to re-observe a crash, and expect the tool to die.
- **`probes-safe.k`** — 165 programs, all eight removed along with their
  `Screen` window placements. Everything that has ever been run.
- **`probes-batch.k`** — 71 programs, hand-authored. **Only the files that have
  never been run**, i.e. the current test batch. This is the one to open.

`probes-safe.k` is a pure deletion of eight `ProgramUnits` entries and eight
`Screen` `Window` entries relative to `probes.k` — no content was rewritten,
and each section's closing paren was left intact.

`probes-batch.k` was written from scratch. Its 55 `Screen` windows reuse the
original coordinates exactly; the remaining 16 units have no window, matching
your instruction not to give them one.

## A pre-existing quirk, for the record

`probes.k` contains one **extra `)` in its `Screen` section** — cumulative
nesting depth reaches `-1` before the `ColorTable` header. This is in the
original file, not something introduced here, and SattLine opens it fine.
`probes-batch.k` returns to `0` instead, i.e. it is properly balanced. If the
batch project fails to open, this is the first thing to suspect: try appending
one `)` to the end of the `Screen` section to reproduce the original's shape.

## If you need to re-test one

Open `probes.k`, run only the single unit you care about, and close the tool
before opening anything else. Do not batch them.