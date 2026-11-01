"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: AmbiguousForkTarget"
(* INVALID: Two transitions share the name "TrSame" and a SEQFORK targets
   that name. The fork target cannot be resolved to one transition, so it is
   ambiguous in addition to the duplicate element name.
   Expected: strict syntax-check fails at stage "validation" (SL-V021 and
   SL-V056). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Output: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE AmbiguousFork COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Start
         EXITCODE
            Output = 0;
      SEQTRANSITION TrFirst WAIT_FOR True
      SEQSTEP Work
         ACTIVECODE
            Output = 1;
         SEQFORK TrSame
      SEQTRANSITION TrSame WAIT_FOR True
      SEQSTEP Finish
         ACTIVECODE
            Output = 2;
      SEQTRANSITION TrSame WAIT_FOR True
   ENDSEQUENCE

ENDDEF (*BasePicture*);
