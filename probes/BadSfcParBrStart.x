"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: SFCParallelBranchStartsWithTransition"
(*
tier 0 sweep: invalid/SFCParallelBranchStartsWithTransition.s INVALID: A PARALLELSEQ branch opens with a SEQTRANSITION instead of a
   SEQSTEP. Parallel branches must begin with a step so the divergence
   activates a concrete activity on each branch.
   Expected: strict syntax-check fails at stage "validation" (SL-V024). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Output: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE BadPar COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Start
         ACTIVECODE
            Output = 0;
      SEQTRANSITION TrStart WAIT_FOR True
      PARALLELSEQ
         SEQTRANSITION TrBranchA WAIT_FOR True
         SEQSTEP StageOne
            ACTIVECODE
               Output = 1;
      PARALLELBRANCH
         SEQSTEP BranchB
            ACTIVECODE
               Output = 2;
      ENDPARALLEL
      SEQTRANSITION TrDone WAIT_FOR True
   ENDSEQUENCE

ENDDEF (*BasePicture*);
