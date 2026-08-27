"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DurationAndTime"
(* Covers duration and time variable declarations and usage.
   Duration and time variables require Duration_Value and Time_Value keywords.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   DurFull: duration  := Duration_Value "0d0h5m0s0ms";
   DurBare: duration  := Duration_Value "7m6s123ms";
   DurHours: duration  := Duration_Value "1h";
   DurMinutes: duration  := Duration_Value "4m";
   DurComplex: duration  := Duration_Value "5d5h3m6.5s";
   DurSeconds: duration  := Duration_Value "12.345";
   DurZero: duration  := Duration_Value "0";
   DurNegative: duration  := Duration_Value "-0d0h5m0s0ms";
   TimeFull: time  := Time_Value "1984-01-01-00:00:00.000";
   TimeBare: time  := Time_Value "2026-04-23-12:00:00.000";
   TimeMidnight: time  := Time_Value "2000-12-31-23:59:59.999";
   Sink: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Sink = DurFull == DurBare OR TimeFull == TimeBare OR DurZero == DurHours;

ENDDEF (*BasePicture*);
