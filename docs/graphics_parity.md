# Graphics companion correlation — status and open work

Research note, started 2026-10-27. Based on the recovered native behaviour for
build `3.1-2 (3.1.2000.18)` plus a sweep of the 743 companion files under
`~/Projects/Libs`.

## What is implemented

* **Positional binding in declaration order.** `graphics_parsing` collects the
  source `CompositeObject` markers in the order the native reader reaches them
  and pairs marker *n* with record *n* — the native rule (`00665fc0` consumes the
  next record at each marker; there is no name lookup). The order is
  **children-before-own**: module type definitions (recursively, declaration
  order), then inline `SUBMODULES` definitions (recursively, declaration order),
  then the enclosing module's own `ModuleDef`. `005ccaa0` is the controlling
  token reader (`005dc3f0` recurses into module types, `005cc700` into inline
  submodule definitions) and it calls `00663540` for its own `ModuleDef` only
  after its declaration loop has finished; the normal writer `005cf580` emits
  the same order (`005cfc60` types, `005cfa40`/`005cf250` submodules,
  `00661fd0` own graphics). An invocation that *references* an existing named
  module type takes the `005cc700` reference branch and does not reread that
  type. Markers without records and records without markers are reported as
  `GraphicsMessage` values; those diagnostics are parser-owned — no native
  severity was recovered for either case.
* **Record ordinals and marker spans.** `GraphicsCompositeRecord.ordinal` carries
  the companion position; `GraphicsCompositeBinding` exposes the pair and the
  marker's source span (`GraphObject.span`, populated from the `graph_object`
  rule), so a consumer can point at the construct.
* **Family set.** `{1, 2, 4, 5}` matches the recovered handlers
  (`004e5410`, `0041b7f0`, `00402050`, `004ac980`), with family `5` subtype `2`
  recognised as PictureDisplay and a shape flag as its trailer.
* **Default path payloads.** Every subtype-2 record also carries the inline
  default payload — the path used when no index matches, and the real asset path
  for most records. `GraphicsRecord.default_entry` keeps it, and
  `GraphicsPictureDisplayRecord.default_path_row` exposes it separately while it
  stays in `path_rows` (file order, after the indexed entries) so consumers that
  validate literal asset paths keep seeing it. Empty literals are the writer's
  "no path" form and produce no row.
* **One cursor per source/companion pair.** `00584aa0` opens the companion
  (`0043ab10`) before the root `005cc700` call and recursive reads never reopen
  or rewind it, so the first record belongs to the first marker reached anywhere
  in the recursive parse — possibly inside a module type. Closing (`0043a510`)
  does not check that every record was consumed.
* **Structural record readers.** `project/graphics_records.py` consumes each
  record field by field instead of scanning lines, so a record boundary follows
  from the family grammar and never from blank lines. It implements the
  transcription further down this note: the primitives (`I`, `H`, `F`, `D`,
  `END`, `MARK`, `MORE`, `WORD`, `WORD2`, `LINE`, `COUNTED`, plus the one-byte
  separator before a picture-display payload), the binding reader `004a72d0`
  (modern and legacy layouts, baseline kinds `B1`–`B4`/`B11`/`B12`), the family 1
  payload readers `004dcc30`/`004f1950`/`004d1fc0`, the family 2 readers
  `00417930` and the 2/3/4 payloads, family 4, family 5 subtypes 1 (`007343e0`)
  and 2 (`00733520`, older `007333c0`), and the indexed-text loop `00734690`.
* **Version-dependent fields.** The `" Syntax version x.y` header selects every
  branch: the picture-shape byte (`major > 1 and minor > 18`), the pre-qualifier
  binding layout (`major == 0 and minor < 107`), the older picture-display layout
  (`major == 0 and minor <= 96`), the family 1 subrecord 2 trailing block
  (`0062e800` sets `DAT_00845343` before 2.7) and the family 1 subrecord 3
  trailing block (`DAT_0084538e` before 2.18). Both global flags are
  "before", so the trailing blocks are read from that version *on*. The
  picture-display inline default uses `WORD2()` when `major == 0 and minor <
  100` and `LINE()` otherwise. A file without a header is read as the modern
  layout.
* **Version-dependent layout.** The `" Syntax version x.y` header of the
  companion selects the branches: `major > 1 and minor > 18` reads the separate
  picture-shape byte, `major == 0 and minor < 107` is the pre-qualifier binding
  layout, `major == 0 and minor <= 96` is the older picture-display layout. A
  file without a header is read as the modern layout.

## Verification (743 companion files, all four project trees)

| Measurement | Result |
| --- | --- |
| Files read to completion | 743 (all) |
| Records read | 12 924 (12 863 family 5, 40 family 1, 16 family 4, 5 family 2) |
| PictureDisplay records / path rows | 12 210 / 13 863 |
| Files that stop at an unrecovered sub-reader | 0 |
| Record structure that changes when blank lines are removed | 93 files, every one of them a subtype-1 text table storing an *empty* title/default line |
| Units whose marker count equals the companion record count | 209 / 209 (size-capped sample with a companion) |

The blank-line row is the invariant this work targeted. A blank line is no
longer formatting: outside a `LINE()` field it is skipped like any other
whitespace, so removing it cannot move a boundary. The 93 remaining differences
are data — a subtype-1 record stores its title and default text as two free
lines, and an empty default text *is* an empty line. Stripping it shifts that
record's fields exactly as it does for the native reader.

For reference, the blank-line heuristic this replaced reported 12 951 records
for the same corpus, but 582 files changed their record count when blank lines
were removed and `BatchReportzLib.y` collapsed from 23 records to 1. It produced
12 506 path rows against the 13 320 above: it turned an empty payload
(`index SP 0`) into the bogus path `"0"` and never read a binding default.

## What is *not* implemented

Every discriminator the corpus uses is now read. Two readings changed after the
corpus disagreed with the first transcription, and both are worth knowing:

* **Family 1 `7` and `4` are real payloads.** "Inline" meant *implemented inside
  the family switch*, not "consumes nothing": `7` reads `D[4], H[2], I, [I]`, and
  `4` reads `I[2], B3, I[2], [F, B2, B2], [B2]`. The `I[2]` of case `4` is one
  `scanf("%d%d")`, so its second integer may sit at the start of the next
  physical line and the following `MORE()` is evaluated only after both are read.
  Treating either case as inert swallowed payload fields and landed the next
  `disc = I` mid-line.
* **Family 2 discriminator 3 starts with a `B3` binding.** The transcription
  listed `D2, I3, [B2, B2]`, but every corpus record writes
  `3 <binding> <D2> <I3> …` (e.g. `3 Var 1.00000E+002 10 Value.Mean
  3.80000E-001 2.60000E-001 1 0`); `D2` cannot begin on `Var`. Implemented as
  `B3, D2, I3, [B2, B2]`, and the same reading confirmed discriminator 4
  (`I, B3, I3, [F, B2, B2]`) where `B3` is a binding rather than a bare `F`.

**What is left.**

* A family 1/2 discriminator outside the transcribed set still stops the scan
  with a `warning` (`Graphics record content is not recovered for family 1
  discriminator 9; record scan stopped`) rather than guessing a boundary. No
  corpus record reaches one.
* The severity the native tool assigns to a malformed record is not recovered.
  The readers report `error` for content the grammar rejects and `warning` for a
  reader that was never transcribed.

## Deliberate deviations

* `WORD()` (`004a7260`) consumes the byte that terminates the word, including a
  line break. Here a line break is left in the stream for the following `END()`;
  it is equivalent for every field that is followed by `END()` and it keeps the
  `B1` + `END` + `getc` shape-byte sequence aligned when the last word is not
  space-padded.
* `MORE()` (`0042ec70`) tests only for LF. A CRLF companion leaves the CR after a
  numeric read, so both line-break bytes count as "nothing more on this line";
  that is what the native helper sees after a word (which consumes the CR) and it
  is needed for the `if MORE()` gates to line up on real files.
* The separator byte before a picture-display payload is consumed with `getc`
  natively. Here a line break is left alone, so an LF-only companion reads the
  payload it actually has instead of the next line. Real companions are CRLF
  (`read_text_cp1252` deliberately preserves the bytes), where the behaviour is
  identical to native: `getc` eats the CR and `LINE()` stops on the LF.
* A top-level line that cannot open a record (a stray name, a comment) is
  skipped instead of reported. This is the native `MARK` line sync, and it keeps
  a junk companion from producing an error.

## Verification cases

* composites in several module definitions, with ordinary primitives between them
* a marker in a module type, one in an inline submodule and one in the own
  `ModuleDef` — the pairing order is module type, submodule, own
* adjacent companion records (no blank line between them)
* internal zero-valued fields and bare `0` lines inside a record
* family-5 records with different subtypes and entry counts
* family-1 records for each transcribed discriminator, with and without the
  2.7 / 2.18 trailing blocks
* invariant: parsing a file with and without blank lines yields identical
  record structure, except where an empty line is a `LINE()` field value

---

# Recovered record grammar (transcription, 2026-10-27)

Input-consumption transcription of the companion readers for build
`3.1-2 (3.1.2000.18)`. Field *meanings* are unnamed where unrecovered; this is
what the readers consume, not a claim about diagnostics.

## Primitives

```text
I = scanf("%d")   H = scanf("%hd")   F = scanf("%g")   D = scanf("%lg")
MORE()  = next byte is neither LF nor EOF   (does NOT skip spaces)   0042ec70
END()   = scanf("%*[^\n]") then getc()      (consumes the LF)
MARK()  = c = getc(); while c not in {LF, SPACE}: END(); c = getc()   004aea80
WORD()  = skip SPACE/LF, collect to SPACE/LF, consume delimiter      004a7260
WORD2() = WORD() plus "Invalid" -> empty                             004a71d0
LINE()  = one fgets, 256-byte buffer, LF stripped                    004976a0
COUNTED()= n = I; getc(); repeat max(n,0) bytes, LF read as SPACE
```

The outer family integer is consumed before each reader (`0043a9b0`).

## Bindings — `004a72d0`

Modern (`major != 0 or minor >= 107`):

```text
qualifier = WORD()
baseline  = WORD()  # B1 (True/False), WORD2() for B4/B11/B12, I for B2, F for B3

Var   -> reference = COUNTED(); B1 only: if "Not" then second COUNTED()
Lit   -> text = COUNTED(); value interpreted per initialized kind (no extra bytes)
Expr  -> text = COUNTED()
other -> return after the baseline (None is not validated, just unrecognised)
```

`Var BASELINE LEN reference`, `Lit BASELINE LEN text`, `Expr BASELINE LEN text`.
The `(c, p)` conversion arguments never change consumption. `004a72d0` never
calls `END()`; callers own the rest of the line.

Legacy (`major == 0 and minor < 107`): no qualifier; a leading decimal `n`
selects a counted reference (`n` bytes) versus a WORD-style one (`n == 0`);
then the same baseline per kind; B1 has the special `'I'` integer form.

## Families

```text
F1 004e5410: MARK, B1, D4, H, [I2], [B2], END;
             MARK, disc = I; while disc != 0:
                 payload per disc (1: 004dcc30, 2: 004f1950, 3: 004d1fc0,
                                   4: I[2], B3, I[2], [F,B2,B2], [B2],
                                   5/6: F,H,
                                   7: D[4], H[2], I, [I])
                 END; MARK; disc = I
             END
             (no text-list production; the index/text loop is 00734690)

F2 0041b7f0: MARK, B1, D4, I, H, [I], END;
             MARK, disc = I; while disc != 0: payload per disc (1: 00417930,
                 2: B3,F, 3: B3,D2,I3,[B2,B2], 4: I,B3,I3,[F,B2,B2])
                 END; MARK; disc = I
             END
             (the B3 of 3 and 4 is a binding, not a bare F)

F4 00402050: MARK, D4, H3, [word], MARK, trailing = I, END
             (trailing integer is read, not checked against 0)

F5 004ac980: MARK, B1, D4, H; MARK, subtype = I, END; subtype = max(subtype,0)
             subtype 1 -> 007343e0: line, line, I, END, I, END, B4, B2, count = I,
                          END, 00734690(count), trailing = I, END
             subtype 2 newer (major != 0 or minor > 96) -> 00733520:
                          B4, B2, count = I, END;
                          count x { index = I, disc = I;
                                    disc == 0: getc; read_line; trim
                                    else: B4, END }
                          default_disc = I;
                          0: getc; then WORD2() if major == 0 and minor < 100,
                             else LINE(); trim
                          else: B4, END
                          back in 004ac980: B1;
                          if major > 1 and minor > 18: END; getc -> shape byte
                                    (only lowercase 'f' is false)
                          END; trailing = I; END
             subtype 2 older (major == 0 and minor <= 96) -> 007333c0:
                          line, line, I, END, I, END, B4, B2, count = I, END,
                          00734690(count); then marker = I;
                          marker == 55: B1; marker == 0: return; trailing = I, END
             (no shape byte in the older branch)

00734690(count): count x { index = I; END; text = read_line; trim }

F1 payload 004dcc30 (disc 1):
    D[3], B11, B11, H[2], I[2]
    if MORE(): I, B11
    if MORE(): F
    if MORE(): I[2], B12
    if MORE(): B11
    if MORE(): I, END, B1, I, B1, I, B1
    return                        (the outer 004e5410 performs END)

F1 payload 004f1950 (disc 2):
    D[3], B3, B3, I, H, I[2]
    if MORE(): I
    if MORE(): F[2], B2(1,1)
    if MORE(): B4, B1
    if MORE(): I, END, B1
    if DAT_00845343 == 0:         (0062e800 sets it before 2.7)
        B1, END, B3, B3
    return

F1 payload 004d1fc0 (disc 3):
    I, B3, I[3]
    if MORE(): B2(1,1), B2(1,0)
    if MORE(): B1
    if MORE(): I, B4
    if MORE(): B12
    if MORE(): B4, B4
    if MORE(): I
    if MORE(): B1
    if MORE(): B2, B2, B2
    if MORE(): I, END, B1, I, B2
    if DAT_0084538e == 0:         (0062e800 sets it before 2.18)
        END, B2; END, B12; END, B12; END, B2
        END, B2; END, B1; END, B3; END, B1
    return

F2 payload 00417930 (disc 1):
    B3, B3, D[3], I[2]
    if MORE(): I
    if MORE(): F[2], B2(1,1), H, I
    return

The `(c, p)` arguments of `B2(1,1)` / `B2(1,0)` never change consumption. The
`if MORE()` gates are evaluated at the current cursor and never skip spaces.
H[2] and I[2] are two `H` / two `I` reads.
```

Writer layout for a literal entry (`00733830`): `index SP 0 SP text SP LF`, and
`00733520` consumes exactly one byte after `disc == 0` — with native output that
byte is the space; if it is LF the reader consumes it and takes the *following*
line as the literal. Do not replace that `getc()` with whitespace skipping.
