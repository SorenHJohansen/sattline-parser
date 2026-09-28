"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: SFCInitStepRepeated"
(*
tier 0 sweep: invalid/SFCInitStepRepeated.s INVALID: A sequence declares two SEQINITSTEP blocks. A sequence may have
   exactly one initial step; a second initial step leaves the entry point
   ambiguous.
   Expected: strict syntax-check fails at stage "validation" (SL-V022). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Output: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE TwoInits COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP First
         ACTIVECODE
            Output = 0;
      SEQTRANSITION TrA WAIT_FOR True
      SEQINITSTEP Second
         ACTIVECODE
            Output = 1;
      SEQTRANSITION TrDone WAIT_FOR True
   ENDSEQUENCE

ENDDEF (*BasePicture*);
