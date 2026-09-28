# DateCode_ mechanics note

Deliverable 39 from `PARITY_PLAN.md` §6.3 — research (not a rule): how
`DateCode_` works and how code/graphics files are paired, so the date-consistency
(§6.3 #36) and pairing rules rest on understood internals.

Reference material: the real library/unit tree in `Libs/` (read-only; nothing
here is copied from it). Status of every claim is marked `[observed]` (seen in
real files) or `[hypothesis]` (inference; probe C-101…C-106 and the `proj/`
closure exist to confirm).

## 1. What the token is

A `DateCode_` is a signed decimal hash attached to every type-like definition:

```text
TypeA = MODULEDEFINITION DateCode_ 101100          [observed]
UnitPumpDvType = RECORD DateCode_ 200100        [observed]
BasePicture Invocation ( ... ) : MODULEDEFINITION DateCode_ 300100   [observed]
```

It appears on moduletype and record definitions, and as the right-hand reference
of `MODULEDEFINITION` bindings. It is a *stable digest of the definition's
content*, not a hash of its name:

- the same name maps to many different codes across the tree (e.g. `Frame_Module`
  → 11111111, 22222222, 33333333, 44444444, …) `[observed]`
- the same library copy maps to the same code wherever it is stored
  (123456789 shared by four `projectlib` files) `[observed]`
- Java `String.hashCode` and CRC-32 of the definition text do not reproduce any
  observed code `[observed — negative result]`

Conclusion: treat it as an opaque content/version fingerprint. The real data
does not let us recover the algorithm, and the probes carry *synthetic* codes in
a `9xxxxx` / `10xxxxx` / `2xxxxx`-style namespace precisely so they can never be
mistaken for real digests.

## 2. How references are made

Three accepted reference styles, all present in real units:

| Reference | Form | Used for |
| --- | --- | --- |
| Same-unit by name | `: ErrorIcon;` | submodule bound to a moduletype defined in the same unit/library file |
| Cross-unit by code | `: MODULEDEFINITION DateCode_ 123456789` | submodule bound to a moduletype in another library |
| Code + frame module | `: MODULEDEFINITION DateCode_ 300100 ( Frame_Module )` | unit top-level picture that also carries a frame module |

The parenthesised token after the code is **`Frame_Module`** — a frame-module
declaration attached to the binding — *not* a name hint used for back-lookup. It
is what our grammar models as `frame_module`. Our synthetic moduletype bindings
therefore use the plain code form (`: MODULEDEFINITION DateCode_ N`) for
cross-unit references and the name form used inside a unit.

`[hypothesis]` the tool looks references up by code only; the `( Frame_Module )`
form does not bypass it.

## 3. Code/graphics pairing

Each program/library unit ships as a triple in one folder:

```text
ExampleUnit.x    code (extension is irrelevant; .s is equally parseable)
ExampleUnit.y    graphics
ExampleUnit.z    dependency list (library names, one per line)
```

- The `.x` opens with three header lines; the `.y` has a single header line:
  `" Syntax version 2.23, date: 2016-06-08-11:25:38.882 N "` (note the leading
  and trailing spaces inside the quotes). `[observed]`
- Across 557 real code/graphics pairs, 553 share an identical value on that
  first date line; the 4 exceptions are compiled binary libraries (no parseable
  header). `[observed]`
- The `.y` body is sparse numerics; an empty picture compresses to a ~200-byte
  body in which only the date varies. `[observed]`
- The `.z` lists the libraries the unit depends on (e.g.
  `BaseLib / StdLib / userlib / configlib`). `[observed]`

So §6.3 #36 (date parity) and #37 (composite-object count parity) are tested by
C-201 and C-202. Their `.s` files are identical; only the generated `.y`
differs (date shifted by one day / one extra object row). If the real parser
accepts those, both user-asserted rules are contradicted and the pairing is
looser than stated.

## 4. Implications for our model

- Our grammar is already faithful to the three reference styles (§2) —
  `invocation_module_type` (name), `invocation_new_module` (code), and
  `base_picture_module`/`frame_module` (code + `Frame_Module`).
- We deliberately do **not** fabricate a digest algorithm; the probes use
  synthetic codes in a reserved namespace.
- `[hypothesis]` the real parser does not re-derive the code from content when
  checking a unit's own definitions (the tree's same-name/different-code spread
  implies it trusts the stored code, or compares codes only when resolving
  cross-references). The GUI session on `probes/` will confirm or refute this.
