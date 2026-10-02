"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: OpSaveStateMix"
(* Covers a variable declared with both OpSave and State modifiers.
   OpSave restores the value on power-up, State enables :Old / :New access.
   The editor rejects the pair: "Invalid attribute identifier or invalid
   combination of attributes". The grammar still parses any modifier sequence;
   the combination is caught by validation rule SL-V031.
   Expected: rejected by validation. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   NormalVar: integer  := 0;
   SavedVar: integer  OpSave := 0;
   StateVar: integer  State := 0;
   SavedStateVar: integer  OpSave State := 0;
   SavedStateBool: boolean  OpSave State := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      NormalVar = NormalVar + 1;
      SavedVar = SavedVar + 1;
      StateVar = StateVar + 1;
      SavedStateVar = SavedStateVar + 1;
      IF SavedStateBool:Old AND NOT SavedStateBool:New THEN
         NormalVar = 0;
      ENDIF;

ENDDEF (*BasePicture*);
