"Syntax version 2.23, date: 2026-11-04-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-04-12:00:00.000, name: EnableTailNotBoolean"
(* Covers the condition type of a parenthesised Enable_ tail.
   The grammar rule `enable` requires a BOOL before the optional tail, so the
   tail is the condition the directive evaluates. A tail that resolves to an
   integer is therefore not a boolean condition.
   Expected: strict syntax-check passes; strict validation fails with SL-V030.
   The valid counterpart is GraphObjectEnableVariants.s, where the same form
   uses a boolean variable. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Count: integer := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 )
      Enable_ = True : (Count + 1)

ENDDEF (*BasePicture*);
