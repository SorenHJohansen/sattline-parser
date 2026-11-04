"Syntax version 2.23, date: 2026-11-04-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-04-12:00:00.000, name: AnnotationTailUndefined"
(* Covers variable uses in header, graphics, and interact annotation tails.
   The header coordinate tail, the graph-object Enable_ tail, the colour tail,
   and the interact assignment tail all name variables that are not declared.
   Expected: strict syntax-check passes; strict validation fails with SL-V019
   for each unresolved expression tail. *)

BasePicture Invocation
   ( 0.0 : (HeaderCoord) , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Flag: boolean := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   TextObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 )
      "Label"
      OutlineColour : Colour0 = 1 : (MissingColour)
   RectangleObject ( 0.0 , 0.0 ) ( 1.0 , 1.0 )
      Enable_ = True : (MissingEnable)
InteractObjects :
   TextBox_ ( 0.0 , 0.0 ) ( 1.0 , 1.0 )
      Int_Value
      Value = 0 : (MissingAssign)

ENDDEF (*BasePicture*);
