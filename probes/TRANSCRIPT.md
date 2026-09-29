# SattLine real-parser probe transcript
#
# A unit is a program/library triple: `file` is the .s; its .y and .z
# siblings travel with it. Fill `real status` with Accept or Reject per
# unit, and paste the exact message text (or message id) into `message`.
# This file is the input to analyze.py.
#
| id | area | tier | file | kind | expected | real status | message |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T1-001 | expression-types | 1 | rules/T1-001/control.s | control | accept |  |  |
| T1-001 | expression-types | 1 | rules/T1-001/violation-int-from-bool.s | violation | reject |  |  |
| T1-002 | expression-types | 1 | rules/T1-002/control.s | control | accept |  |  |
| T1-002 | expression-types | 1 | rules/T1-002/violation-real-vs-bool.s | violation | reject |  |  |
| T1-003 | expression-types | 1 | rules/T1-003/control.s | control | accept |  |  |
| T1-003 | expression-types | 1 | rules/T1-003/violation-int-condition.s | violation | reject |  |  |
| T1-004 | expression-types | 1 | rules/T1-004/control.s | control | accept |  |  |
| T1-004 | expression-types | 1 | rules/T1-004/violation-string-arg.s | violation | reject |  |  |
| T1-005 | expression-types | 1 | rules/T1-005/control.s | control | accept |  |  |
| T1-005 | expression-types | 1 | rules/T1-005/violation-too-deep.s | violation | reject |  |  |
| T1-006 | context-restricted-types | 1 | AnyTypeParam.x | control | accept | reject | Submodule Controller1, parameter Query not connected. |
| T1-006 | context-restricted-types | 1 | AnyTypeLocVar.x | violation | reject | reject | ControllerType GLOBAL GlobalSetpoint not found at BasePicture.Controller2 |
| T1-006b | context-restricted-types | 1 | rules/T1-006b/control.s | control | accept |  |  |
| T1-006b | context-restricted-types | 1 | rules/T1-006b/violation-anytype-field.s | violation | reject |  |  |
| T1-007 | statement-context | 1 | rules/T1-007/control-default-param.s | control | accept |  |  |
| T1-007 | statement-context | 1 | rules/T1-007/violation-default-scalar-localvar.s | violation | unknown |  |  |
| T1-008 | statement-context | 1 | rules/T1-008/control-with-init.s | control | accept |  |  |
| T1-008 | statement-context | 1 | rules/T1-008/violation-const-no-init.s | violation | accept |  |  |
| T1-009 | statement-context | 1 | rules/T1-009/control.s | control | accept |  |  |
| T1-009 | statement-context | 1 | rules/T1-009/violation-state-int.s | violation | unknown |  |  |
| T1-009 | statement-context | 1 | rules/T1-009/violation-opsave-string.s | violation | unknown |  |  |
| T1-010 | statement-context | 1 | rules/T1-010/control.s | control | accept |  |  |
| T1-010 | statement-context | 1 | rules/T1-010/violation-old-on-nonstate.s | violation | reject |  |  |
| T1-011 | sfc | 1 | rules/T1-011/control.s | control | accept |  |  |
| T1-011 | sfc | 1 | rules/T1-011/violation-step-accessor.s | violation | accept |  |  |
| T1-011 | sfc | 1 | rules/T1-011/violation-seq-reset.s | violation | accept |  |  |
| T1-012 | reserved-names | 1 | rules/T1-012/control-ordinary-name.s | control | accept |  |  |
| T1-012 | reserved-names | 1 | rules/T1-012/violation-var-on.s | violation | reject |  |  |
| T1-012 | reserved-names | 1 | rules/T1-012/violation-var-off.s | violation | reject |  |  |
| T1-012 | reserved-names | 1 | rules/T1-012/violation-var-groupdata.s | violation | reject |  |  |
| R-101 | sfc | 1 | rules/R-101/control-single-init.s | control | accept |  |  |
| R-101 | sfc | 1 | rules/R-101/violation-second-init.s | violation | accept |  |  |
| R-102 | sfc | 1 | rules/R-102/control-init-first.s | control | accept |  |  |
| R-102 | sfc | 1 | rules/R-102/violation-init-after-step.s | violation | accept |  |  |
| C-101 | moduletype-graph | 3 | rules/C-101/control-acyclic.s | control | accept |  |  |
| C-101 | moduletype-graph | 3 | rules/C-101/violation-cycle.s | violation | reject |  |  |
| C-102 | moduletype-graph | 3 | rules/C-102/control-acyclic.s | control | accept |  |  |
| C-102 | moduletype-graph | 3 | rules/C-102/violation-self-instance.s | violation | reject |  |  |
| C-103 | moduletype-graph | 3 | rules/C-103/control-instantiated.s | control | accept |  |  |
| C-103 | moduletype-graph | 3 | rules/C-103/violation-unused.s | violation | reject |  |  |
| C-104 | moduletype-graph | 3 | rules/C-104/control-defined.s | control | accept |  |  |
| C-104 | moduletype-graph | 3 | rules/C-104/violation-undefined-binding.s | violation | reject |  |  |
| C-105 | moduletype-graph | 3 | rules/C-105/control-full-arity.s | control | accept |  |  |
| C-105 | moduletype-graph | 3 | rules/C-105/violation-missing-mapping.s | violation | reject |  |  |
| C-106 | moduletype-graph | 3 | rules/C-106/control-typed-transfer.s | control | accept |  |  |
| C-106 | moduletype-graph | 3 | rules/C-106/violation-bool-to-real.s | violation | reject |  |  |
| C-201 | graphics-correlation | 3 | rules/C-201/control-date-match.s | control | accept |  |  |
| C-201 | graphics-correlation | 3 | rules/C-201/violation-date-shift.s | violation | reject |  |  |
| C-202 | graphics-correlation | 3 | rules/C-202/control-count-match.s | control | accept |  |  |
| C-202 | graphics-correlation | 3 | rules/C-202/violation-extra-object.s | violation | reject |  |  |
| t0-valid-AllDatatypes | tier0-sweep | 0 | tier0/t0-valid-AllDatatypes.s | inventory | accept |  |  |
| t0-valid-BuiltinCalls | tier0-sweep | 0 | tier0/t0-valid-BuiltinCalls.s | inventory | accept |  |  |
| t0-valid-CompressedFullGrammar | tier0-sweep | 0 | tier0/t0-valid-CompressedFullGrammar.s | inventory | accept |  |  |
| t0-valid-CompressedSequenceBasic | tier0-sweep | 0 | tier0/t0-valid-CompressedSequenceBasic.s | inventory | accept |  |  |
| t0-valid-ControlFlow | tier0-sweep | 0 | tier0/t0-valid-ControlFlow.s | inventory | accept |  |  |
| t0-valid-CoordInVarTail | tier0-sweep | 0 | tier0/t0-valid-CoordInVarTail.s | inventory | accept |  |  |
| t0-valid-DefaultInitOnRecord | tier0-sweep | 0 | tier0/t0-valid-DefaultInitOnRecord.s | inventory | accept |  |  |
| t0-valid-DurationAndTime | tier0-sweep | 0 | tier0/t0-valid-DurationAndTime.s | inventory | accept |  |  |
| t0-valid-GraphObjectEnableTails | tier0-sweep | 0 | tier0/t0-valid-GraphObjectEnableTails.s | inventory | accept |  |  |
| t0-valid-GraphObjectShapes | tier0-sweep | 0 | tier0/t0-valid-GraphObjectShapes.s | inventory | accept |  |  |
| t0-valid-GraphObjectsSectionLayer | tier0-sweep | 0 | tier0/t0-valid-GraphObjectsSectionLayer.s | inventory | accept |  |  |
| t0-valid-GraphicsObjects | tier0-sweep | 0 | tier0/t0-valid-GraphicsObjects.s | inventory | accept |  |  |
| t0-valid-InteractEnableTails | tier0-sweep | 0 | tier0/t0-valid-InteractEnableTails.s | inventory | accept |  |  |
| t0-valid-InteractWidgets | tier0-sweep | 0 | tier0/t0-valid-InteractWidgets.s | inventory | accept |  |  |
| t0-valid-MinimalProgram | tier0-sweep | 0 | tier0/t0-valid-MinimalProgram.s | inventory | accept |  |  |
| t0-valid-MultiEquationBlocks | tier0-sweep | 0 | tier0/t0-valid-MultiEquationBlocks.s | inventory | accept |  |  |
| t0-valid-MultiTypedefBlocks | tier0-sweep | 0 | tier0/t0-valid-MultiTypedefBlocks.s | inventory | accept |  |  |
| t0-valid-MultipleModuleDefBlocks | tier0-sweep | 0 | tier0/t0-valid-MultipleModuleDefBlocks.s | inventory | accept |  |  |
| t0-valid-NestedSubmodules | tier0-sweep | 0 | tier0/t0-valid-NestedSubmodules.s | inventory | accept |  |  |
| t0-valid-OldNewOnStateField | tier0-sweep | 0 | tier0/t0-valid-OldNewOnStateField.s | inventory | accept |  |  |
| t0-valid-OpenSequenceSeqFork | tier0-sweep | 0 | tier0/t0-valid-OpenSequenceSeqFork.s | inventory | accept |  |  |
| t0-valid-QuotedIdentifiers | tier0-sweep | 0 | tier0/t0-valid-QuotedIdentifiers.s | inventory | accept |  |  |
| t0-valid-RecordTypeAccess | tier0-sweep | 0 | tier0/t0-valid-RecordTypeAccess.s | inventory | accept |  |  |
| t0-valid-SFCUnnamedElements | tier0-sweep | 0 | tier0/t0-valid-SFCUnnamedElements.s | inventory | accept |  |  |
| t0-valid-SequenceAlternative | tier0-sweep | 0 | tier0/t0-valid-SequenceAlternative.s | inventory | accept |  |  |
| t0-valid-SequenceBasic | tier0-sweep | 0 | tier0/t0-valid-SequenceBasic.s | inventory | accept |  |  |
| t0-valid-SequenceParallel | tier0-sweep | 0 | tier0/t0-valid-SequenceParallel.s | inventory | accept |  |  |
| t0-valid-SubSeqTransition | tier0-sweep | 0 | tier0/t0-valid-SubSeqTransition.s | inventory | accept |  |  |
| t0-valid-SubSeqTransitionAlt | tier0-sweep | 0 | tier0/t0-valid-SubSeqTransitionAlt.s | inventory | accept |  |  |
| t0-valid-SubmoduleParams | tier0-sweep | 0 | tier0/t0-valid-SubmoduleParams.s | inventory | accept |  |  |
| t0-valid-SubsequenceBlock | tier0-sweep | 0 | tier0/t0-valid-SubsequenceBlock.s | inventory | accept |  |  |
| t0-valid-UnCompressedFullGrammar | tier0-sweep | 0 | tier0/t0-valid-UnCompressedFullGrammar.s | inventory | accept |  |  |
| t0-valid-VariableModifiers | tier0-sweep | 0 | tier0/t0-valid-VariableModifiers.s | inventory | accept |  |  |
| t0-edge-ArithmeticPrecedence | tier0-sweep | 0 | tier0/t0-edge-ArithmeticPrecedence.s | inventory | accept |  |  |
| t0-edge-BareDurationZero | tier0-sweep | 0 | tier0/t0-edge-BareDurationZero.s | inventory | accept |  |  |
| t0-edge-CaseInsensitiveIdentifiers | tier0-sweep | 0 | tier0/t0-edge-CaseInsensitiveIdentifiers.s | inventory | accept |  |  |
| t0-edge-CommentInsideEquation | tier0-sweep | 0 | tier0/t0-edge-CommentInsideEquation.s | inventory | accept |  |  |
| t0-edge-ConstStringSetGetPos | tier0-sweep | 0 | tier0/t0-edge-ConstStringSetGetPos.s | inventory | accept |  |  |
| t0-edge-CoordinateInvarTail | tier0-sweep | 0 | tier0/t0-edge-CoordinateInvarTail.s | inventory | accept |  |  |
| t0-edge-DeeplyNestedComments | tier0-sweep | 0 | tier0/t0-edge-DeeplyNestedComments.s | inventory | accept |  |  |
| t0-edge-DurationInParameterMapping | tier0-sweep | 0 | tier0/t0-edge-DurationInParameterMapping.s | inventory | accept |  |  |
| t0-edge-DurationVariousFormats | tier0-sweep | 0 | tier0/t0-edge-DurationVariousFormats.s | inventory | accept |  |  |
| t0-edge-ElsifExpression | tier0-sweep | 0 | tier0/t0-edge-ElsifExpression.s | inventory | accept |  |  |
| t0-edge-EmptyCodeBlocks | tier0-sweep | 0 | tier0/t0-edge-EmptyCodeBlocks.s | inventory | accept |  |  |
| t0-edge-EmptyRecordType | tier0-sweep | 0 | tier0/t0-edge-EmptyRecordType.s | inventory | accept |  |  |
| t0-edge-FrameModuleInvocation | tier0-sweep | 0 | tier0/t0-edge-FrameModuleInvocation.s | inventory | accept |  |  |
| t0-edge-GlobalParameterMapping | tier0-sweep | 0 | tier0/t0-edge-GlobalParameterMapping.s | inventory | accept |  |  |
| t0-edge-KeywordPrefixedIdentifiers | tier0-sweep | 0 | tier0/t0-edge-KeywordPrefixedIdentifiers.s | inventory | accept |  |  |
| t0-edge-LegacySequenceNoInitStep | tier0-sweep | 0 | tier0/t0-edge-LegacySequenceNoInitStep.s | inventory | accept |  |  |
| t0-edge-MinimalSequence | tier0-sweep | 0 | tier0/t0-edge-MinimalSequence.s | inventory | accept |  |  |
| t0-edge-ModuleDefNoTrailingEnddef | tier0-sweep | 0 | tier0/t0-edge-ModuleDefNoTrailingEnddef.s | inventory | accept |  |  |
| t0-edge-ModuleOptions | tier0-sweep | 0 | tier0/t0-edge-ModuleOptions.s | inventory | accept |  |  |
| t0-edge-NegativeDurationValue | tier0-sweep | 0 | tier0/t0-edge-NegativeDurationValue.s | inventory | accept |  |  |
| t0-edge-OldNewOnDottedStateField | tier0-sweep | 0 | tier0/t0-edge-OldNewOnDottedStateField.s | inventory | accept |  |  |
| t0-edge-OpSaveAndStateCombined | tier0-sweep | 0 | tier0/t0-edge-OpSaveAndStateCombined.s | inventory | accept |  |  |
| t0-edge-QuotedIdentifierMaxLength | tier0-sweep | 0 | tier0/t0-edge-QuotedIdentifierMaxLength.s | inventory | accept |  |  |
| t0-edge-ScanGroupClause | tier0-sweep | 0 | tier0/t0-edge-ScanGroupClause.s | inventory | accept |  |  |
| t0-edge-SeqBreak | tier0-sweep | 0 | tier0/t0-edge-SeqBreak.s | inventory | accept |  |  |
| t0-edge-SeqForkMultipleTargets | tier0-sweep | 0 | tier0/t0-edge-SeqForkMultipleTargets.s | inventory | accept |  |  |
| t0-edge-SequenceAlternative | tier0-sweep | 0 | tier0/t0-edge-SequenceAlternative.s | inventory | accept |  |  |
| t0-edge-SequenceParallel | tier0-sweep | 0 | tier0/t0-edge-SequenceParallel.s | inventory | accept |  |  |
| t0-edge-SimpleModuleTypeInvocation | tier0-sweep | 0 | tier0/t0-edge-SimpleModuleTypeInvocation.s | inventory | accept |  |  |
| t0-edge-SubSequenceDefinition | tier0-sweep | 0 | tier0/t0-edge-SubSequenceDefinition.s | inventory | accept |  |  |
| t0-edge-SubSequenceTransition | tier0-sweep | 0 | tier0/t0-edge-SubSequenceTransition.s | inventory | accept |  |  |
| t0-edge-TerminalSeqStep | tier0-sweep | 0 | tier0/t0-edge-TerminalSeqStep.s | inventory | accept |  |  |
| t0-edge-TimeValueInit | tier0-sweep | 0 | tier0/t0-edge-TimeValueInit.s | inventory | accept |  |  |
| t0-edge-UnicodeIdentifiers | tier0-sweep | 0 | tier0/t0-edge-UnicodeIdentifiers.s | inventory | accept |  |  |
| t0-invalid-BadBareDurationString | tier0-sweep | 0 | BadBareDurStr.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) |
| t0-invalid-BadBareTimeString | tier0-sweep | 0 | BadBareTimeStr.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) |
| t0-invalid-BadDurationLiteral | tier0-sweep | 0 | tier0/t0-invalid-BadDurationLiteral.s | inventory | reject |  |  |
| t0-invalid-BadTimeLiteral | tier0-sweep | 0 | tier0/t0-invalid-BadTimeLiteral.s | inventory | reject |  |  |
| t0-invalid-BuiltinDatatypeTypo | tier0-sweep | 0 | BadBuiltinDatatype.x | inventory | reject | reject | "Datatype intege not found" (dialog: replace / open new library / delete / abort) |
| t0-invalid-BuiltinOutArgNotVariable | tier0-sweep | 0 | BadBuiltinOutArg.x | inventory | reject | reject | Type error in if-sentence. If UseA THEN DestinationA ELSE DestinationB ENDIF |
| t0-invalid-BuiltinWrongArity | tier0-sweep | 0 | BadBuiltinWrong.x | inventory | reject | reject | Too few parameters EqualString(Name1, Name2) |
| t0-invalid-ConsecutiveSeqSteps | tier0-sweep | 0 | BadConsecSeqSteps.x | inventory | reject | reject | line 28 >>>SEQSTEP<<< Step2. Incorrect syntax - Error 32 |
| t0-invalid-ConstVarAsBuiltinOutArg | tier0-sweep | 0 | BadConstVarAs.x | inventory | reject | reject | out parameter is not a variable: Fixed |
| t0-invalid-CrossModuleContractMismatch | tier0-sweep | 0 | BadCrossMod.x | inventory | reject | reject | Submodule Child, parameter EnableFlag: Variable CounterValue is an invalid type |
| t0-invalid-DatatypeShadowsBuiltinName | tier0-sweep | 0 | BadDatatypeShadows.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) |
| t0-invalid-DuplicateDatatypeName | tier0-sweep | 0 | BadDupDatatypeName.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) |
| t0-invalid-DuplicateModuletypeName | tier0-sweep | 0 | BadDupModTypeName.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) |
| t0-invalid-DuplicateRecordFieldName | tier0-sweep | 0 | BadDupRecFldName.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) |
| t0-invalid-DuplicateSFCElementNames | tier0-sweep | 0 | BadDupSfcElemNames.x | inventory | reject | reject | error in sequence block |
| t0-invalid-DuplicateSiblingSubmodules | tier0-sweep | 0 | BadDupSibSubmods.x | inventory | reject | reject | module name is not unique: SensorA |
| t0-invalid-DuplicateVariableNames | tier0-sweep | 0 | BadDupVariaNames.x | inventory | reject | accept | compiles without errors (IDE refuses to create via editors; direct file load accepts) |
| t0-invalid-EncodingStress | tier0-sweep | 0 | tier0/t0-invalid-EncodingStress.s | inventory | reject |  |  |
| t0-invalid-FreestandingCommentInModuleCode | tier0-sweep | 0 | tier0/t0-invalid-FreestandingCommentInModuleCode.s | inventory | reject |  |  |
| t0-invalid-GraphObjectsDoubleLayer | tier0-sweep | 0 | tier0/t0-invalid-GraphObjectsDoubleLayer.s | inventory | reject |  |  |
| t0-invalid-InitValueTypeMismatch | tier0-sweep | 0 | tier0/t0-invalid-InitValueTypeMismatch.s | inventory | reject |  |  |
| t0-invalid-Malformed | tier0-sweep | 0 | tier0/t0-invalid-Malformed.s | inventory | reject |  |  |
| t0-invalid-ModuleCodeWithoutModuleDef | tier0-sweep | 0 | tier0/t0-invalid-ModuleCodeWithoutModuleDef.s | inventory | reject |  |  |
| t0-invalid-NotSattLine | tier0-sweep | 0 | tier0/t0-invalid-NotSattLine.s | inventory | reject |  |  |
| t0-invalid-OldNewOnNonState | tier0-sweep | 0 | tier0/t0-invalid-OldNewOnNonState.s | inventory | reject |  |  |
| t0-invalid-OldNewOnNonStateRecordField | tier0-sweep | 0 | tier0/t0-invalid-OldNewOnNonStateRecordField.s | inventory | reject |  |  |
| t0-invalid-OversizedInput | tier0-sweep | 0 | tier0/t0-invalid-OversizedInput.s | inventory | reject |  |  |
| t0-invalid-SFCAlternativeBranchStartsWithStep | tier0-sweep | 0 | tier0/t0-invalid-SFCAlternativeBranchStartsWithStep.s | inventory | reject |  |  |
| t0-invalid-SFCInitStepNotFirst | tier0-sweep | 0 | tier0/t0-invalid-SFCInitStepNotFirst.s | inventory | reject |  |  |
| t0-invalid-SFCInitStepRepeated | tier0-sweep | 0 | tier0/t0-invalid-SFCInitStepRepeated.s | inventory | reject |  |  |
| t0-invalid-SFCParallelBranchStartsWithTransition | tier0-sweep | 0 | tier0/t0-invalid-SFCParallelBranchStartsWithTransition.s | inventory | reject |  |  |
| t0-invalid-SeqForkUnknownTarget | tier0-sweep | 0 | tier0/t0-invalid-SeqForkUnknownTarget.s | inventory | reject |  |  |
| t0-invalid-StringLiteralInCallArgument | tier0-sweep | 0 | tier0/t0-invalid-StringLiteralInCallArgument.s | inventory | reject |  |  |
| t0-invalid-UndefinedVariableRef | tier0-sweep | 0 | tier0/t0-invalid-UndefinedVariableRef.s | inventory | reject |  |  |
| t0-invalid-UnknownDatatypeName | tier0-sweep | 0 | tier0/t0-invalid-UnknownDatatypeName.s | inventory | reject |  |  |
| t0-invalid-UnterminatedComment | tier0-sweep | 0 | tier0/t0-invalid-UnterminatedComment.s | inventory | reject |  |  |
| t0-invalid-WriteToConstVariable | tier0-sweep | 0 | tier0/t0-invalid-WriteToConstVariable.s | inventory | reject |  |  |
| PRJ-PumpLib | cross-module | 3 | proj/PumpLib/PumpLib.s | library | accept |  |  |
| PRJ-AuxLib | cross-module | 3 | AuxLib.x | library | accept | reject | line 17 >>>;<<< after DateCode_ 220100: AliasSym Expected (syntax) - ours rejects identically |
| PRJ-UnusedLib | cross-module | 3 | proj/UnusedLib/UnusedLib.s | library | accept |  |  |
| PRJ-LoopA | cross-module | 3 | proj/LoopA/LoopA.s | library | accept |  |  |
| PRJ-LoopB | cross-module | 3 | proj/LoopB/LoopB.s | library | accept |  |  |
| PRJ-Prog | cross-module | 3 | proj/Prog/Prog.s | program | reject |  |  |
| PRJ-ProgBadDep | cross-module | 3 | proj/ProgBadDep/ProgBadDep.s | program | reject |  |  |
