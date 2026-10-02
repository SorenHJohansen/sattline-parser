"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: BareDurationZero"
(* Covers "0" as a duration init value with Duration_Value keyword.
   In SattLine a duration may be initialized with Duration_Value "0" without
   a unit suffix. This is the edge case because "0" could in principle be
   ambiguous with a bare integer, but the Duration_Value keyword makes it clear.
   Expected: strict syntax-check passes (same as DurZero in DurationAndTime.s).

   Probe 2026-10-01: the real parser accepts both of these declarations, but
   rejects *comparing* two durations -- it reported
     Only integer and real allowed for this operator ZeroDur == ZeroFull
   for exactly the statement below, so the declaration-only form is what this
   fixture covers. See invalid/NonNumericComparisonOperand.s. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   ZeroDur: duration  := Duration_Value "0";
   ZeroFull: duration  := Duration_Value "0d0h0m0s0ms";
   Sink: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Sink = True;

ENDDEF (*BasePicture*);
