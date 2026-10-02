"Syntax version 2.23, date: 2026-10-01-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-01-12:00:00.000, name: OpSaveStateReversed"
(*
tier 0 disambiguation: State before OpSave.
   EdgeOpSaveAndState.x used "OpSave State" and got an unreadable error.
   Modifier order is the other variable: if this is accepted, the tool cares
   about order, which would make the rule an ordering constraint rather than
   a forbidden combination.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Base: integer  := 0;
   Mirror: integer  OpSave := 0;
   Mixed: integer  State OpSave := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Base = Base + 1;
      Mirror = Mirror + 1;

ENDDEF (*BasePicture*);
