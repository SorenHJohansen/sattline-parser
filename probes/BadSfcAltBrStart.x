"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: SFCAlternativeBranchStartsWithStep"
(*
tier 0 sweep: invalid/SFCAlternativeBranchStartsWithStep.s INVALID: An ALTERNATIVESEQ branch opens with a SEQSTEP instead of a
   SEQTRANSITION. Each alternative branch must be entered through its own
   guard transition; starting a branch with a step leaves the divergence
   unguarded.
   Expected: strict syntax-check fails at stage "validation" (SL-V023). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Output: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE BadAlt COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Start
         ACTIVECODE
            Output = 0;
      SEQTRANSITION TrStart WAIT_FOR True
      ALTERNATIVESEQ
         SEQSTEP FirstBranchStep
            ACTIVECODE
               Output = 1;
         SEQTRANSITION TrA WAIT_FOR True
      ALTERNATIVEBRANCH
         SEQTRANSITION TrB WAIT_FOR True
      ENDALTERNATIVE
      SEQTRANSITION TrDone WAIT_FOR True
   ENDSEQUENCE

ENDDEF (*BasePicture*);
