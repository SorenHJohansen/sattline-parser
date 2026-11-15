"Syntax version 2.23, date: 2026-11-15-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-15-12:00:00.000, name: UndefinedMappingSource"
(* SEMANTIC: A parameter mapping names a source variable that is not declared.
   The target type is declared in this file, so its formals are known.
   Expected: strict syntax-check fails with an undefined-variable finding at
   the mapping. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   ChildType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      EnableFlag: boolean  := False;
   LOCALVARIABLES
      Active: boolean  := False;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Active = EnableFlag;

   ENDDEF (*ChildType*);

SUBMODULES
   Child Invocation
      ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4
       ) : ChildType (
      EnableFlag => NoSuchVariable);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
