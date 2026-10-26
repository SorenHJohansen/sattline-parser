"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: TemporalVsNumericCompare"
(* Covers a duration or time operand compared against a NUMERIC LITERAL.

   Proved 2026-10-05 (batch run) - these three all compile in the real tool:
      EdgeDurCmpInt.x    Expired = (Elapsed == 5);
      EdgeDurCmpReal.x   Expired = (Elapsed > 2.5);
      EdgeTimeCmpInt.x   Expired = (Stamp == 5);

   SL-V028 therefore must allow a temporal operand when the other side of the
   comparison is a numeric literal, even though a temporal-versus-temporal
   comparison is rejected. That counter-case is covered by
   invalid/TemporalVsTemporalCompare.s.

   Expected: strict syntax-check passes.
   Expected: zero validation diagnostics. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   TimerType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      Timeout: duration := Duration_Value "0";

   LOCALVARIABLES
   Elapsed: duration := Duration_Value "0";
   Stamp: time := Time_Value "1984-01-01-00:00:00.000";
   Expired: boolean := False;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK TimerEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Expired = (Elapsed == 5) OR (Elapsed > 2.5) OR (Stamp == 5);

   ENDDEF (*TimerType*);

ModuleDef

ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);