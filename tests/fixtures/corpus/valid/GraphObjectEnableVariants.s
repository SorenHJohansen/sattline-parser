"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: GraphObjectEnableVariants"
(* Covers the two legal forms of Enable_ on a GRAPH object.

   Both were proved 2026-10-05 by the batch run:
      EdgePropEnable.x     Enable_ = True            -> compiles (tail omitted)
      EdgePropParenTail.x  Enable_ = True : (Flag)   -> compiles (paren tail)

   The first matters because the interact spelling is stricter: `enable_interact`
   requires an invar tail, while `enable` (graph) allows the tail to be omitted
   or to be a parenthesised expression. The rejected interact counterpart is
   invalid/EnableExpressionTail.s.

   Expected: strict syntax-check passes.
   Expected: zero validation diagnostics. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Flag: boolean := True;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   RectangleObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
      Enable_ = True

   OvalObject ( -0.8 , -0.1 ) ( 0.8 , -0.7 )
      Enable_ = True : (Flag)

ENDDEF (*BasePicture*);