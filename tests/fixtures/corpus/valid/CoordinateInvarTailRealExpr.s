"Syntax version 2.23, date: 2026-06-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-06-19-12:00:00.000, name: CoordInvarTailReal"
(* Edge case: invariant/coord tail syntax — expression branch.
   Grammar rule: coord_invar_tail expression alternative.
   Corrected 2026-10-01: computed tails ARE legal in a corner, but the tail
   expression must be real-typed. With Source declared integer the real tool says
   "The expression is of an invalid type Source + 1"; declaring Source real makes
   the error disappear. Validation rule SL-V032.
   Expected: strict syntax-check passes - a real-typed tail is accepted. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Target: integer  := 0;
   Source: real  := 10.0;

ModuleDef
ClippingBounds = ( -1.0 : (Source + 1.0) , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Target = Source;

ENDDEF (*BasePicture*);
