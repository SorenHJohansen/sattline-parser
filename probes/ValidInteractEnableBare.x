"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: ValidInteractEnableBare"
(* PROBE 2026-10-05 - QUESTION 1 ONLY: can an interact object's Enable_
   directive omit the tail entirely?

   The graph form is known legal with no tail (EdgePropEnable.x:
   "Enable_ = True" on a RectangleObject compiles). But the grammar treats
   interact differently:

       enable:           ENABLE_PREFIX "=" BOOL (invar | enable_expression)?
       enable_interact:  ENABLE_PREFIX "=" BOOL invar          <- tail MANDATORY

   No fixture in the corpus covers a bare interact Enable_, so that mandatory
   tail is an untested assumption. This file isolates exactly one line.

   What to record: PASS or the first error line + message. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   ToggleBit: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
InteractObjects :
   ComBut_ ( -0.8 , 0.6 ) ( 0.8 , 0.4 )
      Bool_Value
      Enable_ = True

ENDDEF (*BasePicture*);