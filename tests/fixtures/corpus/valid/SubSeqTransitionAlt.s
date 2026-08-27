"Syntax version 2.23, date: 2026-08-25-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-25-12:00:00.000, name: SubSeqTransitionAlt"
(* Covers SUBSEQTRANSITION whose body is an ALTERNATIVESEQ.
   The ABB export emits a double ALTERNATIVESEQ marker (#34 #34)
   in this context: the first acts as a structural wrapper and the
   second starts the actual alternative branches.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   StartCmd: boolean  := False;
   Ready: boolean  := False;
   Mode: integer  := 0;
   OutputA: integer  := 0;
   OutputB: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE MainSeq (SeqControl, SeqTimer) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Idle
         ENTERCODE
            StartCmd = False;
      SEQTRANSITION TrStart WAIT_FOR StartCmd
      SEQSTEP Active
         ENTERCODE
            OutputA = 0;
            OutputB = 0;
      SUBSEQTRANSITION TrCheckPhase
         ALTERNATIVESEQ
         ALTERNATIVESEQ
            SEQTRANSITION TrModeA WAIT_FOR Mode == 1
            SEQSTEP ModeA
               ACTIVECODE
                  OutputA = OutputA + 1;
         ALTERNATIVEBRANCH
            SEQTRANSITION TrModeB WAIT_FOR Mode == 2
            SEQSTEP ModeB
               ACTIVECODE
                  OutputB = OutputB + 1;
         ENDALTERNATIVE
      ENDSUBSEQTRANSITION
      SEQTRANSITION TrDone WAIT_FOR NOT StartCmd
   ENDSEQUENCE

ENDDEF (*BasePicture*);
