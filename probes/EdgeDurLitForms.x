"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgeDurLitForms"
(*
open question: the actual subject of EdgeDurVarFmt.x, which died on a misplaced comment before the
   tool reached any literal. Duration literal forms: bare, negative leading minus, complex compound,
   and fractional seconds, all in declarations plus a parameter mapping.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   TimerType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      Timeout: duration := Duration_Value "0";

   LOCALVARIABLES
   DurFull: duration := Duration_Value "0d0h5m0s0ms";
   DurBare: duration := Duration_Value "7m6s123ms";
   DurHours: duration := Duration_Value "1h";
   DurComplex: duration := Duration_Value "5d5h3m6.5s";
   DurSeconds: duration := Duration_Value "12.345";
   DurZero: duration := Duration_Value "0";
   DurNegative: duration := Duration_Value "-0d0h5m0s0ms";
   Expired: boolean := False;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK TimerEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Expired = False;

   ENDDEF (*TimerType*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
