"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgeDurCmpReal"
(*
open question: duration vs real, the other half of the `only integer and real allowed` message.
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
      Expired = (Elapsed > 2.5);

   ENDDEF (*TimerType*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
