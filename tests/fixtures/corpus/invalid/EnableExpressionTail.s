"Syntax version 2.23, date: 2026-10-01-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-01-12:00:00.000, name: EnableExpressionTail"
(* INVALID: the Enable_ directive is given a parenthesised expression tail.
   Probe ValidInteractEnabl.x (2026-10-01) used this exact line and the real
   parser reported:
     >>>Enable_<<< = True: AliasSym Expected
   After the colon the real parser wants a directive name, so only the invar
   form is legal: "Enable_ = True : InVar_ \"ToggleBit\"".

   The restriction is specific to Enable_. The assignment directive in the same
   object, "Variable = 0 : (InputValue > 0)", is accepted by the real parser and
   is kept in valid/InteractEnableTails.s.
   Expected: strict parse fails -- the enable_expression tail is not in the
   grammar for `enable`. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   EnableFlag: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
InteractObjects :
   TextBox_ ( -0.8 , 0.9 ) ( 0.8 , 0.7 )
      Int_Value
      Enable_ = True : (EnableFlag)

ENDDEF (*BasePicture*);
