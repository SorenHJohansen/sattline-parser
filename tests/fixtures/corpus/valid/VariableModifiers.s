"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: VariableModifiers"
(* Exercises the three variable modifiers: Const, State, OpSave.
   Const variables may not be written in equations.
   State variables support :Old / :New temporal access.
   OpSave variables persist operator-set values across restarts.

   Modifier ORDER matters. The batch run 2026-10-05 proved:
      `OpSave State` / `OpSave Const`  -> rejected ("illegal attribute mix")
      `State OpSave`                   -> ACCEPTED (OpSaveStateReversed.x)
   So the accepted spelling is the reversed one pinned here; the rejected
   spellings are covered by invalid/OpSaveAndStateCombined.s and
   invalid/OpSaveConstCombined.s.

   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   MaxLimit: integer Const  := 100;
   ActiveFlag: boolean State  := False;
   OperatorSetpoint: real OpSave  := 50.0;
   SavedAndStated: integer State OpSave  := 0;
   Output: real  := 0.0;
   Changed: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      IF OperatorSetpoint > MaxLimit THEN
         Output = MaxLimit;
      ELSE
         Output = OperatorSetpoint;
      ENDIF;
      Changed = ActiveFlag:New AND NOT ActiveFlag:Old;
      SavedAndStated = SavedAndStated + 1;

ENDDEF (*BasePicture*);
