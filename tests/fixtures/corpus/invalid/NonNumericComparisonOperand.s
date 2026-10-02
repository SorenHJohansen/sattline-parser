"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: NonNumericComparisonOperand"
(* INVALID: a comparison compares two values that are neither integer nor real.
   Probe ViolRealVsBool.x (2026-10-01) compared a real against a boolean and
   the real parser reported:
     Only integer and real allowed for this operator X > Flag1
   Probes EdgeBareDurZero.x, ValidDurAndTime.x and EdgeNegDurVal.x produced the
   identical message for duration, time and negated duration operands, so the
   rule is about the operand's type class, not about one datatype.
   Expected: strict syntax-check fails at stage "validation" (SL-V028). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   X: real  := 0.0;
   Flag1: boolean  := True;
   DurFull: duration  := Duration_Value "0d0h5m0s0ms";
   Sink: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Sink = X > Flag1 OR DurFull == DurFull;

ENDDEF (*BasePicture*);
