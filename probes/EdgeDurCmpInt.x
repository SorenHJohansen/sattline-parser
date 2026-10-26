"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgeDurCmpInt"
(*
open question: ValidDurAndTime.x was rejected with `only integer and real allowed for this operator:
   DurFull == DurBare` (duration vs duration). The message implies integer IS allowed, so this tests
   duration vs integer.
   Expected: unknown. *)

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
      Expired = (Elapsed == 5);

   ENDDEF (*TimerType*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
