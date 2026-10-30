"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: InteractEnableTails"
(* Covers the invar tail on interaction body lines, for both the assignment
   and the enable directive:
   - "Variable = value : (expression)" assignment with an expression tail
   - "Variable = value : InVar_ \"name\"" assignment with an invar tail
   - "Enable_ = True : InVar_ \"name\"" enable with an invar tail
   All use plain NAME flags; no TextObject interaction flags here.
   Expected: strict syntax-check passes.

   Probe 2026-10-01: the enable directive does NOT take an expression tail.
   ValidInteractEnabl.x used "Enable_ = True : (EnableFlag)" and the real parser
   reported "AliasSym Expected" at the Enable_ line -- after the colon it wants
   a directive name, not a parenthesised expression. Note the assignment
   directive on the line above accepts "(InputValue > 0)" just fine, so the
   restriction is specific to Enable_. The rejected form is preserved as
   invalid/EnableExpressionTail.s. *)

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

   ComBut_ ( -0.8 , 0.6 ) ( 0.8 , 0.4 )
      Bool_Value
      Variable = False : InVar_ "EnableFlag"
      Enable_ = True : InVar_ "ToggleBit"

ENDDEF (*BasePicture*);
