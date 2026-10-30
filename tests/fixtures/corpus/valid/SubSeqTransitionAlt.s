"Syntax version 2.23, date: 2026-08-25-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-25-12:00:00.000, name: SubSeqTransitionAlt"
(* Covers SUBSEQTRANSITION whose body is an ALTERNATIVESEQ.
   The alternative group inside a transition sub uses a single
   ALTERNATIVESEQ marker, matching the strict SattLine syntax.
   A redundant double ALTERNATIVESEQ marker would be rejected.

   Each branch closes on its own transition and a step follows the
   sub-transition before the next transition. Alternative branches take the form
   T (S T | M)* and SUBSEQTRANSITION is a transition-position construct, so a
   branch ending on a step, or two transitions in a row, is rejected with
   "ALTERNATIVEBRANCH ... Incorrect Syntax ... Error 32". *)


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
            SEQTRANSITION TrModeA WAIT_FOR Mode == 1
            SEQSTEP ModeA
               ACTIVECODE
                  OutputA = OutputA + 1;
            SEQTRANSITION TrModeADone WAIT_FOR True
         ALTERNATIVEBRANCH
            SEQTRANSITION TrModeB WAIT_FOR Mode == 2
            SEQSTEP ModeB
               ACTIVECODE
                  OutputB = OutputB + 1;
            SEQTRANSITION TrModeBDone WAIT_FOR True
         ENDALTERNATIVE
      ENDSUBSEQTRANSITION
      SEQSTEP PhaseDone
      SEQTRANSITION TrDone WAIT_FOR NOT StartCmd
   ENDSEQUENCE

ENDDEF (*BasePicture*);
