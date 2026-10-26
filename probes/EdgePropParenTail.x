"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgePropParenTail"
(*
open question: the parenthesised enable tail `: ( expr )`, our enable_expression.

REWRITTEN 2026-10-05. The previous version attached the tail to `Width_ = 4 : (Flag)`, but the
batch proved `Width_` is not a legal graph-object property at all (EdgePropWidth.x -> the tool
asks for a StringSym), so the tool died on the keyword and never reached the tail. The verdict
was therefore mis-targeted.

It now hangs the tail off a BARE `Enable_ = True`, which EdgePropEnable.x proved is legal on a
RectangleObject. That isolates exactly one unknown: whether the parenthesised tail is accepted
after it.

This matters more than a normal edge case. SattLine's own compressor emits
`Enable_ = True : ( NOT EnableVar)`, so if this tail is legal then SattLine's own output
contains a construct we currently reject - and our own parser rejects the bare-tail form too,
so this is a candidate we-too-strict bug rather than a dead rule.

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
   RectangleObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
      Enable_ = True : (Flag)

ENDDEF (*BasePicture*);