"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: InteractEnableTails"
(* Covers the enable_expression and invar tails on interaction body lines:
   - "Variable = value : (expression)" assignment with an expression tail
   - "Enable_ = True : (expression)" enable with an expression tail
   - "Variable = value : InVar_ \"name\"" assignment with an invar tail
   All use plain NAME flags; no TextObject interaction flags here.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   InputValue: integer  := 0;
   EnableFlag: boolean  := False;
   ToggleBit: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
InteractObjects :
   TextBox_ ( -0.8 , 0.9 ) ( 0.8 , 0.7 )
      Int_Value
      Variable = 0 : (InputValue > 0)
      Enable_ = True : (EnableFlag)

   ComBut_ ( -0.8 , 0.6 ) ( 0.8 , 0.4 )
      Bool_Value
      Variable = False : InVar_ "EnableFlag"
      Enable_ = True : InVar_ "ToggleBit"

ENDDEF (*BasePicture*);
