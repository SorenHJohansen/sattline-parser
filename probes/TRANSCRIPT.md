# SattLine real-parser probe transcript
#
# A unit is a program/library triple: `file` is the .s; its .y and .z
# siblings travel with it. Fill `real status` with Accept or Reject per
# unit, and paste the exact message text (or message id) into `message`.
# This file is the input to analyze.py.
#
| id | area | tier | file | kind | expected | real status | message |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T1-001 | expression-types | 1 | Ctrl.x | control | accept | accept | loads without warnings |
| T1-001 | expression-types | 1 | ViolIntFromBool.x | violation | reject | reject | BasePicture: Datatype error in assignment: Output = Flag1; - ours REJECTS: SL-V029 ASSIGNMENT_TYPE_MISMATCH, matches the real message |
| T1-002 | expression-types | 1 | CtrlB.x | control | accept | accept | loads without warnings |
| T1-002 | expression-types | 1 | ViolRealVsBool.x | violation | reject | reject | BasePicture. Only integer and real allowed for this operator X > Flag1 - ours REJECTS: SL-V028 OPERAND_NOT_NUMERIC, matches the real message |
| T1-003 | expression-types | 1 | CtrlC.x | control | accept | accept | loads without warnings |
| T1-003 | expression-types | 1 | ViolIntCond.x | violation | reject | reject | BasePicture: Condition in IF-sentence is not boolean :IF A THEN A = 1; - ours REJECTS: SL-V030 CONDITION_NOT_BOOLEAN, matches the real message |
| T1-004 | expression-types | 1 | CtrlD.x | control | accept | accept | loads without warnings |
| T1-004 | expression-types | 1 | ViolStrArg.x | violation | reject |  |  |
| T1-005 | expression-types | 1 | CtrlE.x | control | accept | accept | loads without warnings |
| T1-005 | expression-types | 1 | ViolTooDeep.x | violation | reject | reject | BasePicture: Record component not defined: Sensor.Position.X.Y - ours rejects with SL-V019 at the same construct, so T1-005 is rule-confirmed |
| T1-006 | context-restricted-types | 1 | AnyTypeParam.x | control | accept | reject | Submodule Controller1, parameter Query not connected. - missing `ControllerType`/`GlobalSetpoint` symbol: rejected before AnyType was ever checked, so the rule is UNTESTED |
| T1-006 | context-restricted-types | 1 | AnyTypeLocVar.x | violation | reject | reject | ControllerType GLOBAL GlobalSetpoint not found at BasePicture.Controller2 - missing `ControllerType`/`GlobalSetpoint` symbol: rejected before AnyType was ever checked, so the rule is UNTESTED |
| T1-006b | context-restricted-types | 1 | CtrlF.x | control | accept | accept | loads without warnings |
| T1-006b | context-restricted-types | 1 | ViolAnyTypeFld.x | violation | reject |  |  |
| T1-007 | statement-context | 1 | CtrlDefParam.x | control | accept | reject | Modul:CtrlDefParam:ControllerType GLOBAL GlobalSetpoint not found at BasePicture.Controller2 - missing `ControllerType`/`GlobalSetpoint` symbol; ours accepts clean, so the control is broken, not the rule |
| T1-007 | statement-context | 1 | ViolDefScalLocVar.x | violation | unknown | reject | ControllerType GLOBAL GlobalSetpoint not found at BasePicture:Controller2 - missing symbol again, so the intended rule (:= Default on a plain localvar) is still untested |
| T1-008 | statement-context | 1 | CtrlWithInit.x | control | accept | accept | loads without warnings |
| T1-008 | statement-context | 1 | ViolConstNoInit.x | violation | accept |  |  |
| T1-009 | statement-context | 1 | CtrlG.x | control | accept | accept | loads without warnings |
| T1-009 | statement-context | 1 | ViolStateInt.x | violation | unknown |  |  |
| T1-009 | statement-context | 1 | ViolOpSaveStr.x | violation | unknown |  |  |
| T1-010 | statement-context | 1 | CtrlH.x | control | accept | accept | loads without warnings |
| T1-010 | statement-context | 1 | ViolOldOnNonState.x | violation | reject | reject | BasePicture. No attribute allowed for this variable: Valve.Position:Old - ours rejects with SL-V006, so T1-010 is rule-confirmed |
| T1-011 | sfc | 1 | CtrlI.x | control | accept | accept | loads without warnings |
| T1-011 | sfc | 1 | ViolStepAcc.x | violation | accept |  |  |
| T1-011 | sfc | 1 | ViolSeqReset.x | violation | accept |  |  |
| T1-012 | reserved-names | 1 | CtrlOrdName.x | control | accept | accept | loads without warnings |
| T1-012 | reserved-names | 1 | ViolVarOn.x | violation | reject | reject | Error on line 14: >>>On<<< AliasSym Expected. Ours ACCEPTS - known gap: we never forbid declaring the reserved name On |
| T1-012 | reserved-names | 1 | ViolVarOff.x | violation | reject | reject | Error on line 14: >>>Off<<< AliasSym Expected. Ours ACCEPTS - known gap: we never forbid declaring the reserved name Off |
| T1-012 | reserved-names | 1 | ViolVarGroup.x | violation | reject |  |  |
| R-101 | sfc | 1 | CtrlSingleInit.x | control | accept | accept | loads without warnings |
| R-101 | sfc | 1 | ViolSecInit.x | violation | accept | reject | Error on line 48: >>>ENDSEQUENCE<<< Incorrect Syntax - Error 32. A second SEQINITSTEP is NOT allowed; R-101 hypothesis disproven. Ours rejects with SL-V022 |
| R-102 | sfc | 1 | CtrlInitFirst.x | control | accept | accept | loads without warnings |
| R-102 | sfc | 1 | ViolInitAfterStep.x | violation | accept |  |  |
| C-101 | moduletype-graph | 3 | CtrlAcyc.x | control | accept | accept | loads without warnings |
| C-101 | moduletype-graph | 3 | ViolCycle.x | violation | reject |  |  |
| C-102 | moduletype-graph | 3 | CtrlAcycB.x | control | accept | accept | loads without warnings |
| C-102 | moduletype-graph | 3 | ViolSelfInst.x | violation | reject |  |  |
| C-103 | moduletype-graph | 3 | CtrlInst.x | control | accept | accept | loads without warnings |
| C-103 | moduletype-graph | 3 | ViolUnused.x | violation | reject |  |  |
| C-104 | moduletype-graph | 3 | CtrlDef.x | control | accept | accept | loads without warnings |
| C-104 | moduletype-graph | 3 | ViolUndefBind.x | violation | reject | reject | Moduletype GhostType not found (options: replace, open new library, delete object, abort). Ours ACCEPTS - known gap: ModuleTypeInstance is skipped in validation |
| C-105 | moduletype-graph | 3 | CtrlFullArity.x | control | accept | reject | Modul:CtrlFullArity:ControllerType GLOBAL GlobalSetpoint not found at BasePicture:Controller2 - missing `ControllerType`/`GlobalSetpoint` symbol; ours accepts clean, so the control is broken, not the rule |
| C-105 | moduletype-graph | 3 | ViolMissMap.x | violation | reject | reject | ControllerType: GLOBAL GlobalSetpoint not found at basepicture:controller1 - missing symbol; the missing-mapping rule itself is still untested |
| C-106 | moduletype-graph | 3 | CtrlTypedXfer.x | control | accept | reject | :ControllerType GLOBAL GlobalSetpoint not found at BasePicture:Controller2 - missing `ControllerType`/`GlobalSetpoint` symbol; ours accepts clean, so the control is broken, not the rule |
| C-106 | moduletype-graph | 3 | ViolBoolToReal.x | violation | reject | reject | BasePicture: Submodule Controller1, parameter Setpoint: Variable ControlEnabled is an invalid type - ours rejects with SL-V027 (same wording as SL-V027), so C-106 is rule-confirmed |
| C-201 | graphics-correlation | 3 | CtrlDateMatch.x | control | accept | accept | loads without warnings |
| C-201 | graphics-correlation | 3 | ViolDateShift.x | violation | reject | accept | Dialog: "Composite object file has wrong date. Syntax errors and system crash can arise if this file is read. Continue?" -> answered YES, no crash. A graphics/code date mismatch is a WARNING, not an error. Ours accepts |
| C-202 | graphics-correlation | 3 | CtrlCountMatch.x | control | accept | accept | loads without warnings |
| C-202 | graphics-correlation | 3 | ViolExtraObj.x | violation | reject |  |  |
| t0-edge-ArithmeticPrecedence | tier0-sweep | 0 | EdgeArithPrec.x | inventory | accept |  |  |
| t0-edge-BareDurationZero | tier0-sweep | 0 | EdgeBareDurZero.x | inventory | accept | reject | BasePicture Only integer og real allowed for this operator ZeroDur == ZeroFull - ours REJECTS: SL-V028 OPERAND_NOT_NUMERIC, matches the real message |
| t0-edge-CaseInsensitiveIdentifiers | tier0-sweep | 0 | EdgeCaseInsens.x | inventory | accept |  |  |
| t0-edge-CommentInsideEquation | tier0-sweep | 0 | EdgeCmtInEq.x | inventory | accept | reject | Error on line 35 SEQTRANSITION TrStart WAIT_FOR>>>(*<<< inline comment. Expression expected. - ours accepts (we allow a comment after WAIT_FOR) |
| t0-edge-ConstStringSetGetPos | tier0-sweep | 0 | EdgeConstStrSetGet.x | inventory | accept |  |  |
| t0-edge-ClippingBoundsRealExpr | tier0-sweep | 0 | ClippingBoundsRealExpr.x | inventory | accept |  |  |
| t0-edge-CoordinateInvarTail | tier0-sweep | 0 | EdgeCoordInvarTail.x | inventory | reject | reject | BasePicture The expression is of an invalid type Source + 1 - ours rejects (SL-V032). RESOLVED 2026-10-01 by the editor: this is a TYPE error, not a syntax error. Re-declaring the same tail with `Source` as real made the error disappear, so computed corner tails are legal and the tail must simply be REAL-typed. Rule (a) confirmed, rule (b) (literals only) disproven |
| t0-edge-DeeplyNestedComments | tier0-sweep | 0 | EdgeDeepNestCmts.x | inventory | accept |  |  |
| t0-edge-DurationInParameterMapping | tier0-sweep | 0 | EdgeDurInParamMap.x | inventory | accept |  |  |
| t0-edge-DurationVariousFormats | tier0-sweep | 0 | EdgeDurVarFmt.x | inventory | accept | reject | Error on line 15 >>>(*<<< Duration_Value. AliasSym Expected. - ours rejects on an unrelated construct: this file also compares durations, which is SL-V028. The real tool stopped at the line-15 comment error, so this file is reworked before it can confirm the comment rule |
| t0-edge-ElsifExpression | tier0-sweep | 0 | EdgeElsifExpr.x | inventory | accept |  |  |
| t0-edge-EmptyCodeBlocks | tier0-sweep | 0 | EdgeEmptyCodeBlk.x | inventory | accept |  |  |
| t0-edge-EmptyRecordType | tier0-sweep | 0 | EdgeEmptyRecType.x | inventory | accept |  |  |
| t0-edge-FrameModuleInvocation | tier0-sweep | 0 | EdgeFrameModInvoc.x | inventory | accept | crash | crashes SattLine - ours accepts. A frame-style module invocation kills the tool outright, so the grammar there is a landmine, not just a rule |
| t0-edge-GlobalParameterMapping | tier0-sweep | 0 | EdgeGlobalParamMap.x | inventory | accept | reject | ControllerType GLOBAL GlobalBias not found at BasePicture:Ctrl - missing symbol (same class as GlobalSetpoint; GlobalBias is declared nowhere in probes/). Ours ACCEPTS |
| t0-edge-KeywordPrefixedIdentifiers | tier0-sweep | 0 | EdgeKwPrefixed.x | inventory | accept |  |  |
| t0-edge-LegacySequenceNoInitStep | tier0-sweep | 0 | EdgeLegacySeqNo.x | inventory | accept |  |  |
| t0-edge-MinimalSequence | tier0-sweep | 0 | EdgeMinSeq.x | inventory | accept |  |  |
| t0-edge-ModuleDefNoTrailingEnddef | tier0-sweep | 0 | EdgeModDefNoTrail.x | inventory | accept | reject | Error on line 15 >>><<< SemicolonSym Expected - ours accepts (we allow a missing ENDDEF terminator) |
| t0-edge-ModuleOptions | tier0-sweep | 0 | EdgeModOpt.x | inventory | accept |  |  |
| t0-edge-OpSaveConst | tier0-sweep | 0 | OpSaveConst.x | inventory | accept |  |  |
| t0-edge-OpSaveStateReversed | tier0-sweep | 0 | OpSaveStateReversed.x | inventory | accept |  |  |
| t0-edge-NegativeDurationValue | tier0-sweep | 0 | EdgeNegDurVal.x | inventory | accept | reject | BasePicture only integer and real allowed for this operator NegFive==NegHour - ours REJECTS: SL-V028 OPERAND_NOT_NUMERIC, matches the real message |
| t0-edge-OldNewOnDottedStateField | tier0-sweep | 0 | EdgeOldNewOnDotted.x | inventory | accept |  |  |
| t0-edge-OpSaveAndStateCombined | tier0-sweep | 0 | EdgeOpSaveAndState.x | inventory | reject | reject | Error on line 19 SavedStateVar: integer Opsave >>>State<<< Unknown error - unable to read error message file. - ours rejects (SL-V031). RESOLVED 2026-10-01: the file-load path could not render its message ("unable to read error message file"), but the editor gives it verbatim: "Invalid attribute identifider or invalid combination of attributes" (sic). So the combination IS invalid, and it is caught as a validation error, not a parse error. Confirmed for both the integer and the boolean declaration A missing message is not a specification, so the grammar keeps allowing the combination. State alone is confirmed-accept (CtrlG.x, CtrlWithInit.x), so OpSave+State is the trigger. Needs disambiguation probes: see PARITY_PLAN.md |
| t0-edge-QuotedIdentifierMaxLength | tier0-sweep | 0 | EdgeQuotedIdentMax.x | inventory | accept |  |  |
| t0-edge-ScanGroupClause | tier0-sweep | 0 | EdgeScanGrpCl.x | inventory | accept | reject | BasePicture "ScanGroup": Variable FastScan not declared - ours ACCEPTS: the ScanGroup clause does not resolve its variable |
| t0-edge-SeqBreak | tier0-sweep | 0 | EdgeSeqBrk.x | inventory | accept | reject | Error on line 25 >>>SEQBREAK<<< Unexpected symbol or end of input - ours accepts (we allow SEQBREAK here) |
| t0-edge-SeqForkMultipleTargets | tier0-sweep | 0 | EdgeSeqForkMulti.x | inventory | accept |  |  |
| t0-edge-SequenceAlternative | tier0-sweep | 0 | EdgeSeqAlt.x | inventory | accept | reject | Error on line 21 >>>ALTERNATIVESEQ<<< EndLoopSeqSym Expected - ours accepts |
| t0-edge-SequenceParallel | tier0-sweep | 0 | EdgeSeqPar.x | inventory | reject | reject | Error on line 29 >>>ENDSEQUENCE<<< Incorrect Syntax - Error 32 - ours accepts SL-V033 - ours rejects: a closed sequence body must close on a SEQTRANSITION, not a SEQSTEP |
| t0-edge-SimpleModuleTypeInvocation | tier0-sweep | 0 | EdgeSimpleModType.x | inventory | accept |  |  |
| t0-edge-SubSequenceDefinition | tier0-sweep | 0 | EdgeSubSeqDef.x | inventory | reject | reject | Error on line 26 >>>ENDSEQUENCE<<< Incorrect Syntax - Error 32 - ours accepts SL-V033 - ours rejects: a closed sequence body must close on a SEQTRANSITION, not a SEQSTEP |
| t0-edge-SubSequenceTransition | tier0-sweep | 0 | EdgeSubSeqTrans.x | inventory | accept |  |  |
| t0-edge-TerminalSeqStep | tier0-sweep | 0 | EdgeTermSeqStep.x | inventory | reject | reject | Error on line 22 >>>ENDSEQUENCE<<< Incorrect Syntax - Error 32 - ours accepts SL-V033 - ours rejects: a closed sequence body must close on a SEQTRANSITION, not a SEQSTEP |
| t0-edge-TimeValueInit | tier0-sweep | 0 | EdgeTimeValInit.x | inventory | accept |  |  |
| t0-edge-UnicodeIdentifiers | tier0-sweep | 0 | EdgeUnicodeIdents.x | inventory | accept | reject | Error on line 14 D>>>é<<<bit Incorrect Syntax - Error 76 - ours rejects too (lexer stops on the high byte), so Error 76 = invalid identifier character |
| t0-invalid-BadBareDurationString | tier0-sweep | 0 | BadBareDurStr.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) - ours rejects SL-V009. STAGE-SCOPED: the real tool compiles on direct file load; the IDE refuses to *create* the construct. Our parser models file load, so this is stricter than the tool. |
| t0-invalid-BadBareTimeString | tier0-sweep | 0 | BadBareTimeStr.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) - ours rejects SL-V010. STAGE-SCOPED: compiles on direct file load, IDE refuses to create. Same divergence as BadBareDurStr. |
| t0-invalid-BadDurationLiteral | tier0-sweep | 0 | BadDurLit.x | inventory | reject | accept | compiles without warnings - ours rejects with SL-V011 (`not-a-duration`) |
| t0-invalid-BadTimeLiteral | tier0-sweep | 0 | BadTimeLit.x | inventory | reject | accept | compiles without warnings - ours rejects with SL-V012 |
| t0-invalid-BuiltinDatatypeTypo | tier0-sweep | 0 | BadBuiltinDatatype.x | inventory | reject | reject | "Datatype intege not found" (dialog: replace / open new library / delete / abort) - ours rejects SL-V018 BUILTIN_DATATYPE_TYPO, matches the real message |
| t0-invalid-BuiltinOutArgNotVariable | tier0-sweep | 0 | BadBuiltinOutArg.x | inventory | reject | reject | Type error in if-sentence. If UseA THEN DestinationA ELSE DestinationB ENDIF - ours rejects SL-V014, but MIS-TARGETED probe: the real tool rejected this file for an unrelated reason ("Type error in if-sentence"), so SL-V014 is still unconfirmed. The SL-V010 hits are also incidental: this file initialises time variables from bare strings. |
| t0-invalid-BuiltinWrongArity | tier0-sweep | 0 | BadBuiltinWrong.x | inventory | reject | reject | Too few parameters EqualString(Name1, Name2) - ours rejects SL-V013 BUILTIN_WRONG_ARITY, matches the real message |
| t0-invalid-ConsecutiveSeqSteps | tier0-sweep | 0 | BadConsecSeqSteps.x | inventory | reject | reject | line 28 >>>SEQSTEP<<< Step2. Incorrect syntax - Error 32 - ours rejects SL-V016 CONSECUTIVE_SEQUENCE_STEPS, matches |
| t0-invalid-ConstVarAsBuiltinOutArg | tier0-sweep | 0 | BadConstVarAs.x | inventory | reject | reject | out parameter is not a variable: Fixed - ours rejects SL-V007, matches the real message |
| t0-invalid-Cp1252UndefinedByte | tier0-sweep | 0 | HighByteInvalid.x | inventory | reject |  | byte 0x81 undefined in cp1252 - ours raises UnicodeDecodeError |
| t0-invalid-CrossModuleContractMismatch | tier0-sweep | 0 | BadCrossMod.x | inventory | reject | reject | Submodule Child, parameter EnableFlag: Variable CounterValue is an invalid type - ours rejects SL-V027 PARAM_TRANSFER_TYPE_MISMATCH, matches the real message |
| t0-invalid-DatatypeShadowsBuiltinName | tier0-sweep | 0 | BadDatatypeShadows.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) - ours rejects SL-V026. STAGE-SCOPED: compiles on direct file load, IDE refuses to create. |
| t0-invalid-DuplicateDatatypeName | tier0-sweep | 0 | BadDupDatatypeName.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) - ours rejects SL-V001. STAGE-SCOPED: duplicate datatype names compile on direct file load; the IDE refuses to create them. |
| t0-invalid-DuplicateModuletypeName | tier0-sweep | 0 | BadDupModTypeName.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) - ours rejects SL-V002. STAGE-SCOPED: same as BadDupDatatypeName. |
| t0-invalid-DuplicateRecordFieldName | tier0-sweep | 0 | BadDupRecFldName.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) - ours rejects SL-V025. STAGE-SCOPED: same as BadDupDatatypeName. |
| t0-invalid-DuplicateSFCElementNames | tier0-sweep | 0 | BadDupSfcElemNames.x | inventory | reject | reject | error in sequence block - ours rejects SL-V021, matches |
| t0-invalid-DuplicateSiblingSubmodules | tier0-sweep | 0 | BadDupSibSubmods.x | inventory | reject | reject | module name is not unique: SensorA - ours rejects SL-V004, matches the real message |
| t0-invalid-DuplicateVariableNames | tier0-sweep | 0 | BadDupVariaNames.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) - ours rejects SL-V003. STAGE-SCOPED: same as BadDupDatatypeName. |
| t0-invalid-EncodingStress | tier0-sweep | 0 | BadEncodingStress.x | inventory | reject | crash | SattLine crashes on open (no diagnostic; file is ASCII, crash is the placeholder header lines + truncated `Var1 = Var2 +`) |
| t0-invalid-FreestandingCommentInModuleCode | tier0-sweep | 0 | BadFreeCmtInMod.x | inventory | reject | reject | line 21 >>>(*<<< This comment. AliasSym Expected. Error indicated by >>> <<< - ours rejects at the same line (comment not allowed in ModuleCode) |
| t0-invalid-GraphObjectsDoubleLayer | tier0-sweep | 0 | BadGraphObjDouble.x | inventory | reject | reject | line 15. GraphObjects: >>>Layer_<<< = 2 Layer_ = 3. Error message: AliasSym expected. - ours rejects at the same line |
| t0-invalid-InitValueTypeMismatch | tier0-sweep | 0 | BadInitValType.x | inventory | reject | accept | compiles without warnings - ours rejects with SL-V008 (str init for integer) |
| t0-invalid-Malformed | tier0-sweep | 0 | BadMalformed.x | inventory | reject | crash | SattLine crashes on open (no diagnostic; file has no header line at all - ours rejects at line 1, expected STRING) |
| t0-invalid-ModuleCodeWithoutModuleDef | tier0-sweep | 0 | BadModCodeWithMod.x | inventory | reject | crash | SattLine crashes on open (no diagnostic; bare `ModuleCode` without a ModuleDef - ours rejects at line 13) |
| t0-invalid-NotSattLine | tier0-sweep | 0 | BadNotSattLine.x | inventory | reject | crash | SattLine crashes on open (no diagnostic; plain text, no header - ours rejects at line 1, expected STRING) |
| t0-invalid-OldNewOnNonState | tier0-sweep | 0 | BadOldNewOnNon.x | inventory | reject | reject | Modul: BadOldNewOnNon:BasePicture no attributes allowed for this variable: Counter:Old - ours rejects with SL-V005 |
| t0-invalid-OldNewOnNonStateRecordField | tier0-sweep | 0 | BadOldNewOnNonB.x | inventory | reject | reject | same error as BadOldNewOnNon, for CMD.Other:Old - ours rejects with SL-V006 |
| t0-invalid-OversizedInput | tier0-sweep | 0 | BadOversizeInput.x | inventory | reject | stall | SattLine stalls when opening the file, never loads (1652 B - not a size limit; ours rejects at line 51, `Real_Value`) |
| t0-invalid-SFCAlternativeBranchStartsWithStep | tier0-sweep | 0 | BadSfcAltBrStart.x | inventory | reject | reject | Error on line 26: >>>ALTERNATIVESEQ<<< EngLoopSeqSym Expected. - ours rejects with SL-V023 |
| t0-invalid-SFCInitStepNotFirst | tier0-sweep | 0 | BadSfcInitStepNot.x | inventory | reject | accept | Complies without warnings - ours rejects with SL-V022 (init not first) |
| t0-invalid-SFCInitStepRepeated | tier0-sweep | 0 | BadSfcInitStep.x | inventory | reject |  |  |
| t0-invalid-SFCParallelBranchStartsWithTransition | tier0-sweep | 0 | BadSfcParBrStart.x | inventory | reject | reject | Error on line 26 >>>SEQTRANSITION<<< Incorrect syntax - Error 29 - ours rejects with SL-V024 |
| t0-invalid-SeqForkUnknownTarget | tier0-sweep | 0 | BadSeqForkUnknown.x | inventory | reject | reject | Error on line 30: >>>SEQBREAK<<< Unexpected symbol or end of input. - ours rejects with SL-V017 |
| t0-invalid-StringLiteralInCallArgument | tier0-sweep | 0 | BadStrLitInCall.x | inventory | reject | reject | Error on line 23 IsMatch = EqualStrings(Input, ">>>Expected<<<", True); Expression expected - ours rejects with SL-V015 on the string literal (confirms the literal-call rule) |
| t0-invalid-UndefinedVariableRef | tier0-sweep | 0 | BadUndefVariaRef.x | inventory | reject | reject | BasePicture variable not defined: Ghost - ours rejects with SL-V019 |
| t0-invalid-UnknownDatatypeName | tier0-sweep | 0 | BadUnknownDatatype.x | inventory | reject | reject | SattLine reports Zzzyx as not found; dialog: replace type / open new library / delete object / abort - ours rejects with SL-V020 |
| t0-invalid-UnterminatedComment | tier0-sweep | 0 | BadUntermCmt.x | inventory | reject | reject | Error on line 15: >>><<< AliasSymExpected - ours rejects at line 15 (unterminated comment) |
| t0-invalid-WriteToConstVariable | tier0-sweep | 0 | BadWriteToConst.x | inventory | reject | reject | Modul: BadWriteToConst:BasePicture value cannot be changed: MaxLimit - ours rejects with SL-V007 |
| t0-valid-AllDatatypes | tier0-sweep | 0 | ValidAllDatatypes.x | inventory | accept |  |  |
| t0-valid-BuiltinCalls | tier0-sweep | 0 | ValidBuiltinCalls.x | inventory | accept |  |  |
| t0-valid-CompressedFullGrammar | tier0-sweep | 0 | ValidComprFull.x | inventory | accept | reject | Error on line 24: form>>>å<<<l Incorrect Syntax - Error 76 - ours rejects too; non-ASCII identifiers are illegal |
| t0-valid-CompressedSequenceBasic | tier0-sweep | 0 | ValidComprSeqBasic.x | inventory | accept | reject | Error on line 24: #22 MainSeq #01 >>>SeqControl<<<, SeqTimer). Incorrect Syntax - Error 33 - ours accepts (step number/order syntax in a sequence header) |
| t0-valid-ControlFlow | tier0-sweep | 0 | ValidCtrlFlow.x | inventory | accept |  |  |
| t0-valid-CoordInVarTail | tier0-sweep | 0 | ValidCoordInVar.x | inventory | reject | reject | Error on line 35 ( 0.1 : InVar_ >>>PanelX<<< DefineSym Expected - ours parse-rejects. An InVar_/OutVar_ coordinate tail must name a QUOTED DefineSym; the bare-identifier form is not accepted in this position. The interact `invar`/`invar_tail` contexts still allow it, since the rejection is only evidenced for coordinates |
| t0-valid-Cp1252HighBytes | tier0-sweep | 0 | HighByteValid.x | inventory | accept |  | valid cp1252 high bytes (0x92, 0xE4) in a comment - ours parses clean |
| t0-valid-DefaultInitOnRecord | tier0-sweep | 0 | ValidDefInitOnRec.x | inventory | accept |  |  |
| t0-valid-DurationAndTime | tier0-sweep | 0 | ValidDurAndTime.x | inventory | accept | reject | BasePicture only integer and real allowed for this operator: DurFull == DurBare - ours REJECTS: SL-V028 OPERAND_NOT_NUMERIC, matches the real message |
| t0-valid-GraphObjectEnableTails | tier0-sweep | 0 | ValidGraphObjEnabl.x | inventory | accept | reject | Error on line 22 "DisplayValue">>>ValueFraction<<< AliasSym Expected - ours accepts (a bare enable token after a property name) |
| t0-valid-GraphObjectShapes | tier0-sweep | 0 | ValidGraphObj.x | inventory | accept |  |  |
| t0-valid-GraphObjectsSectionLayer | tier0-sweep | 0 | ValidGraphObjB.x | inventory | accept | reject | Error on line 16: GraphObjects : >>>Layer_<<< 2 AliasSym Expected - ours parse-rejects, and now there is no section-level layer clause, so `graph_objects` no longer allows layer_info. Matches the real AliasSym error (a layer number in the GraphObjects section) |
| t0-valid-GraphicsObjects | tier0-sweep | 0 | ValidGraphicsObj.x | inventory | accept |  |  |
| t0-valid-InteractEnableTails | tier0-sweep | 0 | ValidInteractEnabl.x | inventory | accept | reject | Error on line 27: >>>Enable_<<< = True: AliasSym Expected - ours parse-rejects, and now the enable_expression tail is no longer in the grammar for `enable`, so this matches the real AliasSym error |
| t0-valid-InteractWidgets | tier0-sweep | 0 | ValidInteract.x | inventory | accept |  |  |
| t0-valid-MinimalProgram | tier0-sweep | 0 | ValidMinProg.x | inventory | accept |  |  |
| t0-valid-MultiEquationBlocks | tier0-sweep | 0 | ValidMultiEqBlk.x | inventory | accept |  |  |
| t0-valid-MultiTypedefBlocks | tier0-sweep | 0 | ValidMultiTypedef.x | inventory | accept |  |  |
| t0-valid-MultipleModuleDefBlocks | tier0-sweep | 0 | ValidMultiModDef.x | inventory | accept |  |  |
| t0-valid-NestedSubmodules | tier0-sweep | 0 | ValidNestSubmods.x | inventory | accept |  |  |
| t0-valid-OldNewOnStateField | tier0-sweep | 0 | ValidOldNewOnState.x | inventory | accept |  |  |
| t0-valid-OpenSequenceSeqFork | tier0-sweep | 0 | ValidOpenSeqSeq.x | inventory | accept | reject | Error on line 50: >>>ALTERNATIVEBRANCH<<< Incorrect Syntax - Error 32 - ours accepts (nested open sequence in a branch) |
| t0-valid-QuotedIdentifiers | tier0-sweep | 0 | ValidQuotedIdents.x | inventory | accept |  |  |
| t0-valid-RecordTypeAccess | tier0-sweep | 0 | ValidRecTypeAcc.x | inventory | accept |  |  |
| t0-valid-SFCUnnamedElements | tier0-sweep | 0 | ValidSfcUnnamed.x | inventory | accept |  |  |
| t0-valid-SequenceAlternative | tier0-sweep | 0 | ValidSeqAlt.x | inventory | accept |  |  |
| t0-valid-SequenceBasic | tier0-sweep | 0 | ValidSeqBasic.x | inventory | accept | accept | `[user]` confirmed compiling without issues in the editor - ours accepts. Establishes that our permissive SEQUENCE grammar agrees with the tool on the basic shape: init step, steps, transitions, body closing on a SEQTRANSITION |
| t0-valid-SequenceParallel | tier0-sweep | 0 | ValidSeqPar.x | inventory | accept |  |  |
| t0-valid-SubSeqTransition | tier0-sweep | 0 | ValidSubSeqTrans.x | inventory | accept |  |  |
| t0-valid-SubSeqTransitionAlt | tier0-sweep | 0 | ValidSubSeqTransB.x | inventory | accept | reject | Error on line 40: >>>ALTERNATIVEBRANCH<<< Incorrect Syntax - Error 32 - ours accepts |
| t0-valid-SubmoduleParams | tier0-sweep | 0 | ValidSubmodParams.x | inventory | accept | reject | ControllerType GLOBAL GlobalSetpoint not found at basepicture:controller2 - missing symbol; also a `template-broken` control for T1-007. Ours ACCEPTS |
| t0-valid-SubsequenceBlock | tier0-sweep | 0 | ValidSubseqBlk.x | inventory | accept |  |  |
| t0-valid-UnCompressedFullGrammar | tier0-sweep | 0 | ValidUnComprFull.x | inventory | accept | reject | 71 fuldnavn1, brugerident1, kommentar, form>>>å<<<. Incorrect Syntax - Error 76 - ours rejects too; non-ASCII identifier again |
| t0-valid-VariableModifiers | tier0-sweep | 0 | ValidVariaMods.x | inventory | accept |  |  |
| PRJ-PumpLib | cross-module | 3 | PumpLib.x | library | accept |  |  |
| PRJ-AuxLib | cross-module | 3 | AuxLib.x | library | accept | reject | line 17 >>>;<<< after DateCode_ 220100: AliasSym Expected (syntax) - ours rejects identically |
| PRJ-UnusedLib | cross-module | 3 | UnusedLib.x | library | accept |  |  |
| PRJ-LoopA | cross-module | 3 | LoopA.x | library | accept | reject | Error on line 17 ) : MODULEDEFINITION DateCode_ 210100>>>;<<< AliasSym Expected - DEFECTIVE TEMPLATE: the invocation uses the inline `) : MODULEDEFINITION DateCode_ N` form, but the tool wants a type symbol after the colon (`) : LeafType;` as in CtrlAcyc.x). Separate observation when loading it: "Library:LoopA reference removed to avoid loops", so library cycle detection does fire. Ours rejects identically (SEMICOLON, line 17) |
| PRJ-LoopB | cross-module | 3 | LoopB.x | library | accept | reject | Error on line 17 ) : MODULEDEFINITION DateCode_ 210100>>>;<<< AliasSym Expected - same DEFECTIVE TEMPLATE as LoopA (inline MODULEDEFINITION form); ours rejects identically |
| PRJ-Prog | cross-module | 3 | Prog.x | program | reject | reject | LoopA not found - DEFECTIVE TEMPLATE: the LoopAInst invocation sits inside LOCALVARIABLES instead of the module's submodule list, and Prog.z depends on the broken LoopA. Ours rejects (INVOCATION, line 13) |
| PRJ-ProgBadDep | cross-module | 3 | ProgBadDep.x | program | reject | reject | Error on line 13: PumpInst >>>Invocation<<< Incorrect Syntax - Error 76 - DEFECTIVE TEMPLATE: the PumpInst invocation sits inside LOCALVARIABLES; Error 76 also fires for the reserved word `Invocation` used as a name. Ours rejects (INVOCATION, line 13) |
