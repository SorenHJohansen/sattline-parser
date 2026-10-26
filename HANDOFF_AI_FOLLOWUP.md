# Follow-up questions for the reverse-engineering AI

Context: I implemented the recovered `.SCANNER` table in a standalone Python
parser for SattLine (`sattline-parser`, Lark frontend, strict single-source
validation SL-V001…V035). Your previous answers are now recorded in
`PARITY_HANDOFF_PLAN.md` with their addresses. Goal stays: **we accept a file
only if the real compiler accepts it, and we reject everything it refuses to
compile or load.** Editor/UI guards don't count.

Two things you should know before answering:

* The decoder is **text substitution, then normal lexing**: compact codes are
  expanded to their spelling before the Lark grammar runs. There is no separate
  coded-mode scanner on our side.
* Our grammar is hand-written from probes and native evidence, so an
  authoritative "what does the reader accept here" answer is worth more than a
  probe result.

Please answer with the routine address and the one-line condition for each item.
"Not recovered" is a fine answer — it is better than an inference I then encode
as a rule.

## Part 1 — verify what I just shipped (the compact-code table)

I replaced a 172-entry sample-derived table with the 206-entry recovered one
(`scanner_tokens.json`, ids 9–214 dense, `#` + `chr(48+n//16)` + `chr(48+n%16)`).
Four entries changed behaviour, and I want them checked rather than assumed:

1. **`#9<` = `Module_In_View`** (it previously decoded to `Enable_`, colliding
   with `#64`). Where is `Module_In_View` legal? Our grammar currently only
   accepts it by accident, through a catch-all in the module-header argument list
   (`NAME "=" value`). Is it a module-header argument, a graph-object property, or
   both? Is it distinct from `Enable_` in every context?
2. **`#:=` = `Relative_`** and **`#:<` = `Abs_`** (previously both decoded to
   `Abs_`). In which object/property positions may each appear, and are they
   mutually exclusive?
3. **`#1=` = `On`, `#1>` = `Off`** (previously `True`/`False`). Are these general
   boolean-literal keywords usable anywhere a boolean expression is expected, or
   restricted (e.g. only in `WAIT_FOR`/assignment/initialiser)? Do they behave
   identically to `True`/`False` in the expression parser, including in
   comparisons and as builtin arguments?
4. **Completeness of the enum.** Are scanner ordinals 1…206 the whole token set of
   this build (i.e. nothing above 206)? Which scanner tokens are *never* emitted
   in compact form — literals, numbers, quoted names, comment delimiters? I need
   to know whether "expand every `#NN` then lex normally" is faithful, or whether
   some codes only make sense inside a coded-mode scanner.
5. **The `FreeWord` entries.** `FreeWord0` = `#1?`, `FreeWord1…3` = `#37`/`#38`/`#39`,
   `FreeWord5` = `#67`, `FreeWord6…8` = `#7=`/`#7>`/`#7?` (there is no
   `FreeWord4`). Earlier you noted `006ff000` implements the internal loop using
   scanner IDs 63/64/65, which are `FreeWord1/2/3`. Please state what each
   `FreeWord` is: a hidden separator/closing token of the sequence loop, a
   reserved word, or something else. **Can any of them appear in source text that
   a compiler must accept or reject?** If they are purely internal, I will treat
   them as unrepresentable and say so.
6. **`EQUATIONS` (`#21`)** and **`IntObjPickButton` (`#93`)** have no production in
   our grammar at all. What do they introduce, and what is the shape of the
   construct that follows?

## Part 2 — check my reading of the sequence grammar before I rewrite it

I am about to replace our loose `sequence_body` with the S/T/M productions you
gave. These four inferences are load-bearing; please confirm or correct:

7. **`SEQFORK` is a suffix, not an element.** You wrote that the fork suffix is
   accepted after ordinary steps and ordinary transitions (`0070a100`,
   `0070d180`). Confirm the complete host list: ordinary step, ordinary
   transition, and *nothing else*? Specifically — `SUBSEQSTEP`, `SEQINITSTEP`,
   the `S`/`T` elements inside alternative and parallel branches, and the last
   element before a closing marker: may any of them carry `SEQFORK …[SEQBREAK]`?
8. **Fork target shape.** Are targets plain NAMEs only, or dotted paths /
   quoted names / `:Old` suffixes? Must there be at least one target (an empty
   `SEQFORK` is an error)? Is the target list validated against step names at
   compile time (our SL-V017), or only at run time / not at all?
9. **Optional statement semicolons (`0072b660`).** Optional in *which* lists?
   Enter/active/exit code, IF bodies, equation bodies, submodule invocation
   tails, module-type transfers? And if a semicolon is omitted, what separates
   the two statements — newline, any whitespace, or is `A = 1 B = 2` on one line
   also legal? This is the difference between "relax the terminator" and "the
   grammar has no terminator at all".
10. **Ordering of transition parts.** Is `SEQTRANSITION NAME WAIT_FOR expr
    SEQFORK A,B SEQBREAK` the only order (fork last), and is a fork suffix legal
    on a transition with *no* guard (`SEQTRANSITION Name SEQFORK A,B`)? Same
    question for an unnamed unguarded transition with a fork.
11. **`OPENSEQUENCE` endpoints.** Your `open_body` allows `S` with nothing after
    it. Is a lone initial step (or a body ending on an arbitrary step) therefore
    accepted, or does the open form still require at least one transition
    somewhere? Our corpus assumes `SEQINITSTEP` + code + `ENDOPENSEQUENCE` is
    valid, and I need to know whether that fixture is invented.

## Part 3 — rules I am about to implement

12. **`005bdc70` / `005aad00` (declaration slots).** Is the rule simply "any
    scanner keyword token is invalid where a declaration NAME is required", with
    quoted spellings exempt? Or are some keywords legal NAMEs in some declaration
    lists? Concretely: are `On`, `Off`, `DateCode_`, `GLOBAL`, `State`, `Const`,
    `OpSave`, `Secure`, `PUBLIC_`, `PRIVATE_` all rejected as variable, record and
    record-field names, and does the diagnostic differ (your `#10` answer says the
    token arrives as a keyword, not a NAME — I want to know whether the check is
    the scanner's or per-reader).
13. **Duplicate declarations — is there any compiler check at all?** Our probes
    show the real tool compiles duplicate datatype names, moduletype names,
    record field names and variable names in one scope with no warning, so we
    retired those rules as editor-only guards. Please confirm from the compile
    path whether a duplicate-name check exists anywhere (name table insertion,
    `005dxxxx`/`005axxxx`), or state that there is none. This decides whether
    "duplicates are not a compile error" is permanently closed or merely unproven.
14. **Nominal compatibility (expression error 11).** What is the exact rule for
    argument/assignment compatibility: same record identity (by name), structural
    equivalence, or something else? Does `integer` → `real` assignment pass?
    Does a `real` → `integer` assignment fail? Are `AnyType` formals compatible
    with everything? Our current rule is intentionally permissive and I don't
    want to tighten it on a guess.
15. **`005a4b90` "optional State-connection warning".** Is a State actual
    connected to a non-State formal (or vice versa) a warning that still
    compiles, or an error? If it is configurable, what does the default
    configuration do? This is the one place where we would otherwise reject a
    file the tool accepts.
16. **String capacity (`TYPE-01`).** Exceeding a configured string capacity
    (literal longer than the declared capacity, or `IdentString` default) — is
    that a compile error, a truncation with warning, or unchecked? The earlier
    handoff warned me not to copy prototype capacities, so I need the real check
    rather than a table.
17. **`DateCode_` value domain.** Now that we require the keyword: are negative
    values, zero, and values above 2 000 000 000 accepted in source (the
    reduction to `n % 2 000 000 000` happens on parse, per `005ab1b0`)? Is the
    spelling case-insensitive like other keywords? Is a missing value after
    `DateCode_` an error or an implicit import stamp?

## Part 4 — resources and provenance

18. **Configuration resources.** Which files on a typical installation hold
    `ERRMESSFILE`, `EXPRERRSTR`, `STATEMERRSTR` and the `.SCANNER` section
    (names, paths, extensions, container format)? I want to ask the user for
    those files so the message text is verbatim and the 206-entry table is pinned
    to *this* installation rather than the September extraction.
19. **Build identity.** SHA-256 and version of the analysed `main.exe`, and
    whether parsing/validation lives in the executable or a DLL. Without this I
    cannot tell whether a GUI verdict from the user's machine and your static
    evidence describe the same build, and several of my `native_static` rules
    would stay labelled unverified for that reason alone.
20. **Anything in your answer 13 list that you consider version-fragile** — i.e.
    conditions you would not expect to hold across SattLine builds. I would
    rather label those `unprobed` than ship them as parity.

If you can also say which of the checks in your routine list are reachable
*before* the program is compiled far enough to run (pure load/analyse phase),
that would let me separate "cannot compile" from "cannot run", which is exactly
the line this project cares about.
