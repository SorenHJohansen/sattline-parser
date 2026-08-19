"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: GraphObjectEnableTails"
(* Covers the enable_expression form of every tailed graphic attribute:
   ValueFraction, Width_, Format_String_, Colour0, Colour1, ColourStyle.
   Each tail is "name = value : (expression)" and must parse without
   ambiguity against the tailed rule.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   DisplayValue: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   TextObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
      "DisplayValue" ValueFraction = 2 : (DisplayValue > 0)
      Width_ = 4 : (DisplayValue > 0)
      Format_String_ = "%d" : (DisplayValue > 0)
      OutlineColour : Colour0 = 2 : (DisplayValue > 0)
         Colour1 = 3 : (DisplayValue > 0)
         ColourStyle = 2.0 : (DisplayValue > 0)

ENDDEF (*BasePicture*);
