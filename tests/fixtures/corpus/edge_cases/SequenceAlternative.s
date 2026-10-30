"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: SeqAltEdge"
(* Edge case: alternative group between two steps.
   Grammar rules: seqalternative / ALTERNATIVEBRANCH.
   ALTERNATIVESEQ is a transition-position construct, so it must sit where a
   transition may sit: directly after a step, never directly after another
   transition. Placing it straight after a transition is rejected with
   ">>>ALTERNATIVESEQ<<< EndLoopSeqSym Expected". *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Sel: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE Alt (SeqControl, SeqTimer) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Init
      SEQTRANSITION TrGo WAIT_FOR Sel > 0
      SEQSTEP Choose
      ALTERNATIVESEQ
         SEQTRANSITION TrA WAIT_FOR Sel == 1
         SEQSTEP OptA
         SEQTRANSITION TrDone WAIT_FOR True
      ALTERNATIVEBRANCH
         SEQTRANSITION TrB WAIT_FOR Sel == 2
         SEQSTEP OptB
         SEQTRANSITION TrDone2 WAIT_FOR True
      ENDALTERNATIVE
      SEQSTEP Finish
      SEQTRANSITION TrEnd WAIT_FOR True
   ENDSEQUENCE

ENDDEF (*BasePicture*);
