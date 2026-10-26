"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: ModuleDefTrailingEnddefSemicolon"
(* Positive control for ModuleDefNoTrailingEnddef: the same base picture with the
   trailing ENDDEF correctly terminated by `;`.
   NOTE: tool acceptance of this form is [inferred] from the diagnostic text
   ("SemicolonSym Expected") and has NOT been confirmed by a real run yet. The
   probe probes/EdgeModDefTrail.x exists to settle it. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF;
