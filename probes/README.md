# Real-parser probe tree

Every entry is a **program/library unit**: a `<name>.x` code file
with a `<name>.y` graphics file and a `<name>.z` dependency list
shipped in the same folder. The real tool needs all three before it
will parse a unit. The whole set is **flat** — one directory, no
subfolders — and all unit names are letters only.

Point the real SattLine GUI's check at this whole `probes/`
directory (it supports batch checking of multiple files in one
run). Then fill `TRANSCRIPT.md`: one row per unit — `real status`
is Accept or Reject; `message` is the verbatim diagnostic text or
message id the GUI shows. Save the filled file and hand it back;
`analyze.py` converts it into the committed snapshot.

`real status` must be a single canonical token (`accept`, `reject`,
`crash`, `stall`, or `---` for untested) because the analyzer parses
that cell. Put anything free-form in `message`, and record what **our**
parser did with the same file there too — prefix it with `ours accepts`
or `ours rejects` so `analyze.py` can tell "we also reject this" (fine)
apart from "the real tool rejects it and we happily accept it" (a real
grammar gap). That split shows up as the `gap` field in the snapshot.

- `probes.k` — the project file: 165 program/library units plus one
  window per program, all with `Directory "probes"`.
- `NAME_MAP.tsv` — old tiered path → current flat unit name.
- `TRANSCRIPT.md` — one row per unit (`id | area | tier | file | kind |
  expected | real status | message`).
- `MANIFEST.yaml` — machine-readable rule/probe list.

## ⚠ Known crashers / stalls — open alone

These units take the real SattLine GUI down or wedge it, so they are **never**
safe to batch: a crash kills the run and loses every other result collected in
that session. Open them last, one at a time, after saving your work. The
transcript records them as `crash` (or `stall` for the last one).

| unit | real outcome | ours |
| --- | --- | --- |
| `BadEncodingStress.x` | crashes on open | rejects (`SEMICOLON` expected at line 14) |
| `BadMalformed.x` | crashes on open | rejects (line 1, expected `STRING`) |
| `BadModCodeWithMod.x` | crashes on open | rejects (line 13, bare `ModuleCode`) |
| `BadNotSattLine.x` | crashes on open | rejects (line 1, plain text) |
| `BadOversizeInput.x` | **stalls, never loads** (needs a manual kill) | rejects (line 51, `Real_Value`) |
| `EdgeFrameModInvoc.x` | **crashes on open** (2026-10-01) — a frame-style module invocation; no diagnostic, no dialog | accepts clean |
| `HighByteInvalid.x` | unknown — byte `0x81` is undefined in cp1252 | `UnicodeDecodeError` |

`BadMalformed.x` and `BadNotSattLine.x` have no header line at all, and
`BadModCodeWithMod.x` is a bare `ModuleCode` with no `ModuleDef`; a
missing-header or missing-`ModuleDef` file kills the IDE instead of producing a
diagnostic.

`BadEncodingStress.x` **crashes the real SattLine GUI when it is
opened** (no diagnostic, no dialog). Despite the name it is **not** an encoding
probe — the file is pure ASCII. The crash comes from its placeholder header
lines (`"SyntaxVersion"`, `"OriginalFileDate"`, `"ProgramDate"` instead of a
real `"Syntax version …, date: … N"` line) plus a truncated expression
(`Var1 = Var2 +`).

`HighByteInvalid.x` is a second "open alone" candidate: its byte `0x81` is
undefined in Windows-1252, so the real tool's behavior on it is unknown.

## Encoding probes (raw bytes, no corpus fixtures)

Source files must be **Windows-1252** — the only encoding the real
parser accepts. These two probes carry the bytes for real:

| unit | bytes | ours | real |
| --- | --- | --- | --- |
| `HighByteValid.x` | `0x92`, `0xE4` in a comment (defined in cp1252) | parses + validates clean | expect accept |
| `HighByteInvalid.x` | `0x81` in a comment (undefined in cp1252) | `UnicodeDecodeError` — no utf-8/latin-1 fallback | unknown, open alone |

## Defective probe templates — do not report these as findings

Four units carry a construct the real tool rejects **and** that is not
valid SattLine, so a rejection says nothing about the rule under test.
They are recorded in `TRANSCRIPT.md` as `DEFECTIVE TEMPLATE` notes.

| unit | defect | fix |
| --- | --- | --- |
| `LoopA.x`, `LoopB.x`, `AuxLib.x` | instance header uses the inline form `) : MODULEDEFINITION DateCode_ N`; the tool requires a **type symbol**, `) : TypeName;` (`AliasSym Expected`) | reference the declared type name instead of restating `MODULEDEFINITION` |
| `Prog.x`, `ProgBadDep.x` | the submodule instance sits inside `LOCALVARIABLES` instead of the submodule list | move the invocation above `LOCALVARIABLES`, as `CtrlAcyc.x` does |

Ours rejects all of them too, but for a different reason and without the
type-symbol check, so do not treat our behavior as agreement.

## Error-number glossary

Reading raw GUI messages is faster with these:

| message | meaning |
| --- | --- |
| `Error 32` | sequence body / branch scope rejected |
| `Error 33` | sequence step header (step number or order) |
| `Error 76` | illegal identifier character, or a reserved word used as a name |
| `AliasSym Expected` | a type/symbol was required where a literal appeared |
| `DefineSym Expected` | a `:=` / definition was required |
| `EndLoopSeqSym Expected` | the sequence had to be closed here |

Confirmed 2026-10-01 from `EdgeSeqPar`, `ValidComprSeqBasic`, `EdgeUnicodeIdents`,
`ValidGraphObjB`, and `ProgBadDep` respectively.

Two more message shapes worth recognizing, both 2026-10-01:

| message | meaning |
| --- | --- |
| `Only integer and real allowed for this operator <expr>` | an operand of a comparison or arithmetic operator is not numeric — fires for `boolean` **and** for `duration`/`time` |
| `The expression is of an invalid type <expr>` | an expression sits where a literal is required, e.g. a `ClippingBounds` corner |
| `<name> is not used. Should it be removed?` | an interactive cleanup **question**, not an error — the file still compiles and runs |
