"Syntax version 3.1, date: 2026-11-15-10:30:00.000 N"
"Original file date: 2026-11-15-08:00:00.000"
"Program date: 2026-11-15-10:30:00.000, Name: HeaderMetadata"
(* A header with every field written:
   - a syntax version that is not the editor default
   - an original file date instead of the unknown-date marker
   - a change description comment
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
