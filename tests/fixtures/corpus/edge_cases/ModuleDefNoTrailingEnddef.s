"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: ModuleDefNoTrailingEnddef"
(* EDGE CASE: the trailing module-level ENDDEF after a moduledef_block run is
   optional for base pictures and module invocations. Each ModuleDef block
   still terminates itself with its own ENDDEF, so nothing is left open. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF
