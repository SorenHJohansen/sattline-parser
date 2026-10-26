# Finishing the parity work — plan built on `SattLine_Parser_AI_Handoff`

Status: proposal, 2026-10-26. Companion to `PARITY_PLAN.md` (§6 = the frontier,
§10 = definition of done) and `SattLine_Parser_AI_Handoff/` (native evidence).
**B4.1 (scanner token table) is implemented**; native answers 1–13 are folded in
below and supersede the open questions they answer.

## Landed 2026-10-26 (this pass)

| Item | Where | Evidence |
| --- | --- | --- |
| B4.1 scanner table (206 entries) | `preprocessing/scanner_tokens.json`, `SCANNER_TOKENS` | `.SCANNER` enum, SHA-256 pinned; twin-equivalence test |
| B1.1 fork/break suffix | grammar `seqfork?` on step/transition; `SFCFork.has_break`; `SFCBreak` removed | `006f9850`, `0070a100`, `0070d180` |
| B1.2 S/T/M position model | `validation/sequences.py`, `SL-V036`, reuses V016/V023/V024/V033 | `00625d20`, `00708d20`, `0070db70`, `0070be80`, `0070bcb0`, `0070b440`, `0070cf20` |
| B1.3 optional sub names | grammar; `SFCSubsequence.kind` | `00708b40`, `0070ba70` |
| B2.1 unguarded transition | `condition: SLExpression \| None` | `0070d180`, `006fad30` |
| B2.2/B2.3 DateCode | optional attribute, fixed keyword, `BasePicture.datecode` | `005ab1b0`, `005d6170`, `005ccaa0`, `005dc3f0` |
| B2.4 stamp helpers | `validation/datecode.py` | DATE-01/DATE-02 |
| B2.5 optional semicolons | grammar `statement` | `0072b660` |
| B3.1 `:Old` write | `SL-V035` | `00485470`, `004748b0` |
| B3.2 CP1252 identity | `validation/names.py`, wired through `validation/` | `00806168`, `005b5290` |

Corpus fixtures that encoded the rejected shapes were corrected:
`edge_cases/SeqBreak.s` (rewritten as a fork flag), new
`invalid/StandaloneSeqBreak.s`, `edge_cases/SequenceAlternative.s`,
`valid/SubSeqTransitionAlt.s`, `valid/OpenSequenceSeqFork.s`,
`invalid/SeqForkUnknownTarget.s`.

Still open: B0.1/B0.2 (handoff pinning, report refresh), B3.3 (builtin
catalogue), B4.2 (regenerate compressed probes through a compressor),
B4.3 (message resources), B5 (loader profile), B6 (corpus honesty markers),
`PARITY.md`.

Objective, restated so the two halves of the project stop competing:

> We accept a file **only if** the real SattLine tool's compiler accepts it.
> We must reject every construct the real tool refuses to compile or load.
> Editor/UI guards do **not** count as rejections (already retired: SL-V001/2/3/8/9/10/11/12/22/25/26).
> Runtime and simulation behaviour is out of scope for this plan.

## 0. Baseline (verified 2026-10-26)

| Item | Value |
| --- | --- |
| Host | `kontorpc`, branch `validation-stage`, HEAD `ee33255` + uncommitted work |
| Parser tests | `pytest tests/parser` → 374 passed |
| Last parity snapshot | `tests/real/reports/2026-10-05-2026.10.05-batch.json` (122 tier-0 rows) |
| Tier-0 gaps | 8 `we-too-lenient`, 1 `we-too-strict`, 19 `wrong-both` (mostly retired/encoding), 5 pending |
| Handoff snapshot | `target_parser/` = sattline-parser **2026.9.2**, i.e. *older* than this checkout (no `validation/` package) |
| Handoff gaps | P01–P12 in `knowledge/parser_gap_matrix.json`, claims in `knowledge/claims.json` |
| Conflict to resolve | handoff says Python 3.13/deps unavailable; here they are, so all handoff "static-only" reasoning can be executed |

The `target_parser/` snapshot is **not** the integration target anymore. Use it
only to see what the reviewer was looking at; the `P0x` line numbers no longer
match. The `validation/` package (SL-V001…V034) did not exist in the snapshot, so
every semantic item (P09, P12) must be re-derived against the current tree.

## 1. Two evidence streams, one oracle

| Stream | Strength | Weakness |
| --- | --- | --- |
| GUI probe verdict (`probes/` → `TRANSCRIPT.md`) | *the* accept/reject oracle, end-to-end, includes loader | human session, one file at a time, 6 crash rows, 3 environment-blocked rows |
| Native static (handoff claims, decompiled C) | explains *why*, reaches loader/stamp/scanner detail the GUI can't show, proposes gaps nobody has probed | version-specific; decompiler artefacts; cannot by itself prove a compile verdict |

Rules for using them:

1. **Static evidence proposes, a probe disposes.** A grammar or validator change
   lands with (a) a probe verdict, or (b) a named native routine address, recorded
   in the rule docstring and in `PARITY.md`. Where the address is indirect (a
   dispatcher, or a claim not traced to a single check), the rule carries an
   explicit `UNPROBED` label and a control unit in the next session.
2. **Every tightening needs a control.** A "we too lenient" fix ships with the
   matching accepted control in the same probe unit, so a fix cannot become the
   next `Enable_`/`Layer_` over-restriction.
3. **Both directions count.** `we-too-strict` rows are as damaging as
   `we-too-lenient` ones (P01/P03 are exactly that shape) and are cheaper to fix.
4. **No new invented grammar.** Any construct our corpus asserts that the real
   tool has never seen gets marked, not promoted to spec (see B6).

## 2. Scope rings

* **Ring A — rejection parity, intra-file.** Grammar + `validation/`. This is the
  stated goal; everything in B1–B4 serves it.
* **Ring B — AST/metadata fidelity.** Only what a later rule needs (DateCode
  presence, quoted identifiers, spans, State suffix). No gratuitous reshaping.
* **Ring C — project load parity.** Body/sidecar pairing, Windows path algebra,
  lookup order, missing-sidecar errors (B5). Still rejection parity, different
  layer: a library the real tool refuses to load is a project that cannot compile.
* **Out of scope.** Runtime/simulation: STATE-03 transfer, NUM-01 int32/binary32,
  TIMER-01, SCHED-01, SCAN-01, equation masks, builtin bodies. The handoff's
  `acceptance_cases.json` marks 12 cases `layer: runtime|scheduler|constant_folding`
  — leave them unimplemented here and say so.

## 3. Work batches

Each batch is a branch + PR (repo rule: never commit to `main`), validated once at
the end (`pytest`, ruff, pyright) as the handoff and `AGENTS.md` both ask.

### B0 — Re-baseline and pin the evidence (0.5 day, no behaviour change)

1. Run `python tools/validate_handoff.py` once; record the handoff tree hash,
   `target_parser` snapshot hash and `main.exe` SHA-256 from
   `knowledge/provenance.json` into `docs/handoff-provenance.md`.
2. Re-run `scripts/probe/analyze.py` against the unchanged transcript to refresh
   the snapshot. Expect at least one stale row: `EdgePropEnable.x` is still
   listed `we-too-strict` although `enable` now takes an optional tail
   (`grammar/sattline.lark:207`). Add a test that the newest report equals a
   fresh analysis of the committed transcript, so reports cannot drift silently.
3. Vendor the handoff selectively: 74 MB of decompiled C does not belong in the
   repo. Commit `MANIFEST.json`, `knowledge/*.json` (minus
   `snapshot_comparison.json`), `docs/*.md`, `tools/`, and gitignore
   `references/` + `target_parser/`, pinned by hash.
4. Write `docs/handoff-claims.md`: claim id → the repo rule / probe / test that
   relies on it. One table, so a future reversal of native evidence is findable.

**Exit:** `docs/handoff-provenance.md`, refreshed report, drift test, claim map.

### B1 — Sequence shape parity (≈2 days; native SEQ-01..04, gaps P02+P07)

**Settled natively 2026-10-26** (`00625d20` starter sets, `00708d20`, `007089a0`,
`0070db70`, `0070be80`, `0070bcb0`, `0070b440`, `0070cf20`). Sequence elements
occupy one of three positions, and the body productions are:

```ebnf
S  = SEQINITSTEP | SEQSTEP | SUBSEQSTEP | PARALLELSEQ          (* step position *)
T  = SEQTRANSITION | SUBSEQTRANSITION | ALTERNATIVESEQ         (* transition position *)
M  = SUBSEQUENCE                                              (* structural *)

closed_body     = (S T | M)+ ;                                 (* SEQUENCE, SUBSEQUENCE *)
transition_body = T (S T | M)* ;                               (* each alternative branch, SUBSEQTRANSITION *)
step_body       = M* S (T M* S)* ;                             (* each parallel branch, SUBSEQSTEP *)
```

`OPENSEQUENCE` additionally allows incomplete endpoints but must stay non-empty:

```ebnf
open_body = S after_step | T after_boundary | M after_boundary ;
after_step = empty | T after_boundary ;
after_boundary = empty | M after_boundary | S after_step ;
```

Consequences: `ALTERNATIVESEQ` occupies **T** (so `EdgeSeqAlt` was rejected
because it sat after a transition), `PARALLELSEQ` occupies **S**, `SEQFORK` is a
suffix of its host step/transition, empty groups and empty branches are illegal,
and structural `SUBSEQUENCE` (M) is not an arbitrary nested `SEQUENCE`.

* **B1.1 Fork/break suffix.** `SEQFORK NAME ("," NAME)* [SEQBREAK]` is a suffix of
  an ordinary **step or transition** (`006f9850`, `0070a100`, `0070d180`), never a
  free-standing element. Restructure the grammar: `seqstep: SEQSTEP NAME? code_blocks seqfork?`,
  `seqtransition: SEQTRANSITION NAME? guard? seqfork?`; delete the standalone
  `seqbreak` production and `seq_element` membership. AST: `SFCFork.break`,
  `seqfork` attached to its host node; `SFCBreak` retired. Update
  `_sfc_mixin`, `formatter.py:220`, `SL-V017`, fixtures
  (`edge_cases/SeqBreak.s` → `invalid/StandaloneSeqBreak.s`, new
  `valid/SequenceForkBreak.s`), and the full-grammar twins.
* **B1.2 Encode the productions.** Replace the loose
  `sequence_body: (code_comment | seq_element | ...)*` shape with per-context
  productions (`closed_body`, `open_body`, `transition_body`, `step_body`) so the
  tool's parse-time failures happen at parse time. `SL-V023`/`SL-V024` then
  become grammar-enforced for the shapes above and stay only as belt-and-braces
  for what the grammar cannot express. Branch count: **at least two, no maximum**
  (`00703970`).
* **B1.3 Names are optional** on `SUBSEQSTEP` and `SUBSEQUENCE`
  (`0070ba70`, `00708b40`), while our grammar requires them — a *false reject*.
  Fix in the same breath as B1.2.
* Corpus files that encode invented shapes (`valid/SequenceAlternative.s`,
  `valid/SubSeqTransitionAlt.s`, `valid/OpenSequenceSeqFork.s`, both full-grammar
  goldens) are corrected against the productions above, not against our old guess.

**Exit:** `EdgeSeqBrk`, `EdgeSeqAlt`, `ValidOpenSeqSeq`, `ValidSubSeqTransB` reach
`agree`; SEQ-01..04 have grammar tests including the negative shapes.

### B2 — Optional-element tolerance (≈1 day; native SEQ-02/03, DATE-01/03, gaps P01+P03)

Accept-direction changes: today we falsely reject several constructs.
All are confirmed natively (2026-10-26), so no GUI session is needed first.

* **B2.1 Unguarded transition** (`0070d180`, `006fad30`):
  `SEQTRANSITION [NAME] [WAIT_FOR expression]`, where an absent guard lowers to
  true. `_sfc_mixin.seqtransition` + `SFCTransition.condition: SLExpression | None`
  (formatter omits `WAIT_FOR`); tests for unnamed/named/guarded/`WAIT_FOR False`.
* **B2.2 Optional DateCode** at `record`, `moduletype_definition`,
  `invocation_new_module`, `base_picture_module` (`005d6170`, `005ccaa0`,
  `005dc3f0`). AST fields are already `int | None`; only the grammar forces the
  stamp. Preserve `None`; never inject a clock (DATE-03 is an import step).
* **B2.3 `DateCode_` is a fixed keyword, not `NAME` + integer** (`005ab1b0`
  requires scanner token `0x89`, ordinal 137). Tighten `sl_datecode` so
  `Bogus_ 5` is rejected — today we accept it.
* **B2.4 Raw vs normalized stamp.** Keep the source integer in the AST; add
  `validation/datecode.py` (`normalized_datecode(n)`, non-negative
  `n % 2_000_000_000`, signed case documented but not guessed) and cover
  `date-preserve` / `date-modulus` acceptance cases. No AST mutation, no clock.
* **B2.5 Statement semicolons are optional** (`0072b660`). Our
  `statement: assignment_statement ";" | ...` requires them, so we reject files
  the compiler accepts. Make the terminator optional in `entercode`/`activecode`/
  `exitcode`/`if_statement` bodies, keep it optional-but-legal in equations, and
  add both directions as fixtures.

**Exit:** those constructs no longer rejected by us; each has a grammar test and
a control unit in the next GUI session; `we-too-strict` = 0.

### B3 — Semantic rejections still missing (≈2 days; STATE-02, NAMES-01/02, gaps P06+P09+P12)

All three are confirmed natively as **compiler** checks (not editor guards).

* **B3.1 Writing `:Old`.** `00485470` (called by statement analysis) rejects
  `:Old` assignment targets with expression-node error `0x14`/20, non-State
  suffixes with `0x13`, and reference-required arguments selecting Old/Der/Der2
  likewise (`004748b0`). Today `_check_old_new` (`validation/code.py:322`) only
  checks that a suffix sits on a State symbol, so `Count:Old = 0` passes. Add
  `SL-V035 OLD_STATE_NOT_WRITABLE` covering assignment LHS, builtin out positions
  (reuse SL-V014's writability predicate) and out-arg calls; keep syntax
  untouched. Module-type transfers travel a different route (`005d0350 →
  0059bb30 → 005de7d0`) whose reference production is a dotted NAME path with no
  colon suffix, so `:Old` there is a grammar-level question, not this rule.
* **B3.2 Identifier identity (CP1252 byte table).** Native lookup folds through
  the upper-byte table at `00806168`: `a–z → A–Z`, `0x9A→0x8A`, `0x9C→0x8C`,
  `0xE0–0xF6 → 0xC0–0xD6`, `0xF8–0xFE → 0xD8–0xDE`, `0xFF→0x9F`; everything else
  is identity. `0xDF (ß)` does **not** fold, so `ß`/`ss` must not match, and
  `œ`→`Œ` is a single-byte fold, not `oe`. Quoted names compare **including**
  their quote delimiters but still fold case. Apply this to symbol identity in
  `validation/`, keep `.casefold()` for filesystem identity in `project/`
  (`005b5290`, `005b5f90`, `005b6ce0`).
  Note this validates the existing `SFC_RUNTIME_CONSTANTS = {on, off}` decision:
  type names (`GroupData`, `Timer`, `Time`, `Duration`, `IdentString`) are **not**
  scanner keywords, so SL-V034 must stay limited to real keywords.
* **B3.3 Builtin catalogue (P12).** Compiler analysis really does reject unknown
  functions/procedures (errors 5/6), type mismatches (8), wrong arity (9/10) and
  unsuitable reference actuals (11) — `0047b5a0`, `00485470`, `004748b0`,
  `006a3020`, `006a30e0`. Load the 504 registrations as data for diagnostics, but
  keep the descriptor field at `+0x1C` as a **raw mode enum**: masks are derived
  by `00711af0` (`>100` subtract 100, `>50` subtract 50, then
  `1,2,22→0x01; 4,24→0x02; 6,26→0x03; 8,28→0x08; 9,29→0x04; 10,30→0x0C; 11,31→0x10`),
  write-like is `0x0A`, and `+0x20`/`+0x21` are dependency flags, not `is_out`.
  Start with arity/reference checks that are unambiguous; never reject unknown
  names before the catalogue and user-type rules are both solid.

**Exit:** SL-V035 with tests; identity tests for ASCII/CP1252/ß/œ/quoted; builtin
checks limited to unambiguous cases; `RETIRED_CODES` unchanged.

### B4 — Diagnostics and coded-format fidelity (≈1 day; closes the ugly rows)

Three `we-too-lenient` rows (`ValidComprSeqBasic`, `ValidComprFull`,
`ValidUnComprFull`) hinge on compressed-source detail, and their history already
shows self-inflicted probes (UTF-8 saved as cp1252, hand-converted codes).

* **B4.1 Adopt the recovered scanner table — DONE 2026-10-26.**
  `preprocessing/scanner_tokens.json` now ships the 206-entry `.SCANNER` enum
  (ids 9–214 dense, `'#'+chr(48+n//16)+chr(48+n%16)`; SHA-256
  `edf254ac…41bb4b8a`, identical to the handoff copy). `SCANNER_TOKENS` replaces
  the 172-entry sample-derived `SEED_MAPPING` (`SEED_MAPPING` kept as an alias),
  the `#01…`/`#0<…` prefix hack is gone, and four wrong entries are corrected:
  `#1=`→`On` (was `True`), `#1>`→`Off` (was `False`), `#9<`→`Module_In_View`
  (was `Enable_`, colliding with `#64`), `#:=`→`Relative_` (was `Abs_`). 34
  newly decodable codes include `PUBLIC_`, `EQUATIONS`, `Invisible_`,
  `Non_Expandable_`, `Disable_`, `Der`, `Der2`, `RealVar`, `xCoord`, `yCoord`,
  `AutoMan`, `SeqTimerCheck`, `**`. New guards: table shape/hash test, corrected
  entries test, unknown-marker test, and a twin test proving
  `CompressedFullGrammar.s` decodes to `UnCompressedFullGrammar.s` token for
  token (it did not before). Packaging test + wheel check confirm the JSON ships.
* **B4.2 Regenerate the compressed probes instead of hand-writing them.**
  Answer 7 settles the mechanism: a fixed-width `#NN` token needs no trailing
  whitespace (`#01SeqControl` is fine), **but raw alphabetic words in coded mode
  stay NAME and never become keywords**. Our two compressed probes spell
  keywords as raw words (`SeqControl`, `SeqTimer`), so the tool parsed them as
  NAMEs and failed downstream — consistent with the recovered meanings of the
  codes we saw: **33 = missing `OBJSIZE` after the second coordinate value**
  (`00726030`) and **76 = missing `ENDSUBSEQSTEP` after a step-led body**
  (`0070ba70`). Both rows are therefore probe defects, not missing rules: retire
  them after regenerating with every keyword encoded.
* Add a round-trip test: decompressor(compressor(plain)) == plain for the corpus
  pair, and generator-side validation that every compressed probe comes from the
  compressor (keywords encoded, literals raw), never hand-edited.
* **B4.3 Message catalogue.** Displayed wording lives outside the executable:
  syntax errors come from the `ERRMESSFILE` resource (`006250b0`), expression
  errors from the `EXPRERRSTR` configuration list, statement errors from
  `STATEMERRSTR`, plus loader strings. Our diagnostics matching the real text is
  therefore blocked until those resources are supplied — another reason to ask
  the user for the installation's configuration files.
* Publish `PARITY.md`: rule × status (`enforced` / `retired` / `consumer` /
  `unprobed`) × real message × claim id × test. §10 requires it and it does not
  exist yet.

### B5 — Project load parity (≈4 days; LIB-01..05, DATE-01, gaps P04/P05/P10/P11)

Ring C. Our loader is deliberately more forgiving than the native route, so a
project the real tool refuses to load compiles here. Introduce an explicit
profile instead of silently rewriting consumer behaviour:

```python
class LookupProfile(Enum):
    CONVENIENCE = "convenience"   # today's behaviour, unchanged
    NATIVE = "native"             # traced LibraryFilePath route
```

* **B5.1 Body/sidecar pairing (P04).** Today `_load_one` calls `find_code` and
  `find_deps` independently, so `A/Lib.x` can be combined with `B/Lib.z`, and
  `_read_deps` treats a missing sidecar as empty. Native: the sidecar is read at
  the *selected body prefix* and a missing one does not resume the search
  (LIB-05, `00589be0`). **Important nuance (answer 11):** these are interactive
  conditions — `00582470`/`005821b0` offer Continue/Cancel unless the automatic
  path `DAT_0081e9b0` is set — so parity means *surfacing a load diagnostic at
  the selected prefix*, not inventing an unconditional abort. Also keep a present
  empty sidecar distinct from an absent one. Implement in `NATIVE`, keep
  `CONVENIENCE`. Tests from `sidecar-only`, `sidecar-missing`.
* **B5.2 Windows path algebra (P05).** Pure, injected-environment functions:
  comma-split prefix list copied literally (no separator insertion, no trim),
  `NAME:` → `%NAME%\` with expansion and undefined→empty, single-letter drive
  excluded, working-directory merge, config-`Directory` default for the direct
  candidate. Tests: `prefix-literal`, `prefix-trailing-slash`, `env-symbol`,
  `drive-not-env`.
* **B5.3 Search order.** direct candidate → already-bound/known unit → path list,
  first matching *body* wins; a newer DateCode in a later prefix never wins
  (LIB-01, DATE-01). Close the `ordered_lookup_bases` reordering question for
  `NATIVE` (it currently moves requester/sibling roots first — convenience).
* **B5.4 Cache.** Warm/cold equivalence when a preferred extension appears later
  (P10) and content-hash keying (P11) — tests plus a small schema/profile field.
  Explicitly *not* a native claim.
* **B5.5 Cycles.** Answer 11: an active-traversal check triggers library-error
  handling (`005844e0`) and Continue can detach the offending reference, so a
  cycle is a *reported* condition, not a silent dedupe. Emit a diagnostic in
  `NATIVE`, keep today's dedupe in `CONVENIENCE`, and do not copy either
  prototype's policy.

### B6 — Corpus honesty pass (0.5 day, prevents future reversals)

Add a first-line marker to fixtures, like the probes already carry:
`(* REAL-PARSER: verified 2026-10-05 | unverified | our-profile *)`.
A test asserts every `invalid/` fixture has either a verdict or an explicit
`our-profile` label. This is the guardrail against a second `Enable_`/`Layer_`
incident, and it makes the next Tier-0 sweep cheap: the unverified set is exactly
what needs a GUI run.

### B7 — Consolidation (0.5 day per batch end)

`pytest tests/parser` → `pytest tests` → ruff → pyright → regenerate report and
`PARITY.md` → update `PARITY_PLAN.md` §11 and `CHANGELOG.md`.

## 4. Suggested probe sessions (user-run, now optional rather than blocking)

Answers 1–13 settled the sequence, DateCode, identity, `:Old` and loader
questions at code level, so implementations can proceed on `native_static`
evidence. Probes now serve two narrower purposes: catching drift between the
analysed build and the installed one, and pinning the few areas that remain
open.

| Session | Units | Purpose |
| --- | --- | --- |
| S1 | ~12 | Controls for everything landed from native evidence: fork+break, unguarded transition, optional DateCode, `Module_In_View`/`Relative_`/`On`/`Off` in a coded unit, optional statement semicolon, unnamed `SUBSEQUENCE`/`SUBSEQSTEP` |
| S2 | ~6 | `:Old` write, high-byte identity pairs (`Straße`/`STRASSE`, `œ`/`Œ`, `ß`/`ss`, quoted vs unquoted), one builtin arity error |
| S3 | ~4 | Regenerated compressed units (isolated; some may crash/stall) |

Session hygiene: one violation per unit, byte-identical control, crashers in
their own session, `probes/MANIFEST.yaml` + `TRANSCRIPT.md` regenerated by
`scripts/probe/generate.py` so `analyze.py` picks them up.

## 5. Definition of done for *this* plan

1. Tier-0 `we-too-lenient` = 0. Any survivor is entered in `PARITY.md` as an
   accepted divergence with a claim id or probe verdict that justifies it.
2. `we-too-strict` = 0 for constructs the tool accepts (B2 done).
3. No `pending`/`unknown` tier-0 rows.
4. Every new or changed grammar rule cites a native address or probe id in its
   comment.
5. `PARITY.md` complete for SL-V001…V035 including retired codes and their reason.
6. Ring C: `LookupProfile.NATIVE` reproduces the traced resolver for the six
   path/sidecar acceptance cases; `CONVENIENCE` unchanged.
7. `pytest`, ruff, pyright clean; no runtime/simulation claims anywhere.

## 6. Risks / non-goals

| Risk | Mitigation |
| --- | --- |
| Tightening on static evidence alone | native address + control unit in the next session; `UNPROBED` label where the address is indirect |
| Re-probing environment-blocked rows (`GlobalSetpoint`, `GlobalBias`) | they stay environment-blocked; never retry (already confirmed twice) |
| Treating tool crashes as verdicts | `crashes-tool` stays terminal; we keep rejecting those files and say why |
| Copying prototype policies (v0.8 BFS, missing-sidecar tolerance, newest DateCode, source-order priority) | CONFLICTS.md items 2/3/5/6 as review checklist |
| Loader profile change leaking into consumers | `CONVENIENCE` default, `NATIVE` opt-in, A/B tests |
| 74 MB handoff in git | selective vendoring + hash pin (B0.3) |
| Compressed probes that mis-encode keywords | generator-only compressed units + twin/round-trip tests (B4.2) |
| Editing the scanner table by hand | JSON pinned by SHA-256, parity test against the handoff copy, shape test |

---

# Native answers received 2026-10-26

Recorded so the decisions stay auditable. Every claim below carries a native
address and is treated as `native_static` until a probe contradicts it.

| # | Question | Answer | Plan effect |
| --- | --- | --- | --- |
| 1 | Sequence element loop | Positions S/T/M with `closed_body`, `transition_body`, `step_body`, `open_body` productions (`00625d20`, `00708d20`, `007089a0`, `0070db70`, `0070be80`, `0070bcb0`, `0070b440`, `0070cf20`) | B1.2 rewrite |
| 2 | Alternative branches | `T (S T \| M)*`, ≥2 branches, no maximum, branch may end in `SEQTRANSITION … SEQFORK` (`00703970`) | B1.2 |
| 3 | Standalone `SEQBREAK` | Never legal on its own; only as `SEQFORK … [SEQBREAK]`, and the fork suffix attaches to steps *and* transitions (`006f9850`, `0070a100`, `0070d180`) | B1.1 |
| 4 | Transition names/guards | `SEQTRANSITION [NAME] [WAIT_FOR expr]`; absent guard → true (`0070d180`, `006fad30`); `SUBSEQSTEP`/`SUBSEQUENCE` names optional | B2.1, B1.3 |
| 5 | DateCode | Optional at records and module definitions; fixed keyword token 0x89/137, not `NAME + int` (`005d6170`, `005ccaa0`, `005dc3f0`, `005ab1b0`) | B2.2, B2.3 |
| 6 | Error 33 / 76 | 33 = missing `OBJSIZE` after the second coordinate value (`00726030`); 76 = missing `ENDSUBSEQSTEP` after a step-led body (`0070ba70`). Messages live in `ERRMESSFILE`/`EXPRERRSTR`/`STATEMERRSTR`, not in the exe | B4.2, B4.3 |
| 7 | Coded scanner | Fixed-width `#NN` needs no trailing space, but raw words stay NAME and are never keyword-reclassified (`0062cbc0`, `0062cb40`, `0062dab0`) | B4.2 — our compressed probes are invalid |
| 8 | `:Old` write | Compiler check: `:Old` target → expr error 0x14, non-State suffix → 0x13; reference-required args likewise (`00485470`, `004748b0`, `004888a0`); moduletype transfers use a different route | B3.1 |
| 9 | Identifier folding | Byte table at `00806168`: a–z→A–Z, 9A→8A, 9C→8C, E0–F6→C0–D6, F8–FE→D8–DE, FF→9F; `ß` unfolds; quoted names compare with quotes (`005b5290`, `005b5f90`, `005b6ce0`) | B3.2 |
| 10 | Reserved names | Keywords are tokens, not NAMEs, in identifier slots; `On`/`Off` are literal keywords; native type names are *not* keywords | SL-V034 stays limited to `{on, off}` |
| 11 | Load-path errors | Interactive Continue/Cancel (`00582470`, `005821b0`), automatic path sets cancellation (`DAT_0081e9b0`); cycle → library-error handling (`005844e0`); empty ≠ absent sidecar | B5.1, B5.5 |
| 12 | Builtin checks | Compiler rejects unknown function/procedure (5/6), type mismatch (8), too few/many (9/10), bad reference actual (11); `+0x1C` is a mode enum, masks from `00711af0`, write-like `0x0A` | B3.3 |
| 13 | Rejection checklist | 33 routines with one-line conditions (appendix below) | new backlog |
| — | Statement semicolons | Optional (`0072b660`) | new B2.5 |

## Still open

1. `FreeWord0` (`#1?`), `FreeWord1…3` (`#37`, `#38`, `#39`), `FreeWord5` (`#67`),
   `FreeWord6…8` (`#7=`, `#7>`, `#7?`) — real keywords or reserved no-ops? (There
   is no `FreeWord4`.) Also `EQUATIONS` (`#21`) and `IntObjPickButton` (`#93`)
   have no grammar production here yet.
2. The installation's `ERRMESSFILE`, `EXPRERRSTR`, `STATEMERRSTR` resources and
   the `.SCANNER` config container — needed for verbatim messages and to re-pin
   the 206-entry table to *this* build.
3. Duplicate declarations, graph/geometry validation, nominal compatibility,
   dependency masks and online-change rules: explicitly *not* covered yet.
4. Whether the analysed `main.exe` is the same build as the GUI the probes run
   against (needed before treating any `native_static` claim as installed-build
   truth).

---

# Appendix — rejection checklist from answer 13

Conditions are paraphrased from the native routines, not recovered UI messages.
Use as the backlog for finding rules we do not know we are missing.

| Routine | Condition |
| --- | --- |
| `0062cbc0` | unterminated quoted identifier; identifier length violation |
| `00708d20` | invalid initial body position; wrong sequence closing marker |
| `0070db70` | neither step nor structural construct at a closed-body position |
| `0070d180` | invalid transition-position construct; missing `ENDSUBSEQTRANSITION` |
| `0070ba70` | invalid step-position construct; missing `ENDSUBSEQSTEP` |
| `0070bcb0` | step-led body never reaches a required step |
| `00703970` | missing `ALTERNATIVEBRANCH` or `ENDALTERNATIVE` |
| `007025b0` | missing `PARALLELBRANCH` or `ENDPARALLEL` |
| `00708b40` | missing `ENDSUBSEQUENCE` |
| `006ff000` | missing internal loop separator/closing token |
| `006f9850` | missing fork target initially or after a comma |
| `00726030` | malformed equation coordinates, size or header separator |
| `005ab1b0` | wrong DateCode keyword or value token |
| `005dc3f0` | malformed named type declaration, visibility/body or semicolon |
| `005aad00` | missing variable-declaration colon, datatype or semicolon |
| `005bdc70` | non-NAME token in a declaration identifier slot |
| `005d0350` | missing transfer formal name or `=>` |
| `005de7d0` | missing reference name initially or after a dot |
| `0047b5a0` | unknown function/variable, wrong arity, invalid suffix, operand types |
| `00485470` | const/unwritable target, `:Old` assignment, non-State suffix, procedure resolution/arity |
| `004748b0` | argument type, reference requirement, `:Old` reference, nominal mismatch |
| `00725660` / `0072aad0` | assignment type mismatch, non-Boolean IF guard, branch ordering, wrong statement-call kind |
| `0059f060` | unresolved named type or recursive alias |
| `005a4b90` | unresolved actual connection, formal/actual type mismatch, optional State-connection warning |
| `0070e3d0` | prohibited write-like parameter-boundary mask |
| `0070f510` | prohibited nested reference mask |
| `0070ff10` | output-like access on a prohibited connection path |
| `00589be0` | missing/unreadable dependency sidecar |
| `00584aa0` | body/read setup or companion metadata failure |
| `005844e0` | dependency already active in recursive traversal |
| `00582c10` | missing-body rename/continue/abort decision |
| `00582470` / `005821b0` | file/library Continue/Cancel policy |
| `005d6f90` | central information/warning/error dispatch, suppression, interactive decisions |

Two of these are already implementable without further evidence and are not yet
in any batch: **`005bdc70`** (a keyword or literal where a declaration NAME
belongs — the `AliasSym Expected` family we keep meeting) and **`005aad00`**
(missing colon/datatype/semicolon in a variable declaration). Both belong in B4
as soon as `PARITY.md` exists.
