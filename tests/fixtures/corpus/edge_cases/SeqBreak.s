"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: SeqBreakEdge"
(* Edge case: SEQBREAK as the closing flag of a SEQFORK suffix.

   SEQFORK is not a sequence element of its own. It is a suffix of its host step
   or transition, reads one or more comma-separated target names, and may then
   consume a SEQBREAK. A standalone SEQBREAK is not in any position starter set,
   so the early-exit form is written as the fork's flag; see
   invalid/StandaloneSeqBreak.s for the rejected spelling. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Abort: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE Abortable (SeqControl, SeqTimer) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Init
         ENTERCODE
            Abort = False;
      SEQTRANSITION TrRun WAIT_FOR True
      SEQSTEP Working
      SEQTRANSITION TrCheck WAIT_FOR Abort
         SEQFORK SkipWork SEQBREAK
      SEQSTEP SkipWork
      SEQTRANSITION TrDone WAIT_FOR NOT Abort
      SEQSTEP Finish
      SEQTRANSITION TrEnd WAIT_FOR NOT Abort
   ENDSEQUENCE

ENDDEF (*BasePicture*);
