"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: TransitionConditionNotBoolean"
(* INVALID: a transition guard must be boolean, exactly like an IF condition.
   `WAIT_FOR Count` reads an integer, so SL-V030 is reported.
   Expected: strict validation reports SL-V030. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Count: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE Counter (SeqControl, SeqTimer) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Init
      SEQTRANSITION TrCount WAIT_FOR Count
   ENDSEQUENCE

ENDDEF (*BasePicture*);
