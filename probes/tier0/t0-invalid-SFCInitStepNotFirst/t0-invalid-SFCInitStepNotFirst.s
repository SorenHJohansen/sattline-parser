"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: SFCInitStepNotFirst"
(*
tier 0 sweep: invalid/SFCInitStepNotFirst.s INVALID: A SEQINITSTEP is not the first element of the sequence. The
   sequence opens with a SEQSTEP; the initial step must be the very first
   element so the sequence has a defined entry point.
   Expected: strict syntax-check fails at stage "validation" (SL-V022). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Output: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE NotFirst COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQSTEP StepA
         ACTIVECODE
            Output = 0;
      SEQTRANSITION TrA WAIT_FOR True
      SEQINITSTEP WrongOrder
         ACTIVECODE
            Output = 1;
      SEQTRANSITION TrDone WAIT_FOR True
   ENDSEQUENCE

ENDDEF (*BasePicture*);
