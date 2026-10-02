"Syntax version 2.23, date: 2026-10-01-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-01-12:00:00.000, name: OpSaveConst"
(*
tier 0 disambiguation: OpSave combined with Const.
   EdgeOpSaveAndState.x showed that OpSave + State makes the real tool emit
   "Unknown error - unable to read error message file", so it rejects the
   combination but cannot say why. This probe asks whether that is specific
   to State or general to any second modifier. If this is accepted, the
   problem is OpSave+State alone; if it fails the same way, it is a general
   multi-modifier defect in the tool.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Base: integer  := 0;
   Mirror: integer  OpSave := 0;
   Mixed: integer  OpSave Const := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Base = Base + 1;
      Mirror = Mirror + 1;

ENDDEF (*BasePicture*);
