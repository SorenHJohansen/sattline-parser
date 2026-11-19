"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: SetIoAttributeConstArgument"
(* Edge case: a Const variable passed to SetIoAttribute's Variable parameter.
   The call addresses an I/O object and writes the supplied value into it, so
   the argument is a value written into the object, not a caller variable the
   callee assigns. The Const-write rule is exempt for this parameter only. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Fixed: integer Const := 1120;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ModuleCode
EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
   SetIoAttribute(4, 0, 0, 0, 1120, Fixed);
ENDDEF (*BasePicture*);
