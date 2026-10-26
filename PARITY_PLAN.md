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

**Expression typing — implemented.**
Probed 2026-10-01; the real tool confirmed three rules, all three now ship.
See §11 for the outcome and the four corpus expectations they corrected.

1. Assignment LHS↔RHS type compat. `[inferred]` → **confirmed → SL-V029**
   `[user, 2026-10-01]`: `ViolIntFromBool.x` (T1-001) is rejected with
   `Datatype error in assignment: Output = Flag1;` — assigning a `boolean` to
   an `integer` is illegal. Ours accepts. Note this **confirms** the
   `DurationInParameterMapping`/bool rejection already seen in `BadCrossMod.x`
   and implemented as SL-V027 for the single-file case, but that rule only
   covers submodule parameter supply, not a plain `:=` in an equation block.
   SL-V029 is the equation-block rule; it groups primitives into type families
   (numeric / boolean / string / temporal) rather than demanding an exact
   match, because `integer` into `real` is probed-accept.
2. Binary/compare operand types. `[inferred]` → **confirmed → SL-V028**
   `[user, 2026-10-01]`, twice:
   - `ViolRealVsBool.x` (T1-002): `Only integer and real allowed for this
     operator X > Flag1` — a `boolean` operand is illegal in a comparison.
   - `EdgeBareDurZero.x`, `EdgeNegDurVal.x`, `ValidDurAndTime.x`:
     `Only integer og real allowed for this operator ZeroDur == ZeroFull` —
     `duration` (and `time`) operands are illegal in `==`/`<`/`>` too. So the
     numeric-only operand rule covers *both* booleans and time-like types.
     The three negative/zero/complex duration **declarations** are fine; it is
     only the comparison that fails. Ours now rejects all three files
     (SL-V028); this also invalidated four of our own corpus fixtures (§11).
3. `IF`/ternary condition must be boolean. `[inferred]` → **confirmed → SL-V030**
   `[user, 2026-10-01]`: `ViolIntCond.x` (T1-003) is rejected with
   `Condition in IF-sentence is not boolean :IF A THEN A = 1;`. Ours now
   rejects (SL-V030). Branch-type compatibility is still `[inferred]` —
   unprobed, and a ternary with disagreeing branches is left unflagged.
4. Builtin argument **types** (in/out/inout) — current `BuiltinFunction` only
   models arity + out positions. `[inferred]`
4a. **Call arguments must be variables** — raw string/number literals in a
    call (e.g. `EqualStrings("alpha", "beta")`) are rejected; pass a declared
    variable instead. `[user]` / observed: re-probed while clearing
    `BadBuiltinWrong.x` (the real parser rejects literals in `EqualStrings`).
    **Implemented** as SL-V015 `STRING_LITERAL_CALL_ARGUMENT` (flags each
    string-literal argument in any call, not just known builtins).
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

    **SL-V031 IMPLEMENTED 2026-10-01** - the `OpSave + State` pair is invalid.
    The file-load path for `EdgeOpSaveAndState.x` could not render its message
    (*"unable to read error message file"*), so I parked it rather than guess.
    The editor then supplied the missing text verbatim: **"Invalid attribute
    identifider or invalid combination of attributes"** (sic, typo in the tool).
    That turns an unreadable rejection into a real rule, and the wording settles
    the mechanism: the *combination* is invalid, not the spelling of an attribute.
    Scope is deliberately narrow - only the `opsave`+`state` pair is rejected.
    `State` alone and `OpSave` alone stay clean (`CtrlG.x` / `CtrlWithInit.x`,
    plus single-modifier controls in the fixture). `OpSave+Const`, `State+Const`,
    `Secure` combinations and modifier order remain unproven; the transformer
    flattens modifiers to booleans so order/repetition are not representable in
    the AST at all. `OpSaveConst.x` and `OpSaveStateReversed.x` are queued.
    Implemented as a **validation** error, not a grammar restriction: the editor
    reports an attribute complaint, and validation keeps it out of the parser.

13. **A coordinate position must be a real, never an integer.** SL-V032 IMPLEMENTED.
    `[user]` The first version of this rule was too narrow: I scoped it to
    ClippingBounds *computed* tails and deliberately left bare-variable tails
    permissive as "unproven". The user then stated the rule generally - a
    coordinate position can never be an integer - which is the correct scope, so
    the check now covers every collected tail, computed or bare. Kept as validation
    rather than grammar so real-typed computed tails still parse.
    Why the grammar alone cannot carry this: every coordinate *literal* position is
    already `REAL`-only in the grammar (`coordinates`, `clip_value`,
    `clip_value_plain`, `objsizedef`), so an integer can only reach a coordinate
    through a tail. The corpus contains zero integer coordinate literals, and the
    only non-real tail anywhere in the fixtures was the one probe.
    Two implementation notes worth keeping:
    * `ModuleDef.clipping_bounds` holds only the resolved float corners, so tail
      expressions were being dropped. Added `ModuleDef.clipping_tails` and populate
      it in `moduledef`; the shared `tails` property is untouched, so graphics and
      interact consumers are unaffected.
    * `_extract_coord_tails` collected only `str`, numeric pairs and `VarRef`, so
      expression tails were silently discarded. Extended it to the remaining
      expression nodes.
    Known gap, deliberately left: an `InVar_ "Name"` tail carries a variable
    *reference* whose value could be integer, but resolving the name is not
    evidenced and no corpus file uses that shape in a coordinate. Flagged rather
    than silently ignored.


14. **A closed sequence body must not end with a step.** SL-V033 IMPLEMENTED.
    Three independent probes (`EdgeTermSeqStep.x`, `EdgeSeqPar.x`,
    `EdgeSubSeqDef.x`) all put the caret on `ENDSEQUENCE` with
    `Incorrect Syntax - Error 32` rather than on the step itself. Reading the
    caret positionally: the tool was still waiting for more body when the
    terminator arrived, so the last `SEQSTEP` left the body unfinished.
    `[user]` **The grammar is correct and must not be changed.** The editor is
    graphical, so this state is simply unreachable there; the defect is a
    *missing rejection rule*, not absent vocabulary.
    `[user]` The rule's scope is conditional: legality depends on whether the
    sequence is open. `Sequence.type` already carries `SEQUENCE` vs
    `OPENSEQUENCE`, so the check is gated on that and `OPENSEQUENCE` is exempt.
    Two scoping decisions kept deliberately narrow, because only the outer body
    is evidenced:
    * the check runs on the sequence's own body only - not inside
      `ALTERNATIVEBRANCH` / parallel branches or sub-sequence bodies, where
      termination rules may differ;
    * branches that end on a step produce **one** diagnostic for the enclosing
      sequence rather than one per branch, matching the single caret the tool
      emits.
    `SeqBreak.s` and `SequenceAlternative.s` also ended on a step, but that was
    incidental to what those files probe (`SEQBREAK` placement and
    `ALTERNATIVESEQ`/`ENDLOOPSEQ` respectively). They were corrected to end on
    a transition rather than being reclassified, because otherwise the trailing
    step would mask the real question those files exist to answer. Both remain
    open `we-too-lenient` gaps.

12. `InVar_` / `OutVar_` **coordinate tail** must name a quoted DefineSym.
    **IMPLEMENTED 2026-10-01.** `ValidCoordInVar.x` gives an unambiguous syntax
    error (`DefineSym Expected` at `InVar_ PanelX`).
    *My first pass at this was wrong* and I want the correction on record: I
    regex-scanned the corpus, counted 50 "unquoted" sites, called them all defects,
    and proposed ~50 mechanical edits including 38 in `UnCompressedFullGrammar.s`.
    The user pointed out that file is a golden file the real tool compiles cleanly.
    Re-scanning properly - comments and string contents stripped, literals
    distinguished from identifiers - shows the 50 were almost all false positives:
    `InVar_ True` / `InVar_ 1` / `InVar_ 0.5` are **literals** (the `value`
    alternative), and `InVar_ LitString "..."` is the separate `litstring_tail`
    rule. `LitString` is never declared as a variable; it is a literal marker.
    The **only** genuine bare-name `InVar_` in the entire corpus is the four
    identifiers in `CoordInVarTail.s` - precisely the rejected construct.
    So: **zero golden-file edits were needed**, both golden files still parse
    untouched, and the one real defect moved `valid/` -> `invalid/`.
    Scoped to the **coordinate** context only (`coord_invar_tail`). The interact
    `invar` / `invar_tail` contexts still permit a bare name, because the
    rejection is only evidenced for coordinates and a bare-name binding is
    semantically plausible there.


**SFC:**
13. **Accessor enabling & namespace**: `Step.X` / `Step.T` are only legal when
    the corresponding function is enabled for that sequence; when enabled the
    step name becomes a variable, so it must not conflict with declared
    variables. The same applies to `.Reset` on a sequence. `[user]` Extends the
    existing `DuplicateSFCElementNames` (SL-V021) and SFC-accessor exemption
    work into a full namespace rule.
14. ~~**Unlimited `SEQINITSTEP`s are allowed**~~ — **disproven**.
    `[user]` `ViolSecInit.x` (R-101 violation) is rejected by the real
    parser: line 48 `>>>ENDSEQUENCE<<< Incorrect Syntax - Error 32`. A
    second init step is *not* allowed, so **SL-V022 stands** (must be
    first / single init). Ours rejects with SL-V022. The transcript
    classifies R-101 as `surprise-reject` because the *hypothesis* cell
    said accept; the hypothesis was wrong, not our rule.
15. SFC reachability is **not** checked by the real parser. `[user]` — drop.
16. `SEQFORK` forward-only semantics are **not** checked. `[user]` — drop
    (we check only target existence, which stays).
17. Branch-start rules (SL-V023 alternative/parallel branch starts) — keep;
    verify via Tier 0 sweep. `[corpus]`

**Reserved names / catalog completeness:**
18. Declaring a variable/datatype named `On` / `Off` / `GroupData` (we exempt
    reads but never forbid re-declaration). `[inferred]` — **confirmed for
    `On`/`Off`; SL-V034 IMPLEMENTED 2026-10-02.** `ViolVarOn.x` /
    `ViolVarOff.x` (T1-012) are both rejected by the real parser with
    `>>>On<<<` / `>>>Off<<< AliasSym Expected`. Reading the message: at the
    declaration position the tool wanted an *alias* and found a reserved word.
    So `On`/`Off` are reserved words that mean an SFC runtime thing — readable
    wherever a boolean is expected (hence the long-standing SL-V019 read
    exemption) but never declarable. Implemented as `SL-V034
    RESERVED_NAME_DECLARED` over the variable-declaration family (locals, module
    parameters, record fields) plus `DATATYPE` names, per "variable/datatype"
    above. `MODULETYPE` names are deliberately left alone: no probe reaches
    them and a moduletype sits in a different namespace.
    Two structural notes:
    * The reserved set moved out of `validation/code.py` into
      `validation/symbols.py` as `SFC_RUNTIME_CONSTANTS`, so the SL-V019 read
      exemption and the SL-V034 declaration ban read from one frozenset and
      cannot drift apart.
    * **`GroupData` is deliberately NOT in the set.** It is a reserved
      *datatype* — used by a module definition's `GroupConn=` tail — and we
      intentionally accept it as a type name
      (`declarations._VALID_UNRESOLVED_DATATYPES`). Folding it into the
      runtime-constant set would contradict that. Whether *declaring a variable*
      named `GroupData` is illegal is still open: `probes/ViolVarGroup.x` covers
      exactly that and is the one pending row in the T1-012 group. If the tool
      rejects it, `GroupData` joins the set with no structural change; if it
      accepts, the current exclusion is confirmed correct.
19. Builtin catalog completeness — only 8 functions modeled. `[inferred]`

### 6.2 Semantic / cross-module — project graph territory

**Moduletype & library graph (incl. both kinds of "loops"):**
20. **Loops — both kinds**: (a) moduletype-instantiation cycles — a moduletype
    whose body transitively instantiates itself → infinite expansion; (b)
    **library loops** — a library unit whose dependencies transitively loop
    back on itself. Real parser should detect both. `[user]`
    **Library-loop detection confirmed** `[user, 2026-10-01]`: loading
    `LoopA.x` emits `Library:LoopA reference removed to avoid loops`. So the
    real tool *does* break library cycles rather than erroring — a loop is a
    **recovery**, not a rejection. This is the one positive result in the
    project tier.
21. Self-instance (degenerate variant of 20a). `[model]`
22. **Moduletype not invoked where it is declared** (declared in
    `TYPEDEFINITIONS` but zero instances in its own unit/library). `[user]`
23. Instance references a moduletype name with no definition anywhere
    (`ModuleTypeInstance` is fully skipped today). `[model]`
24. Instance/param arity vs declared moduletype params (positional + named
    binding). `[model]` — **confirmed** `[user, 2026-10-01]`: a submodule
    invocation must sit in the **submodule list** (`SUBMODULES`, or bare in
    the module header position as `CtrlAcyc.x` does), **not** inside
    `LOCALVARIABLES`. `Prog.x` and `ProgBadDep.x` both place the instance in
    `LOCALVARIABLES` and are rejected (`Unexpected symbol or end of input` /
    `Error 76`). Ours rejects identically (`Unexpected token INVOCATION`).
25. Instance header form: `) : TypeName;` — a **type symbol** — is required
    after the coordinates. The inline `) : MODULEDEFINITION DateCode_ N` form
    is rejected with `AliasSym Expected` even with the terminator present.
    `[user, 2026-10-01]` This is what made `LoopA.x` / `LoopB.x` /
    `AuxLib.x` unusable (the `;` looked stray but was not — the *form* is
    wrong). Ours is lenient here and accepts the inline form.
26. Param-transfer typing (value vs formal param type — the
    `DurationInParameterMapping`/`GlobalParameterMapping` mechanism).
    **Confirmed** `[corpus]` — real rejects an incompatible variable supply
    verbatim: ``Submodule Child, parameter EnableFlag: Variable CounterValue
    is an invalid type`` (BadCrossMod.x). Implemented as **SL-V027** for the
    single-file case (module type declared in the same file); transfers into
    externally-declared module types, GLOBAL sources, and undeclared sources
    are skipped and stay consumer territory. `[inferred] → [corpus]`
27. GLOBAL-marked params/vars must have a matching declaration in scope.
    `[inferred]` — **tool-side confirmed** `[user, 2026-10-01]`, ours not:
    `EdgeGlobalParamMap.x` is rejected with `ControllerType GLOBAL GlobalBias
    not found at BasePicture:Ctrl`, the same shape as the `GlobalSetpoint`
    cluster. `GlobalBias` is a *second* symbol nobody declares, so the
    missing-symbol class now covers two names. Ours accepts.
28. ~~Formal param direction (`in`/`out`) matching~~ — **not checked** by the
    real parser. `[user]` — drop.

**Cross-file variable contracts:**
29. Referencing another program's variable — name/type/direction contract vs
    actual. `[corpus, consumer]`
30. Writes into a dependency's const/read-only external var. `[inferred]`
31. Ambiguous supply — a variable provided by two dependencies. `[inferred]`
32. Referencing an undeclared external variable (no supplier) — accepted
    today. `[corpus, consumer]`

**Dependency consistency:**
33. **Undeclared dependency used** (a file references a name not in its `.l` /
    `.z` dependency list) — probe. Note: the real parser does **not** detect a
    *declared-but-unused* dependency. `[inferred] / [user]`

**Scan groups / GroupConn:**
34. `( GroupConn = Var )` variable exists + is a `GroupData` variable; duplicate
    group connections; group var used elsewhere. `[inferred]` — existence part
    **confirmed** `[user, 2026-10-01]`: `EdgeScanGrpCl.x` writes
    `MODULEDEFINITION DateCode_ 1 (GroupConn=FastScan)` but declares only
    `InputA`/`OutputB`; the tool reports `"ScanGroup": Variable FastScan not
    declared`. Ours accepts. The *type* half (must be `GroupData`) and the
    duplicate/unused checks stay `[inferred]`.
35. `ScanGroupVar` declarations in moduletype bodies tied to the enclosing
    group. `[inferred]`

**Library hygiene:**
36. Declared-but-unused DATATYPE / variable. `[inferred]` — **prompt, not
    error** `[user, 2026-10-01]`: opening `ViolUndefBind.x` yields
    `ModuleType PumpType in ViolUndefBind is not used. Should it be removed?`
    The file still goes on to run, and the same session confirmed "all the
    remaining compile and go to run without warnings". So an unused module type
    is an interactive cleanup *question*, not a diagnostic — do not implement
    it as a validation error.

### 6.3 Graphics correlation — `sattline_parser.project` / consumer

37. **Date consistency**: the dates in the initial 3 header lines must match
    between the code file and the graphics file. `[user]` — **severity
    corrected 2026-10-01**: a mismatch is a **warning, not an error**.
    `ViolDateShift.x` (C-201 violation) shows
    `Composite object file has wrong date. Syntax errors and system crash can
    arise if this file is read. Continue?`; answering **yes** proceeds with no
    error and no crash. Ours accepts, which now matches. The C-201 group
    classifies as `not-enforced`. Keep any date check as a warning-level
    diagnostic at most — do **not** make it a hard reject.
38. **Composite-object count parity**: the number of composite objects in the
    code must equal the number in the graphics file. `[user]`
39. Graphic object bindings ↔ module defs; enable/invar tails resolving to
    declared vars. `[consumer/corpus]`

### 6.3a Tier-0 sweep result — 16 "valid" files the real tool REJECTS (2026-10-01)

The single largest finding so far. Every file below was written as a *valid*
construct and is `expected = accept` in the manifest, but the real tool
rejects it. Ours accepts 16 of the 19. These are **not** one bug: they are
**16 independent grammar gaps**, each needing its own probe + rule. The 3
remaining are the encoding cases we already reject correctly.

| Probe | Real diagnostic | Ours | Gap |
| --- | --- | --- | --- |
| `EdgeCmtInEq.x` | `SEQTRANSITION TrStart WAIT_FOR>>>(*<<< inline comment. Expression expected.` | accepts | a comment may not follow a bare `WAIT_FOR` expression |
| `EdgeDurVarFmt.x` | `>>>(*<<< Duration_Value. AliasSym Expected.` | accepts | duration value list may not be followed by a comment |
| `EdgeModDefNoTrail.x` | `>>><<< SemicolonSym Expected` | rejects | **RESOLVED 2026-10-02 (grammar *tightening*).** `[user]` re-confirmed. `SemicolonSym Expected` is a token-level expectation error, so unlike SL-V031/032/033 this is a grammar change, not a validator rule. `base_picture_module`'s trailing clause went from ENDDEF_KW + optional `;` to ENDDEF_KW + **required** `;`. Deliberately scoped: RECORD ENDDEFs and ScanGroup ENDDEFs keep their optional `;` - `UnCompressedFullGrammar.s` uses both and the real tool compiles it cleanly, so a blanket rule would have broken a known-good golden file |
| `EdgeOpSaveAndState.x` | `SavedStateVar: integer Opsave >>>State<<< Unknown error - unable to read error message file.` | accepts | `State` is illegal on a `Opsave` var; the tool cannot even render the message |
| `EdgeSeqAlt.x` | `>>>ALTERNATIVESEQ<<< EndLoopSeqSym Expected` | accepts | `ALTERNATIVESEQ` is not a standalone step |
| `EdgeSeqBrk.x` | `>>>SEQBREAK<<< Unexpected symbol or end of input` | accepts | `SEQBREAK` is not a step in this position |
| `EdgeSeqPar.x` | `>>>ENDSEQUENCE<<< Incorrect Syntax - Error 32` | rejects | **RESOLVED 2026-10-02 -> SL-V033.** The caret sits on `ENDSEQUENCE`, i.e. the body was unfinished: a closed sequence must close on a `SEQTRANSITION`, not a `SEQSTEP`. This is a missing *validation* rule, not a grammar defect - the grammar is correct |
| `EdgeCoordInvarTail.x` | `The expression is an invalid type Source + 1` | rejects | **RESOLVED 2026-10-01 -> SL-V032.** Type rule, not a ban on expressions: re-declaring the same tail with `Source` as real made the error disappear. Corner tails must be real-typed; the earlier "literals only" reading is disproven |
| `EdgeSubSeqDef.x` | `>>>ENDSEQUENCE<<< Incorrect Syntax - Error 32` | rejects | **RESOLVED 2026-10-02 -> SL-V033.** Same terminal-step cause: the outer body ends on a step. The nested sub-sequence body itself is legal |
| `EdgeTermSeqStep.x` | `>>>ENDSEQUENCE<<< Incorrect Syntax - Error 32` | rejects | **RESOLVED 2026-10-02 -> SL-V033.** The minimal isolated case for the same rule |
| `ValidComprSeqBasic.x` | `#22 MainSeq #01 >>>SeqControl<<<, SeqTimer). Incorrect Syntax - Error 33` | accepts | Error 33 = step number/order in a sequence header |
| `ValidCoordInVar.x` | `( 0.1 : InVar_ >>>PanelX<<< DefineSym Expected` | rejects | **RESOLVED 2026-10-01 -> §6.1-12.** `coord_invar_tail` narrowed to `(value \| litstring_tail)`; a bare name no longer parses. Scoped to the coordinate context only |
| `ValidGraphObjB.x` | `GraphObjects : >>>Layer_<<< 2 AliasSym Expected` | rejects | **RESOLVED 2026-10-01 as a grammar *removal*** — section-level `layer_info?` dropped from `graph_objects`. Reversible; see §6.4 |
| `ValidGraphObjEnabl.x` | `"DisplayValue">>>ValueFraction<<< AliasSym Expected` | accepts | a bare enable token may not follow a property name |
| `ValidInteractEnabl.x` | `>>>Enable_<<< = True: AliasSym Expected` | rejects | **RESOLVED 2026-10-01 as a grammar *removal*** — `enable_expression` dropped; only the `invar` form is legal. Reversible; see §6.4 |
| `ValidOpenSeqSeq.x` | `>>>ALTERNATIVEBRANCH<<< Incorrect Syntax - Error 32` | accepts | open sequence inside a branch is illegal |
| `ValidSubSeqTransB.x` | `>>>ALTERNATIVEBRANCH<<< Incorrect Syntax - Error 32` | accepts | `ALTERNATIVEBRANCH` in a sub-sequence transition |
| `EdgeUnicodeIdents.x` | `D>>>é<<<bit Incorrect Syntax - Error 76` | **rejects** | matched — Error 76 = illegal identifier char |
| `ValidComprFull.x` | `form>>>å<<<l Incorrect Syntax - Error 76` | **rejects** | matched |
| `ValidUnComprFull.x` | `form>>>å<<<. Incorrect Syntax - Error 76` | **rejects** | matched |

**Error-number glossary** (useful for reading raw messages):
`Error 32` = sequence body/scope rejected · `Error 33` = sequence step
header (number/order) · `Error 76` = illegal identifier character or reserved
word used as a name · `AliasSym Expected` = a type/symbol was required where a
literal appeared · `DefineSym Expected` = `:=`/definition required.

### 6.3b Second sweep — 7 more gaps, 1 new crasher, 6 rule confirmations

Same 2026-10-01 session, second batch. Of the 16 results, 6 close rule probes
and 10 land in Tier 0 / project territory.

**New rules confirmed, none of which we enforce:**

| Probe | real message | ours | rule |
| --- | --- | --- | --- |
| `ViolIntFromBool.x` (T1-001) | `Datatype error in assignment: Output = Flag1;` | accepts | bool→numeric assignment is illegal (§6.1-1) |
| `ViolRealVsBool.x` (T1-002) | `Only integer and real allowed for this operator X > Flag1` | accepts | comparison operands must be numeric (§6.1-2) |
| `ViolIntCond.x` (T1-003) | `Condition in IF-sentence is not boolean` | accepts | `IF` condition must be boolean (§6.1-3) |
| `EdgeBareDurZero.x` | `Only integer og real allowed for this operator ZeroDur == ZeroFull` | accepts | `duration` may not be compared (§6.1-2) |
| `EdgeNegDurVal.x` | `only integer and real allowed for this operator NegFive==NegHour` | accepts | same; negative durations are legal *declarations* |
| `ValidDurAndTime.x` | `only integer and real allowed for this operator: DurFull == DurBare` | accepts | same; all 10 duration/time initializer forms are fine |
| `EdgeScanGrpCl.x` | `Modul: "ScanGroup" : Variable FastScan not declared.` | accepts | **NOT A RULE - reclassified 2026-10-02.** `[user]` confirmed the file loads, warns and **runs**: the diagnostic is a compile-time *warning*, not a load-time error. The file is accepted and we were already right to accept it. The earlier "rejects" verdict came from reading the warning text as a rejection. Genuine open question is warning *severity*, not rejection - see §6.4 |
| `EdgeCoordInvarTail.x` | `The expression is an invalid type Source + 1` | rejects | **RESOLVED 2026-10-01 -> SL-V032.** Type rule, not a ban on expressions. Re-declaring the same tail with `Source` as real made the error disappear. Corner tails must be a coordinate position can never be an integer, so the tail must be
real-typed; rule (b) "literals only" disproven |

**The numeric-operand rule is one rule, not two.** `boolean` and `duration`
fail the *same* check, which is worth stating as a single type-class rule
(operands of `== != < <= > >= + - * /` must be integer/real) rather than a
per-datatype special case.

**Rules confirmed where we already agree** (no work): `ViolTooDeep.x`
(SL-V019), `ViolOldOnNonState.x` (SL-V006), `ViolBoolToReal.x` (SL-V027),
`ViolUndefBind.x` (C-104) — four probes reach `rule-confirmed`.

**New crasher: `EdgeFrameModInvoc.x`.** A frame-style module invocation kills
the GUI outright — no diagnostic, no dialog, nothing. That is now the 6th
`crashes-tool` entry and belongs in the open-alone list in `probes/README.md`.

**Still blocked on the missing symbol:** `ValidSubmodParams.x`,
`ViolDefScalLocVar.x` (T1-007), `ViolMissMap.x` (C-105) all die on
`GLOBAL GlobalSetpoint not found`, and `EdgeGlobalParamMap.x` on the *second*
missing name `GlobalBias`. Four probes cannot test their intended rule until
those two symbols exist.

**Non-finding worth recording:** the real tool asked
`ModuleType PumpType in ViolUndefBind is not used. Should it be removed?` and
then ran the file. Unused declarations are an interactive question, not a
diagnostic — do not implement §6.2-36 as an error.

**Consequence for the plan.** Each row above needs its own isolating Tier-0
probe and then a validator rule. Do **not** treat "the corpus accepted it" as
evidence of validity — this batch proves the flattened corpus carried 16
invalid constructs that we inherited.

`analyze.py` now splits these automatically via a `gap` field on every tier-0
row, derived from an `ours accepts` / `ours rejects` marker in the message cell:
`agree` (both sides as expected) · `we-too-lenient` (real rejects, we accept —
**the work queue**) · `we-too-strict` (real accepts, we reject — candidate
divergence) · `wrong-both` (both reject, agreement on an invalid file) ·
`unknown` (no marker recorded; never treated as agreement). Current counts:
**19 we-too-lenient, 11 we-too-strict, 7 wrong-both, 20 agree, 0 unknown.**

All 106 tier-0 files now carry an `ours` marker, so these counts are over the
whole survey rather than the 91 files that happened to have one. Filling the
last 15 moved `we-too-strict` 4 → 11 and `agree` 12 → 20, and left
`we-too-lenient` at 19.

The 11 `we-too-strict` rows are all the same kind of divergence — **a rule the
real tool does not enforce when it loads a file**:

- 7 newly surfaced, all with the identical real message *"compiles without
  errors (IDE refuses to create via editors; direct file load accepts)"*:
  SL-V009 `BadBareDurStr`, SL-V010 `BadBareTimeStr`, SL-V026
  `BadDatatypeShadows`, SL-V001 `BadDupDatatypeName`, SL-V002
  `BadDupModTypeName`, SL-V025 `BadDupRecFldName`, SL-V003 `BadDupVariaNames`.
  Two thirds of these are *duplicate-declaration* rules, which suggests the real
  tool checks uniqueness when it builds a library and not when it loads one.
- 4 pre-existing, from the §6.4 IDE-vs-compiler divergence: SL-V011, SL-V012,
  SL-V008, SL-V022.

The message itself names the distinction: the IDE refuses to *create* these
constructs, but loading the file is accepted. This package is a file parser, so
it is modelled against the load path — which makes us **stricter than the tool
on load, by design**. The right response is to keep the rules and document the
stage they belong to, not to delete them. Deleting them would be wrong twice
over: it would lose checks the build path does want, and it would do so on the
strength of one probe each. Do not "fix" these 11; they are the recorded
stage-scoped divergence from §6.4.

Two other facts from the same sweep:

- `BadBuiltinOutArg.x` is a **mis-targeted probe**, not a `we-too-strict` row.
  The real tool rejected it for an unrelated reason (*"Type error in
  if-sentence"*), so **SL-V014 is still unconfirmed** — neither proven nor
  disproven. Its three SL-V010 hits are incidental: the file initialises its
  time variables from bare strings, so it carries a second, unrelated defect.
  This is the `Bad*.x` twin of the broken `Ctrl*` templates, and it needs a
  rewrite before SL-V014 can be settled.
- `we-too-lenient` did **not** rise when the 15 markers were filled. All 15
  files were already being rejected, so no hidden grammar gap was sitting in
  them. The lenient backlog is genuinely the 19 listed in §11.
40. **Mechanics research** (not a rule — a deliverable): document how the
    `DateCode_` is generated and how it works, and how `.g`/`.y` files are
    paired with code, so the date-consistency and pairing rules above rest on
    understood internals. `[research]`

### 6.4 Reversal watchlist — implemented rules the real parser may contradict

| Rule | Finding driving the probe | Probe |
| --- | --- | --- |
| ~~SL-V022 `SFC_INIT_STEP_PLACEMENT`~~ | Unlimited `SEQINITSTEP`s allowed `[user]` | **closed 2026-10-01: hypothesis disproven, rule STANDS** — `ViolSecInit.x` rejected with `Error 32`; a second init step is not allowed |
| `Enable_` with an expression tail | Our grammar allowed `enable_expression` after `Enable_ =` `[inferred]` | **closed 2026-10-01 as a grammar *removal*** — `ValidInteractEnabl.x` rejected with `AliasSym Expected`, so only the `invar` form is legal. **Watch:** the `InVar_` form is *unproven*, not confirmed — the only file exercising it (`UnCompressedFullGrammar.s`) errored at line 71 on a non-ASCII identifier, 300 lines before reaching it |
| Section-level `Layer_` on `GraphObjects` | Our grammar allowed `layer_info?` there `[inferred]` | **closed 2026-10-01 as a grammar *removal*** — `ValidGraphObjB.x` rejected with `AliasSym Expected`. **Watch:** per-object `Layer_ = N` is unproven; no probe reaches it. Our own "full grammar" golden files are the only evidence and they are not real-tool validated |
| SL-V020 `UNKNOWN_DATATYPE_NAME` | `AnyType` is a legal (parameter-only) type `[user]` | feed `: AnyType` param, field, localvar |
| SFC accessor exemption (dotted `Step.X`) | accessors only legal when enabled for the sequence `[user]` | feed accessor with function disabled |

Both 2026-10-01 grammar removals share a failure mode worth naming: they were
**removals of syntax our own corpus had invented**, each driven by exactly one
probe. A removal is the risky direction — if the real tool does in fact accept
the form, we have introduced a false positive. Both are therefore on this
watchlist, and both removed forms are preserved as `invalid/` fixtures
(`EnableExpressionTail.s`, `GraphObjectsSectionLayer.s`) so the evidence is
reversible rather than lost. The cheapest confirmation is a probe that feeds
only the disputed construct, with no other novelty in the file.

**Resolved 2026-09-29 — documented divergence (kept strict).** The real
*compiler* accepts all seven of these constructs; the real *IDE* blocks every
one of them at edit time (e.g. the variables panel refuses to add a duplicated
name), so they only arise from hand-authored files. Per planning decision the
parser keeps the strict single-source checks as-is; these are recorded as
accepted divergence, not force-parity, until a consumer-layer context argues
otherwise:

| Rule(s) | Real behavior (probe) |
| --- | --- |
| SL-V001/002/003/025 duplicate names | compiles clean: `BadDupDatatypeName`, `BadDupModTypeName`, `BadDupVariaNames`, `BadDupRecFldName` |
| SL-V009/010 bare duration/time init | compiles clean: `BadBareDurStr`, `BadBareTimeStr` |
| SL-V026 `BUILTIN_DATATYPE_SHADOWED` | compiles clean: `BadDatatypeShadows` |

**Tier-0 survey over-rejects (observed 2026-10-01, kept strict).** Four rules
are contradicted by the *compiler* with no IDE involvement at all — the files
compile clean, so these are plain over-rejects, not editor artifacts:

| Rule | Probe | Real behavior | Ours |
| --- | --- | --- | --- |
| SL-V008 `INIT_VALUE_TYPE_MISMATCH` | `BadInitValType.x` | compiles without warnings | rejects (`str` init for an `integer`) |
| SL-V011 `MALFORMED_DURATION_LITERAL` | `BadDurLit.x` | compiles without warnings | rejects (`'not-a-duration'`) |
| SL-V012 (time literal) | `BadTimeLit.x` | compiles without warnings | rejects |
| SL-V022 `SFC_INIT_STEP_PLACEMENT` | `BadSfcInitStepNot.x` | complies without warnings | rejects (init not first) |

All four are on the analyzer's reversal watchlist (`WATCHLIST` in
`scripts/probe/analyze.py`), so the snapshot reports `rev: 4` for them. Like the
seven rows above, the rules stay strict until a consumer-layer context argues
otherwise — but unlike those, no IDE guard exists to catch them, so a
hand-authored file with a mistyped duration or time literal, a quoted integer
initializer, or a sequence whose init is not first is silently accepted by the
real compiler. These four are the strongest candidates for a future
*force-parity* decision. SL-V022 is the widest gap: the real compiler accepts an
init step anywhere in a sequence, while we reject any placement but the first.

**Confirmed parity (2026-10-01, tier-0).** Seven rejects match ours, most with
the same line and token:

| Probe | Real message | Ours |
| --- | --- | --- |
| `BadFreeCmtInMod.x` | `line 21 >>>(*<<< This comment. AliasSym Expected.` | rejects, same line |
| `BadGraphObjDouble.x` | `line 15. GraphObjects: >>>Layer_<<< = 2 Layer_ = 3. ... AliasSym expected.` | rejects, same line |
| `BadSeqForkUnknown.x` | `line 30: >>>SEQBREAK<<< Unexpected symbol or end of input.` | SL-V017 |
| `BadSfcAltBrStart.x` | `line 26: >>>ALTERNATIVESEQ<<< EngLoopSeqSym Expected.` | SL-V023 |
| `BadSfcParBrStart.x` | `line 26 >>>SEQTRANSITION<<< Incorrect syntax - Error 29` | SL-V024 |
| `BadUntermCmt.x` | `line 15: >>><<< AliasSymExpected` | rejects at line 15 |
| `BadUndefVariaRef.x` | `BasePicture variable not defined: Ghost` | SL-V019 |
| `BadUnknownDatatype.x` | `Zzzyx` not found; dialog: replace type / open new library / delete object / abort | SL-V020 |
| `BadWriteToConst.x` | `Modul: …:BasePicture value cannot be changed: MaxLimit` | SL-V007 |

**SL-V015 confirmed with a verbatim message (2026-10-01).** `BadStrLitInCall.x`
is rejected by the real compiler with the caret on the literal itself:

```
Error on line 23 IsMatch = EqualStrings(Input, ">>>Expected<<<", True); Expression expected
```

So a string literal as a call argument really is illegal — "Expression expected"
is the real parser's wording. This upgrades the §6.1 item 4a note from a
user-reported rule to a probe-backed one; our SL-V015 rejects the same file at
the same column. Note the real tool names the *first* offending literal only, so
one diagnostic per call is the parity target.

**Missing-symbol class — 4 probes are untestable (2026-10-01).** The real tool
rejected three *controls* with `ControllerType GLOBAL GlobalSetpoint not found`:
`CtrlDefParam.x`, `CtrlFullArity.x`, `CtrlTypedXfer.x`. Ours accepts all three
cleanly. The cause is a gap in the probe set, not in either parser: nine files
reference the module type `ControllerType` and the `GLOBAL GlobalSetpoint`
`GlobalSetpoint` variable, but **no file in `probes/` ever declares
`GlobalSetpoint`** — the corpus file `GlobalParamMap.s` declared the type in
its own `TYPEDEFINITIONS`, and the flattening kept only the usage half. Several
of the nine files *do* declare `ControllerType` themselves (e.g.
`CtrlDefParam.x` has `ControllerType = MODULEDEFINITION DateCode_ 1` in
`TYPEDEFINITIONS`); the tool's message names both symbols but the one that is
actually unresolvable is `GlobalSetpoint`. Our grammar has no syntax for
declaring a GLOBAL variable at all, so the symbol can only come from the tool's
environment — and `probes.z`, the only dependency every other `.z` declares,
does not provide it.

| Probe | Id | Consequence |
| --- | --- | --- |
| `AnyTypeParam.x`, `AnyTypeLocVar.x` | T1-006 | the AnyType rule is **untested** — the earlier "real rejects AnyType as a parameter/localvar" reading is **retracted**; the file died on the missing symbol first |
| `CtrlDefParam.x` | T1-007 | `template-broken` |
| `CtrlFullArity.x` | C-105 | `template-broken` |
| `CtrlTypedXfer.x` | C-106 | `template-broken` |
| `ViolBoolToReal.x`, `ViolMissMap.x`, `ValidSubmodParams.x`, `ViolDefScalLocVar.x` | C-106, C-105, T1-007, T1-007 | will fail identically until the symbols exist |

All four affected probe ids classify as `template-broken` in the snapshot, and
the analyzer now checks a rejected control *before* the pending check so a broken
control cannot hide behind an unanswered violation. Fixing this needs a library
unit that declares `ControllerType` and `GlobalSetpoint` (or self-contained
rewrites of the nine files that declare the type locally, as `EdgeGlobalParamMap.x`
already does); the exact library syntax is not in our grammar, so it must come
from the real tool.

**The 22 controls are otherwise sound.** The other 19 controls all
`loads without warnings` on the real tool and validate clean for us, so every
paired probe except the four above now has a working template.

**Tool-crash class (observed 2026-10-01).** A crash is a third, *terminal*
outcome — neither accept nor reject — and is recorded as `crashes-tool` in the
transcript and the snapshot; `analyze.py` must never fold it into `pending`
(that would hide a known, reproducible result). Five probes now sit in this
class, and the transcript marks them `crash` or `stall`:

| Probe | Real outcome | Ours |
| --- | --- | --- |
| `BadEncodingStress.x` | crashes on open | rejects (`SEMICOLON` expected at line 14) |
| `BadMalformed.x` | crashes on open | rejects (line 1, expected `STRING`) |
| `BadModCodeWithMod.x` | crashes on open | rejects (line 13, bare `ModuleCode`) |
| `BadNotSattLine.x` | crashes on open | rejects (line 1, plain text) |
| `BadOversizeInput.x` | **stalls, never loads** | rejects (line 51, `Real_Value`) |

`BadEncodingStress.x` crashes the real IDE **on open**, with no diagnostic.
Despite its name the file is **pure ASCII**, so the crash is not an encoding
effect: lines 1-3 are placeholder header lines (`"SyntaxVersion"`) instead of
a real `"Syntax version …, date: … N"` line, and line 13 is a truncated
expression (`Var1 = Var2 +`). Our parser rejects the same file cleanly — the
behavior the strict, no-fallback Windows-1252 decode exists to guarantee: fail
loudly on a malformed file rather than guessing an encoding.

The three new crashers share one trait: they are files the real tool cannot
salvage at all. `BadMalformed.x` and `BadNotSattLine.x` have no header line
whatsoever, and `BadModCodeWithMod.x` is a bare `ModuleCode` with no
`ModuleDef` — a missing-header or missing-`ModuleDef` file takes the IDE down
rather than producing a diagnostic. `BadOversizeInput.x` is only 1652 bytes, so
its stall is **not** a size limit; the file stalls before any parse result,
which makes it unusable as a size probe — treat it as a tool-robustness
observation, not an encoding/size finding. Consequence for the probe set: a
crasher kills the whole GUI session, so crash-prone probes must not be batched
together, and a stall needs its own session with a manual kill.

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
  snapshot with zero unexplained mismatches — where "explained" means every
  `we-too-lenient` row has become a rule or a corrected probe, and every
  `we-too-strict` row is a recorded divergence;
- every defective probe template is either fixed or explicitly retired, so no
  snapshot verdict rests on a construct the real tool cannot represent.

---

## 11. Current state — 2026-10-02

| | count |
| --- | --- |
| transcript rows | 167 |
| tier-0 files surveyed | 110 |
| `confirmed` | 34 |
| `crashes-tool` | 6 |
| `not-enforced` | 1 |
| `rule-confirmed` | 6 |
| `surprise-reject` | 1 |
| `template-broken` | 4 |
| `survey-mismatch` (tier-0) | 20 |
| `survey-surprise` (tier-0) | 11 |
| `pending` | 59 |

Tier-0 versus our own parser: **8 we-too-lenient**, 11 we-too-strict (all
documented stage-scoped divergences — §6.3), 8 wrong-both, 31 agree,
**0 unknown** (all 110 files carry a marker).

**Three validation rules landed since the previous revision of this section:**
`SL-V031 ATTRIBUTE_COMBINATION_INVALID` (the `OpSave + State` pair, §6.1-11),
`SL-V032 COORDINATE_NOT_REAL` (§6.1-13) and `SL-V033 SEQUENCE_ENDS_WITH_STEP`
(§6.1-14), plus the `coord_invar_tail` grammar narrowing (§6.1-12). Together
with SL-V028/029/030 they moved `we-too-lenient` 23 → 11 and `agree` 20 → 27
over two sessions. `ValidSeqBasic.x` was confirmed by the user and no longer
sits pending.

**Still outstanding at this revision** — carried into the release as known gaps
rather than defects:
* 8 `we-too-lenient` rows, each needing one probe apiece: `EdgeSeqAlt`,
  `EdgeSeqBrk`, `ValidComprSeqBasic`, `ValidGraphObjEnabl`,
  `ValidOpenSeqSeq`, `ValidSubSeqTransB`.
* `EdgeCmtInEq` / `EdgeDurVarFmt` came off this list on 2026-10-02 as a
  **reversal**, not a missing rule — see §6.3d. The reserved-name
  re-declaration gap (§6.1-18) came off earlier the same day with SL-V034;
  it was the only entry already `[corpus]`-confirmed, which is why it needed
  no new probe.
* `EdgeScanGrpCl.x` came off this list on 2026-10-02: `[user]` established that
  an undeclared `GroupConn=` target is a compile-time **warning** on a file that
  still loads and runs, so no rejection rule is owed. Whether we should surface
  it as `DiagnosticSeverity.WARNING` is an open *design* question, not a parity
  gap — it is deliberately not implemented, because emitting it would add a
  diagnostic to a file the real tool accepts, and every current consumer treats
  any diagnostic as failure.
* `EdgeModDefTrail.x` is the queued **positive control** for the ENDDEF rule. The
  negative case is `[corpus]`, but "the terminated form is accepted" is only
  `[inferred]` from the diagnostic text. If the tool *rejects* `ENDDEF;` too, the
  trailing clause should be dropped entirely instead of tightened — the fixtures
  and grammar change are reversible for exactly that reason.
* 4 probes cannot test their intended rule until `GlobalSetpoint` and
  `GlobalBias` exist (§6.3b).
* `HighByteValid.x` / `HighByteInvalid.x` still need a real run (open the
  invalid one alone).
* §6.4 watchlist unresolved: SL-V020 vs `AnyType`, and the SFC accessor
  namespace. The two grammar removals remain reversible pending single-construct
  probes of the `Enable_` `InVar_` form and per-object `Layer_`.
* **`PARITY.md` does not exist yet** — it is listed as a deliverable in §7 and
  is required by §10. Until it is written, no rule has the single
  rule × status × real-message matrix the definition of done asks for.

Two more closed this session, both **grammar removals** rather than new
validator rules, and both on the §6.4 watchlist because a removal driven by a
single probe is the risky direction:

- `Enable_` no longer accepts a parenthesised expression tail
  (`enable_expression` dropped from `enable`). `ValidInteractEnabl.x` was
  rejected with `AliasSym Expected`. The *assignment* directive still accepts
  `(expr)`, so the restriction is specific to `Enable_`.
- `GraphObjects` no longer accepts a section-level `Layer_ = N` clause
  (`layer_info?` dropped from `graph_objects`). `ValidGraphObjB.x` was rejected
  with `AliasSym Expected`. Per-object `Layer_` is untouched.

Both removals were **syntax our own corpus had invented**, so fixing them meant
correcting four fixtures whose premise was wrong rather than adding coverage:
`valid/GraphObjectsSectionLayer.s` moved to `invalid/` (it asserted a
propagation feature that cannot exist), `valid/InteractEnableTails.s` lost the
rejected line, and both copies of the compressed/uncompressed full-grammar
golden files were changed in step so they stay equivalent. `we-too-lenient`
19 → 17 and `wrong-both` 7 → 9, the latter because the real tool and we now
agree those two files are invalid.

Of the 7 `wrong-both`, 4 (`EdgeBareDurZero.x`, `EdgeDurVarFmt.x`,
`EdgeNegDurVal.x`, `ValidDurAndTime.x`) are now **agreements with the real
tool**: both reject them, and the "wrong" part is our expectation, not our
parser. They were authored as expected-accept, but each one compares two
durations, which the real parser forbids. The remaining 3
(`EdgeUnicodeIdents.x`, `ValidComprFull.x`, `ValidUnComprFull.x`) are the
non-ASCII identifier gap.

Resolved this session: SL-V022 **stands** (item 14 disproven); date mismatch is a
**warning, not an error** (§6.3 item 37); reserved-name re-declaration is a real
**gap in us**, not a reversal (item 18); library loops are **broken, not
rejected** (item 20); submodule invocation placement and header form are now
specified (items 24-25); unused declarations are a **question, not an error**
(item 36); the `GlobalSetpoint` wording is corrected (§6.2).

**Expression typing is now implemented.** The three rules confirmed in §6.1
items 1-3 ship as `SL-V028 OPERAND_NOT_NUMERIC`, `SL-V029
ASSIGNMENT_TYPE_MISMATCH` and `SL-V030 CONDITION_NOT_BOOLEAN`, backed by
`src/sattline_parser/validation/typing.py`. Inferring types means we reject 4
more tier-0 files, so `we-too-lenient` fell 23 → 19. Each rule is deliberately
permissive where the probes were silent: builtin call results, record-typed
values and mixed-branch ternaries are all unproven and stay unflagged, and
`real` into `integer` is *not* rejected because no probe covers it.

Enforcing these rules exposed **four wrong expectations in our own corpus**:
`valid/DurationAndTime.s`, `edge_cases/BareDurationZero.s`,
`edge_cases/DurationVariousFormats.s` and `edge_cases/NegativeDurationValue.s`
all declared duration/time variables and then compared them, which the real
parser rejects. Each file's actual purpose is declaration coverage, which the
real tool *does* accept, so the illegal comparison was removed and the finding
recorded in the fixture header rather than by moving the file to `invalid/`.

Six probes reach `rule-confirmed` where
we already agree, which is the good news: SL-V006, SL-V019, SL-V027 and the
C-104 moduletype rule all held up.

Two probe files still need a real run before they can leave `pending`:
`HighByteValid.x` and `HighByteInvalid.x` (open the invalid one alone).

---

*Last updated: 2026-10-02*


### 6.3d Comment placement is a grammar concern — two clauses removed (2026-10-02)

`EdgeCmtInEq.x` (`WAIT_FOR` then `(* ... *)` then the expression →
`Expression expected`) and `EdgeDurVarFmt.x` (a comment as the first item of
`LOCALVARIABLES` → `AliasSym Expected`) were filed as unimplemented gaps. They
were not missing rules. Both are **reversals**: the grammar had been written to
*invite* exactly the constructs the real tool rejects.

```
-variable_list:   (comments | variable_group)+
+variable_list:   variable_group+
-seqtransition:   SEQTRANSITION NAME? WAIT_FOR comments? expression
+seqtransition:   SEQTRANSITION NAME? WAIT_FOR expression
```

Why these two clauses were the anomaly: `variable_list` was the **only** place a
bare comment was admitted as a declaration-list item. Every other comment
position in the grammar uses `code_comment`, and only inside *code* lists —
`entercode`, `activecode`, `exitcode`, `equationblock`, `sequence_body`,
`if_statement`. So the grammar already encoded "comments live inside code
blocks"; the two `comments` opt-ins contradicted that. Removing them makes the
grammar *consistent* rather than adding a concept.

Consequences handled:
- `edge_cases/CommentInsideEquation.s` had `inline comment is stripped` baked
  into a `SEQTRANSITION` — the fixture asserted our own bug. The comment now
  sits between sequence elements, where `sequence_body` still allows it.
- `edge_cases/DurationVariousFormats.s` had a section comment inside its
  variable list. A bare comment is not legal before `LOCALVARIABLES` either, so
  the three group labels moved into the file header.
- `test_record_and_moduletype_definition_capture_role_comments` carried an
  unasserted comment in a `RECORD` variable list; removed. Its real assertions
  (record `trailing_comments`, moduletype `description_comments`) are untouched.
- **Zero `corpus/valid/` golden files depend on either clause.** No AST change.

### 6.3e Encoding and reserved-name questions closed (2026-10-02 / 2026-10-05)

Four user GUI runs closed four open questions, all in our favour:

| Probe | Result | Settles |
| --- | --- | --- |
| `EdgeAsciiIdent.x` | opened without issues | cp1252 high bytes are legal in an **identifier**. The ASCII-only hypothesis was wrong; our `NAME` rule (`\p{L}`, `constants.py:257`) is correct. |
| `HighByteValid.x` | compiles | cp1252 high bytes are legal in a **comment**. Encoding picture complete - no encoding rule needed anywhere. |
| `EdgeModDefTrail.x` | compiles | `ENDDEF;` (semicolon **required** when ENDDEF is present) is accepted, confirming the `base_picture_module` narrowing. Evidence-backed in both directions with `EdgeModDefNoTrail.x`. |
| `ViolVarGroup.x` | parses | Declaring a **variable** named `GroupData` is legal, confirming the deliberate exclusion of `GroupData` from the SL-V034 reserved set. `On`/`Off` are reserved runtime constants; `GroupData` is not. |

**Environment-blocked, not parity gaps.** `ValidSubmodParams.x` and
`EdgeGlobalParamMap.x` fail only on `ControllerType GLOBAL GlobalSetpoint` /
`GlobalBias`, which the user confirmed do not exist in their installation. They
can never load here regardless of grammar, so they are now tagged
`ENVIRONMENT-BLOCKED` and excluded from the tier-0 tally by
`analyze.ENVIRONMENT_BLOCKED_MARKERS` instead of inflating `we-too-lenient`.

**Encoding defect in two probes (not a language rule).** `ValidUnComprFull.x`
and `ValidComprFull.x` were saved as **UTF-8**, not cp1252: they contained byte
`0x86` (undefined in Windows-1252), and read as cp1252 their `formål` became
`formÃ¥l` with a `¥` currency symbol where a letter was required. That is exactly
the recorded `Error 76` - our own encoding failure reproducing the tool's. Both
have been re-encoded to cp1252. Note the corpus twins
`valid/UnCompressedFullGrammar.s` / `valid/CompressedFullGrammar.s` were always
correct cp1252 and parse with zero diagnostics; no tool result was ever recorded
against them. After re-encoding, both probes hit a *separate*, still-open
construct - the graph-object enable tail `Enable_ = True : ( ... )` - so they
remain blocked pending that question.

Two consequences worth carrying forward:

1. `EdgeDurVarFmt.x`'s *stated* subject is duration-literal formats, which the
   real tool **never reached** — it died on the comment at line 15. That probe is
   evidence about comment placement and says nothing about duration forms. The
   duration question is still open and needs a fresh probe.
2. `edge_cases/UnicodeIdentifiers.s` is a **UTF-8** file living in a cp1252
   corpus. It only survives because the *test* loader reads UTF-8 first while the
   public API enforces strict cp1252. Unrelated to this change — it fails
   identically either way — but it is a latent trap.
