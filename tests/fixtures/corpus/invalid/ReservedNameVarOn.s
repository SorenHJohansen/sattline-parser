"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: MinimalProgram"
(*
probe T1-012: reserved constant names (On/Off/GroupData) as variable identifiers.
   `On`/`Off` are boolean literals and may never be declared. The parser
   rejects this at the declaration position, matching the real tool's
   `AliasSym Expected`; SL-V034 remains a validator backstop for constructed
   ASTs. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   On: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
