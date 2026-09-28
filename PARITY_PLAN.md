# SattLine Parser Parity Plan

How we verify — against the **real SattLine parser** — which validation and
semantic/parity checks are genuinely missing from `sattline-parser`, pin the
exact behavior of each, and encode confirmed findings back into this repo.

---

## 1. Objective

Turn the speculative gap list (validation-tier + semantic/cross-module) into a
**verified conformance catalog** by feeding adversarial files to the real
parser and recording exactly what it accepts, rejects, and says. Every rule we
ship (or deliberately leave to the consumer layer) is then grounded in real
observed behavior instead of inference.

Parity direction we care about: **if our parser says "valid", the real parser
agrees**, and conversely the real parser's rejections become our fixtures.
Findings that contradict rules we already implemented get a **reversal** pass
(a real reject → our accept, or a real accept → our reject).

## 2. Core method — isolated probes

Every candidate rule gets identical treatment:

1. **Control file** — a minimal SattLine program that is valid except that it
   exercises the construct in question. Must be *pre-verified* to be accepted
   by the real parser. This gate catches wrong intuition fast (a "valid"
   template can violate a real rule we didn't know about).
2. **Probe file** — byte-identical to the control, minus exactly **one**
   injected violation. One violation per file — isolation is the whole point.
3. **Run both through the real parser** and classify:

   | Outcome                                  | Meaning                                              | Action                  |
   | ---------------------------------------- | ---------------------------------------------------- | ----------------------- |
   | `reject` (violation only)                | rule confirmed real                                   | encode rule             |
   | `accept` both                            | not enforced **or** probe too weak                    | strengthen violation, re-probe (default), then drop if still accepted |
   | `reject` both                            | template bug                                          | fix control file        |
   | `accept` the probe when expected reject  | surprise — real allows it                            | study real semantics    |
   | `reject` the control when expected accept| our notion of "valid" is wrong                        | learn from real error   |
   | `reverse` (contradicts an implemented rule) | our rule is a false positive / false negative     | disable/adjust rule + fixture |

   The **accept-both** corner is resolved by default to "strengthen the
   violation and re-probe"; only a *stronger* probe that is still accepted
   counts as a disproven rule.

4. **Capture the real diagnostic text/codes verbatim** (message, line/column,
   numeric code) — that verbatim text becomes the expected-output reference.
5. **Encode confirmed rules**: validator rule + unit test + fixture, with the
   real parser's exact message as the expected reference where applicable.

## 3. Harness — GUI-only, snapshot driven (decided)

The real parser is a **Windows GUI** tool that checks **multiple files per run**
and reports **readable diagnostics**. There is no CLI and no pinned version.
This locks in **snapshot mode** — a human runs the tool, and its output is
transcribed and committed.

Workflow per probing session:

1. `scripts/probe/generate.py` emits the probe tree:
   - `probes/rules/<id>/control.s` and `probes/rules/<id>/violation.s`
   - `probes/MANIFEST.yaml` — machine-readable rule list (id, area, expected
     classification, status)
   - `probes/TRANSCRIPT.md` — one row per probe file:

     | file | rule | kind | expected | real status | message |
     | --- | --- | --- | --- | --- | --- |

2. **Human** runs the GUI's batch check over the whole `probes/` tree (one
   session), then fills `real status` (accept/reject) and pastes the verbatim
   message into the transcript.
3. `scripts/probe/analyze.py` parses the filled transcript, classifies every
   probe against its expected outcome, and writes
   `tests/real/reports/<date>-<gui-version-if-known>.json` plus a summary table
   (confirmed / disproven / accept-both / reversed / template-broken).
4. The committed snapshot is the golden record; our test suite reads it. CI
   never needs the licensed tool. Optional CI job: diff a freshly generated
   transcript against the committed snapshot to detect drift in either parser.

*If a scriptable entry point ever becomes available, a `run.py` live adapter
can slot in behind the same report schema — the format, not the transport, is
the contract.*

## 4. Probing tiers

Cheapest–most-informative first.

- **Tier 0 — inventory the existing corpus.** A **one-column sweep** of all
  ~104 current fixtures (valid + edge + invalid): feed each file to the real
  parser, record accept/reject + message. No control/violation pairs here —
  this tier verifies every existing assumption for free and surfaces the first
  surprises and **reversals** (e.g. real accepts a file we treat as invalid,
  or rejects one we treat as valid).
- **Tier 1 — one probe pair per inferred validation-tier candidate**
  (frontier list in §6.1).
- **Tier 2 — edge matrix per confirmed rule.** Case-insensitivity, ordering,
  nesting depth, argument positions, modifier combinations — to pin exact
  boundaries (same technique as the duration/time format tables).
- **Tier 3 — cross-module projects.** Multi-file sets (program + library with
  moduletypes) to nail the semantic/cross-module frontier (§6.2).
- **Mechanics probes first** — register the mechanism once (datecode handling,
  module type binding, parameter transfer, `.g`↔`.s` pairing) before
  dependent probes reuse the template.

## 5. Feedback loop into this repo

| Case                          | Action                                                                   |
| ----------------------------- | ------------------------------------------------------------------------ |
| We accept, real rejects       | add validation rule + unit test + (real-confirmed) invalid fixture        |
| We reject, real accepts       | remove/adjust rule + fixture (e.g. `SubSeqTransitionAlt`, compressed-grammar cases) |
| **Reversal** of an implemented rule | disable/amend rule + fixture; record in reversal watchlist (§6.4)  |
| Consumer territory (project graph) | record behavior + real diagnostics for the SattLint layer            |
| Edge behavior discovered      | extend the equivalent format/table test (like the duration/time tables)   |

## 6. The frontier being probed

Confidence markers: `[user]` = asserted by the user as real-parser behavior
(verify on first tool run, then promote to `[corpus]`) · `[corpus]` = evidenced
by real output · `[model]` = strongly implied by AST/language semantics ·
`[inferred]` = plausible, unverified.

### 6.1 Validation tier — intra-file (`src/sattline_parser/validation/`)

**Expression typing — largest gap:**
1. Assignment LHS↔RHS type compat, incl. allowed implicit conversions
   (int↔real) vs forbidden (string↔numeric, time↔integer). `[inferred]`
2. Binary/compare operand types (`time > integer`, string arithmetic). `[inferred]`
3. `IF`/ternary condition boolean; mutually compatible branches. `[inferred]`
4. Builtin argument **types** (in/out/inout) — current `BuiltinFunction` only
   models arity + out positions. `[inferred]`
5. SFC-accessor typing: `Step.X` boolean, `Step.T` duration, `Seq.Reset`
   boolean. `[inferred]`
6. Record-qualification depth (`A.B.C` on a scalar root). `[inferred]`

**Context-restricted / pseudo-types:**
7. **AnyType** — legal **only** as a module parameter type; rejected as a
   `RECORD` field type and as a `LOCALVARIABLES` type. `[user]` Today the
   parser would flag `X: AnyType` as an unknown datatype (SL-V020) — a
   potential false positive to resolve.
8. `GroupData` — reserved scan-group connector type (already whitelisted).
   Complete the reserved-name set; probe for sibling pseudo-types. `[corpus]`

**Statement / context rules:**
9. `:= Default` is legal on **all parameters**. `[user]` Probe separately
   whether `:= Default` is legal on plain (non-parameter) local variables.
10. **Const does not require an initializer** — it silently uses the default
    value when unset. `[user]` Removes the earlier "Const needs init"
    hypothesis entirely; no rule.
11. State / OpSave / Secure modifier legality per datatype. `[inferred]`
12. `:Old` / `:New` only inside STEP ENTER/ACTIVE/EXIT code (today we check
    target is State, not location). `[inferred]`

**SFC:**
13. **Accessor enabling & namespace**: `Step.X` / `Step.T` are only legal when
    the corresponding function is enabled for that sequence; when enabled the
    step name becomes a variable, so it must not conflict with declared
    variables. The same applies to `.Reset` on a sequence. `[user]` Extends the
    existing `DuplicateSFCElementNames` (SL-V021) and SFC-accessor exemption
    work into a full namespace rule.
14. **Unlimited `SEQINITSTEP`s are allowed** `[user]` — so our SL-V022
    init-placement rule (must be first / single init) is a **candidate
    reversal**: probe before relying on it.
15. SFC reachability is **not** checked by the real parser. `[user]` — drop.
16. `SEQFORK` forward-only semantics are **not** checked. `[user]` — drop
    (we check only target existence, which stays).
17. Branch-start rules (SL-V023 alternative/parallel branch starts) — keep;
    verify via Tier 0 sweep. `[corpus]`

**Reserved names / catalog completeness:**
18. Declaring a variable/datatype named `On` / `Off` / `GroupData` (we exempt
    reads but never forbid re-declaration). `[inferred]`
19. Builtin catalog completeness — only 8 functions modeled. `[inferred]`

### 6.2 Semantic / cross-module — project graph territory

**Moduletype & library graph (incl. both kinds of "loops"):**
20. **Loops — both kinds**: (a) moduletype-instantiation cycles — a moduletype
    whose body transitively instantiates itself → infinite expansion; (b)
    **library loops** — a library unit whose dependencies transitively loop
    back on itself. Real parser should detect both. `[user]`
21. Self-instance (degenerate variant of 20a). `[model]`
22. **Moduletype not invoked where it is declared** (declared in
    `TYPEDEFINITIONS` but zero instances in its own unit/library). `[user]`
23. Instance references a moduletype name with no definition anywhere
    (`ModuleTypeInstance` is fully skipped today). `[model]`
24. Instance/param arity vs declared moduletype params (positional + named
    binding). `[model]`
25. Param-transfer typing (value vs formal param type — the
    `DurationInParameterMapping`/`GlobalParameterMapping` mechanism). `[model]`
26. GLOBAL-marked params/vars must have a matching declaration in scope. `[inferred]`
27. ~~Formal param direction (`in`/`out`) matching~~ — **not checked** by the
    real parser. `[user]` — drop.

**Cross-file variable contracts:**
28. Referencing another program's variable — name/type/direction contract vs
    actual. `[corpus, consumer]`
29. Writes into a dependency's const/read-only external var. `[inferred]`
30. Ambiguous supply — a variable provided by two dependencies. `[inferred]`
31. Referencing an undeclared external variable (no supplier) — accepted
    today. `[corpus, consumer]`

**Dependency consistency:**
32. **Undeclared dependency used** (a file references a name not in its `.l` /
    `.z` dependency list) — probe. Note: the real parser does **not** detect a
    *declared-but-unused* dependency. `[inferred] / [user]`

**Scan groups / GroupConn:**
33. `( GroupConn = Var )` variable exists + is a `GroupData` variable; duplicate
    group connections; group var used elsewhere. `[inferred]`
34. `ScanGroupVar` declarations in moduletype bodies tied to the enclosing
    group. `[inferred]`

**Library hygiene:**
35. Declared-but-unused DATATYPE / variable. `[inferred]`

### 6.3 Graphics correlation — `sattline_parser.project` / consumer

36. **Date consistency**: the dates in the initial 3 header lines must match
    between the code file and the graphics file. `[user]`
37. **Composite-object count parity**: the number of composite objects in the
    code must equal the number in the graphics file. `[user]`
38. Graphic object bindings ↔ module defs; enable/invar tails resolving to
    declared vars. `[consumer/corpus]`
39. **Mechanics research** (not a rule — a deliverable): document how the
    `DateCode_` is generated and how it works, and how `.g`/`.y` files are
    paired with code, so the date-consistency and pairing rules above rest on
    understood internals. `[research]`

### 6.4 Reversal watchlist — implemented rules the real parser may contradict

| Rule | Finding driving the probe | Probe |
| --- | --- | --- |
| SL-V022 `SFC_INIT_STEP_PLACEMENT` | Unlimited `SEQINITSTEP`s allowed `[user]` | feed a multi-init sequence to real parser |
| SL-V020 `UNKNOWN_DATATYPE_NAME` | `AnyType` is a legal (parameter-only) type `[user]` | feed `: AnyType` param, field, localvar |
| SFC accessor exemption (dotted `Step.X`) | accessors only legal when enabled for the sequence `[user]` | feed accessor with function disabled |

## 7. Deliverables

- `scripts/probe/{generate,analyze}.py` (+ optional `run.py` live adapter)
- `probes/` tree with `MANIFEST.yaml` + `TRANSCRIPT.md` per session
- `tests/real/reports/<date>-<gui-version>.json` snapshots (golden records)
- New **real-confirmed** fixtures + validator rules + unit tests
- **`PARITY.md`** — living conformance matrix (rule × status × real message)
- **`docs/datecode.md`-style mechanics note** — `DateCode_` generation,
  header-line semantics, `.g`/`.y` pairing (deliverable 39)
- Optional CI job comparing a freshly generated snapshot against the committed
  one (diff = behavioral drift of either parser)

## 8. Phasing

- **P0** — handoff contract + generator/analyzer + Tier-0 corpus sweep
- **P1** — Tier-1 probes (§6.1) → implement confirmed rules; resolve reversal
  watchlist (§6.4)
- **P2** — Tier-3 project probes (§6.2/§6.3) → verified spec for the consumer
  layer + datecode/mechanics note
- **P3** — encode everything (fixtures / tests / PARITY.md), CI wiring

## 9. Decisions (from planning Q&A)

1. **Invocation**: Windows GUI only → snapshot/workflow mode is mandatory; no
   live automation.
2. **Diagnostics**: readable messages (name + line/column) → transcribe
   verbatim into the transcript.
3. **Batching**: multiple files per run → the whole `probes/` tree is one GUI
   session.
4. **Version**: no pinned baseline → record the version string if discoverable
   in the GUI; otherwise key the snapshot by session date.

## 10. Definition of done

Parity work is complete when:

- every `[inferred]` / `[model]` / `[user]` item in §6 is classified by a real
  parser run (confirmed / disproven) and recorded in `PARITY.md`;
- every confirmed in-package rule (§6.1) is implemented with a unit test and a
  real-confirmed fixture, and none of the asserted-not-checked items are
  implemented as rules;
- the reversal watchlist (§6.4) is fully resolved;
- cross-module/graphics findings (§6.2/§6.3) are documented as a verified spec
  for the consumer layer;
- a Tier 0 re-sweep of the whole fixture corpus passes against the committed
  snapshot with zero unexplained mismatches.

---

*Last updated: 2026-09-28*
