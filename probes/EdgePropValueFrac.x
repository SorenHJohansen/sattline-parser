"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgePropValueFrac"
(*
open question: is `ValueFraction = 2` accepted? ValidGraphObjEnabl.x was rejected AT `ValueFraction`
   with `AliasSym Expected`, so this keyword may not exist in SattLine at all while our grammar has a
   dedicated value_fraction_tailed rule. Isolated here.
   Expected: unknown - this probe decides it. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Flag: boolean := True;
   Count: integer  := 5;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   TextObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
      ValueFraction = 2

ENDDEF (*BasePicture*);
