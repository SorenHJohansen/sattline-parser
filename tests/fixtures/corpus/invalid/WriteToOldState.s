"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-26-12:00:00.000, name: WriteToOldState"
(* INVALID: assigning to the Old state of a State variable.

   :Old is a read state. An :Old assignment target is rejected with
   expression-node error 0x14, and the same check applies to reference-required
   call arguments. This is a compile-time check, not an editor guard, and the
   syntax itself stays legal so that reads such as
   `Seen = Counter:Old;` keep working.

   Ours reports SL-V035 OLD_STATE_NOT_WRITABLE. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Counter: integer State := 0;
   Mirror: integer := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Mirror = Counter:Old;
      Counter:Old = Mirror;

ENDDEF (*BasePicture*);
