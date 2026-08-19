"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: SFCUnnamedElements"
(* Covers unnamed SEQUENCE elements, matching real SattLine:
   - SEQINITSTEP without a NAME
   - SEQTRANSITION without a NAME
   - SEQSTEP without a NAME
   Only the element name is optional; the code block run and WAIT_FOR
   condition are still required.
   Expected: strict syntax-check passes; all three elements report name=None. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   StartCmd: boolean  := False;
   RunCmd: boolean  := False;
   DoneCmd: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   SEQUENCE Main (SeqControl, SeqTimer) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP
         ENTERCODE
            StartCmd = False;
      SEQTRANSITION WAIT_FOR StartCmd
      SEQSTEP
         ENTERCODE
            RunCmd = True;
         EXITCODE
            RunCmd = False;
      SEQTRANSITION WAIT_FOR DoneCmd
   ENDSEQUENCE

ENDDEF (*BasePicture*);
