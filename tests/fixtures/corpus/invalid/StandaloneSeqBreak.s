"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: SeqBreakStandalone"
(* INVALID: SEQBREAK as a standalone sequence element.

   Native evidence (006f9850, 0070a100, 0070d180): SEQBREAK is only read after a
   SEQFORK target list, and SEQFORK itself is only a suffix of a step or a
   transition. SEQBREAK appears in none of the sequence position starter sets.

   Real tool (probe EdgeSeqBrk.x, 2026-10-05):
     Error on line 27 >>>SEQBREAK<<< Unexpected symbol or end of input
   Ours rejects the same construct at parse time. *)

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
      SEQBREAK
      SEQTRANSITION TrDone WAIT_FOR NOT Abort
      SEQSTEP Finish
      SEQTRANSITION TrEnd WAIT_FOR NOT Abort
   ENDSEQUENCE

ENDDEF (*BasePicture*);
