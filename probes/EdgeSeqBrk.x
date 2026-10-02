"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: SeqBreakEdge"
(*
tier 0 sweep: edge_cases/SeqBreak.s Edge case: SEQBREAK used to exit a sequence early.
   Grammar rule: seqbreak. *   Added a closing SEQTRANSITION: the body originally ended on SEQSTEP Finish,
   which is illegal in itself (SL-V033). That was incidental to what this file
   tests, and it masked the real SEQBREAK question. *)

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
