"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: TypedExpressions"
(* Covers the expression forms the real parser was probed to accept.
   Probe 2026-10-01 confirmed acceptance of: boolean into boolean, integer into
   integer, integer into real, real into real, arithmetic on integers and
   reals, comparisons on integers and reals, and boolean IF conditions.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Count: integer  := 0;
   Rate: real  := 0.0;
   Flag1: boolean  := True;
   Flag2: boolean  := False;
   Output: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Count = Count + 1;
      Count = Count * 2;
      Rate = Count;
      Rate = Count * 1.5;
      Rate = Rate * 2.0;
      Output = Count == 1;
      Output = Count > 0;
      Output = Rate > 0.0;
      Output = Count == 1 AND Rate > 0.0;
      Output = NOT Flag1;
      IF Flag1 THEN
         Rate = 1.0;
      ELSIF NOT Flag2 THEN
         Rate = 2.0;
      ENDIF;

ENDDEF (*BasePicture*);
