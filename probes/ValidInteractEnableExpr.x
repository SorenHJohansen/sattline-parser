"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: ValidInteractEnableExpr"
(* PROBE 2026-10-05 - QUESTION 2 ONLY: may an interact object's Enable_
   directive take a parenthesised expression tail?

   This is the ValidInteractEnabl.x contradiction. The records disagree:
     - TRANSCRIPT.md `real` cell          -> accept
     - TRANSCRIPT.md its own note         -> "Error on line 27: >>>Enable_<<<
                                              = True: AliasSym Expected"
     - invalid/EnableExpressionTail.s     -> rejects (probe 2026-10-01)
     - valid/InteractEnableTails.s header -> "the enable directive does NOT
                                              take an expression tail"
   The same file also carries "Variable = 0 : (InputValue > 0)" on the line
   above, which the tool DOES accept, so the restriction must be specific to
   Enable_.

   Our parser rejects this line today (enable_interact only allows `invar`).
   If the tool ACCEPTS it, we are the only too-strict row left and the grammar
   must gain the expression tail for interact enable.

   Note ValidInteractEnabl.x is NOT isolated - it bundles this line with a
   ComBut_ and an assignment. This file has one widget and one line.

   What to record: PASS or the first error line + message. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   EnableFlag: boolean  := False;
   InputValue: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
InteractObjects :
   TextBox_ ( -0.8 , 0.9 ) ( 0.8 , 0.7 )
      Int_Value
      Variable = 0 : (InputValue > 0)
      Enable_ = True : (EnableFlag)

ENDDEF (*BasePicture*);