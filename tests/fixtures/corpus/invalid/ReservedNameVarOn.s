"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: MinimalProgram"
(*
probe T1-012: reserved constant names (On/Off/GroupData) as variable identifiers Minimal valid SattLine program.
   No variables, no code, no submodules.
   Verifies that the parser and transformer accept the bare minimum structure.    Corrected 2026-10-02: rejected by the real tool with
   `>>>On<<<` / `>>>Off<<< AliasSym Expected` - at the declaration position the
   tool wanted an alias and found a reserved word. `On`/`Off` are readable
   wherever a boolean is expected (exempt from SL-V019) but may never be
   declared. Caught by validation rule SL-V034. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   On: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
