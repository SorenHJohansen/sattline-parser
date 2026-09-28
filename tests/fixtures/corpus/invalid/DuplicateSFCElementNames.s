"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DuplicateSFCElementNames"
(* INVALID: Two SFC elements share the same name. The SEQSTEP "Work" appears
   twice in the same sequence; SFC element names must be unique so SEQFORK
   targets and step runtime accessors are unambiguous.
   Expected: strict syntax-check fails at stage "validation" (SL-V021). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Output: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE DupeSeq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Start
         EXITCODE
            Output = 0;
      SEQTRANSITION TrFirst WAIT_FOR True
      SEQSTEP Work
         ACTIVECODE
            Output = 1;
      SEQTRANSITION TrSecond WAIT_FOR True
      SEQSTEP Work
         ACTIVECODE
            Output = 2;
      SEQTRANSITION TrDone WAIT_FOR True
   ENDSEQUENCE

ENDDEF (*BasePicture*);
