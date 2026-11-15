"Syntax version 2.23, date: 2026-11-15-11:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-15-11:00:00.000, name: DottedMappingFieldMismatch"
(* SEMANTIC: A parameter mapping targets a record field, and the source has the
   wrong datatype for that field.
   ChildType declares a record parameter 'Settings'; its 'Flag' field is boolean.
   The caller maps the integer variable 'CounterValue' to that field.
   Expected: strict syntax-check fails with the parameter-transfer type mismatch. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   Settings = RECORD DateCode_ 1
      Flag: boolean  := False;
      Level: real     := 0.0;
   ENDDEF
    (*Settings*);

TYPEDEFINITIONS
   ChildType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      Settings: Settings;
   LOCALVARIABLES
      Flag: boolean  := False;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Flag = Settings.Flag;

   ENDDEF (*ChildType*);

LOCALVARIABLES
   CounterValue: integer  := 0;

SUBMODULES
   Child Invocation
      ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4
       ) : ChildType (
      Settings.Flag => CounterValue);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      CounterValue = CounterValue + 1;

ENDDEF (*BasePicture*);
