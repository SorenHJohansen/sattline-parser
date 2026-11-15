"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: SequenceWithoutInitStep"
(* EDGE CASE: A closed SEQUENCE that begins with a SEQSTEP instead of
   SEQINITSTEP. The real tool loads such a sequence, so the parser accepts it
   and validation reports nothing: SEQUENCE_REQUIRES_INIT_STEP is retired.
   Expected: strict syntax-check passes with no diagnostics. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   StartCmd: boolean  := False;
   Output: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE LegacySeq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQSTEP Step1
         ENTERCODE
            Output = 0;
      SEQTRANSITION TrStart WAIT_FOR StartCmd
      SEQSTEP Step2
         ACTIVECODE
            Output = Output + 1;
      SEQTRANSITION TrDone WAIT_FOR Output >= 5
   ENDSEQUENCE

ENDDEF (*BasePicture*);
