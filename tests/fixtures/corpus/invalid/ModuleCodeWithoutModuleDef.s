"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: ModuleCodeWithoutModuleDef"
(* INVALID: a ModuleCode block must be part of a moduledef_block, which
   requires a leading ModuleDef. A bare ModuleCode in the module body is
   rejected. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Value = 1;

ENDDEF (*BasePicture*);
