# Graphics companion correlation — status and open work

Research note, started 2026-10-27. Based on the recovered native behaviour for
build `3.1-2 (3.1.2000.18)` plus a sweep of the 743 companion files under
`~/Projects/Libs`.

## What is implemented

* **Positional binding.** `graphics_parsing.correlate_composites(picture, model)`
  walks the source AST in parse order (module definitions, nested submodules,
  then module types) and pairs the *n*-th `CompositeObject` marker with the
  *n*-th companion record — the native rule (`00665fc0` consumes the next record
  at each marker; there is no name lookup). Markers without records and records
  without markers are reported as `GraphicsMessage` values; the native
  diagnostic and severity for both cases is not recovered.
* **Record ordinals.** `GraphicsCompositeRecord.ordinal` carries the companion
  position; `GraphicsCompositeBinding` exposes the pair.
* **Family set.** `{1, 2, 4, 5}` matches the recovered handlers
  (`004e5410`, `0041b7f0`, `00402050`, `004ac980`), with family `5` subtype `2`
  recognised as PictureDisplay and a shape flag as its trailer.
* **Structural record readers.** `project/graphics_records.py` consumes each
  record field by field instead of scanning lines, so a record boundary follows
  from the family grammar and never from blank lines. It implements the
  transcription further down this note: the primitives (`I`, `H`, `F`, `D`,
  `END`, `MARK`, `WORD`, `WORD2`, `LINE`, `COUNTED`, plus the one-byte separator
  before a picture-display payload), the binding reader `004a72d0` (modern and
  legacy layouts), families 1, 2 and 4, family 5 subtypes 1 (`007343e0`) and 2
  (`00733520`, older `007333c0`), and the indexed-text loop `00734690`.
* **Version-dependent layout.** The `" Syntax version x.y` header of the
  companion selects the branches: `major > 1 and minor > 18` reads the separate
  picture-shape byte, `major == 0 and minor < 107` is the pre-qualifier binding
  layout, `major == 0 and minor <= 96` is the older picture-display layout. A
  file without a header is read as the modern layout.

## Verification (743 companion files, all four project trees)

| Measurement | Result |
| --- | --- |
| Files read to completion | 727 |
| Records read | 12 535 (12 525 family 5, 10 family 4) |
| PictureDisplay records / indexed rows | 11 967 / 1 936 |
| Files that stop at an unrecovered sub-reader | 16 (all family 1, see below) |
| Record structure that changes when blank lines are removed | 83 files, every one of them a subtype-1 text table storing an *empty* title/default line |

The last row is the invariant this work targeted. A blank line is no longer
formatting: outside a `LINE()` field it is skipped like any other whitespace, so
removing it cannot move a boundary. The 83 remaining differences are data — a
subtype-1 record stores its title and default text as two free lines, and an
empty default text *is* an empty line. Stripping it shifts that record's fields
exactly as it does for the native reader.

For reference, the blank-line heuristic this replaced reported 12 951 records
for the same corpus, but 582 files changed their record count when blank lines
were removed and `BatchReportzLib.y` collapsed from 23 records to 1.

## What is *not* implemented

**Family 1 and 2 payload sub-readers.** The family-level loop is recovered
(`MARK, disc = I; while disc != 0: payload; END`), and the payloads that *are*
transcribed are read (`F1`: 4, 5, 6, 7; `F2`: 2, 3, 4). Four sub-readers are
still unknown, and they are exactly the ones the corpus exercises:

| Sub-reader | Called for | Shape seen in the corpus |
| --- | --- | --- |
| `004dcc30` | family 1, disc 1 | a multi-line block: three bindings, then a further binding/`I` mix, then a fixed tail of eight `None <value>` bindings with differing baseline kinds |
| `004d1fc0` | family 1, disc 3 | `I` plus a `Lit`-style binding, on the discriminator's own line |
| `004f1950` | family 1, disc 2 | not observed in the corpus |
| `00417930` | family 2, disc 1 | not observed in the corpus |

The readers do **not** guess a boundary for these. A record whose payload hits one
of them stops the scan with a `warning` `GraphicsMessage`
(`Graphics record content is not recovered for family 1 discriminator 3; record
scan stopped`) and the records already read are kept. Guessing would shift the
ordinal of every later record, which is the failure mode positional binding
exists to prevent — the 16 affected files stop after 1, 6, 10 or 15 records
rather than hand out a wrong association.

Recovering them needs a transcription of those four functions, or a schema
derived from the corpus (the family-1 block repeats identically within a file,
so the field order is fixed per discriminator). Until then the fields stay
unread.

Two smaller gaps:

* Optional same-line fields that the native code guards with `MORE()`
  (`F1` `[I2]`/`[B2]`, `F2` `[I]`/`[B2,B2]`/`[F,B2,B2]`, `F4` `[word]`) are not
  interpreted — the field's own `END()` consumes them, which is what keeps the
  boundary right. `MORE()` tests "next byte is not LF", which a CRLF companion
  answers with "yes" because of the padding the writer emits before the line
  break, so it cannot be used as-is.
* The severity the native tool assigns to a malformed record is not recovered.
  The readers report `error` for content the grammar rejects and `warning` for a
  reader that was never transcribed.

## Deliberate deviations

* `WORD()` (`004a7260`) consumes the byte that terminates the word, including a
  line break. Here a line break is left in the stream for the following `END()`;
  it is equivalent for every field that is followed by `END()` and it keeps the
  `B1` + `END` + `getc` shape-byte sequence aligned when the last word is not
  space-padded.
* The separator byte before a picture-display payload is consumed with `getc`
  natively. Here a line break is left alone, so an LF-only companion reads the
  payload it actually has instead of the next line. Real companions are CRLF
  (`read_text_cp1252` deliberately preserves the bytes), where the behaviour is
  identical to native: `getc` eats the CR and `LINE()` stops on the LF.
* A top-level line that cannot open a record (a stray name, a comment) is
  skipped instead of reported. This is the native `MARK` line sync, and it keeps
  a junk companion from producing an error.

## Verification cases for the family 1/2 readers

* composites in several module definitions, with ordinary primitives between them
* adjacent companion records (no blank line between them)
* internal zero-valued fields and bare `0` lines inside a record
* family-5 records with different subtypes and entry counts
* family-1 records for each discriminator, including the repeating block shape
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
                                   4: inline, 5/6: F,H, 7: inline)
                 END; MARK; disc = I
             END
             (no text-list production; the index/text loop is 00734690)

F2 0041b7f0: MARK, B1, D4, I, H, [I], END;
             MARK, disc = I; while disc != 0: payload per disc (1: 00417930,
                 2: B3,F, 3: D2,I3,[B2,B2], 4: I,B3,I3,[F,B2,B2])
                 END; MARK; disc = I
             END

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
                          default_disc = I; 0: getc + line/word (version split)
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
```

Writer layout for a literal entry (`00733830`): `index SP 0 SP text SP LF`, and
`00733520` consumes exactly one byte after `disc == 0` — with native output that
byte is the space; if it is LF the reader consumes it and takes the *following*
line as the literal. Do not replace that `getc()` with whitespace skipping.
