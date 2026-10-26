"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: TemporalVsTemporalCompare"
(* INVALID: comparing two duration operands, or two time operands.

   This is the counter-evidence to valid/TemporalVsNumericCompare.s. The real
   tool compiles a duration or time compared against a NUMERIC LITERAL, but
   these three probes were all REJECTED:
      EdgeBareDurZero.x   Sink = ZeroDur == ZeroFull;
      EdgeNegDurVal.x     Sink = NegFive == NegHour OR NegSmall == NegFive;
      ValidDurAndTime.x   Sink = DurFull == DurBare OR TimeFull == TimeBare
                                  OR DurZero == DurHours;

   Both sides are the same non-numeric family, so neither can be widened to a
   numeric comparison - SL-V028 stays. Kept as a pair with
   valid/TemporalVsNumericCompare.s so the numeric-literal relaxation cannot
   quietly absorb this case.

   Expected: strict syntax-check passes.
   Expected: SL-V028. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   ZeroDur: duration  := Duration_Value "0";
   ZeroFull: duration  := Duration_Value "0d0h0m0s0ms";
   NegFive: duration  := Duration_Value "-0d0h5m0s0ms";
   NegHour: duration  := Duration_Value "-1d0h0m0s0ms";
   NegSmall: duration  := Duration_Value "-0d0h0m30s500ms";
   DurFull: duration  := Duration_Value "0";
   DurBare: duration  := Duration_Value "1h";
   DurZero: duration  := Duration_Value "0";
   DurHours: duration  := Duration_Value "1h";
   TimeFull: time  := Time_Value "1984-01-01-00:00:00.000";
   TimeBare: time  := Time_Value "2026-04-23-12:00:00.000";
   Sink: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Sink = ZeroDur == ZeroFull;
      Sink = NegFive == NegHour;
      Sink = NegSmall == NegFive;
      Sink = DurFull == DurBare;
      Sink = TimeFull == TimeBare;
      Sink = DurZero == DurHours;

ENDDEF (*BasePicture*);