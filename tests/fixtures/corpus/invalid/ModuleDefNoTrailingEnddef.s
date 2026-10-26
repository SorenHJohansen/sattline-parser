"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: ModuleDefNoTrailingEnddef"
(* EDGE CASE: the trailing module-level ENDDEF after a moduledef_block run is
   optional for base pictures and module invocations. Each ModuleDef block
   still terminates itself with its own ENDDEF, so nothing is left open.
   Corrected 2026-10-02: rejected by the real tool - `Error on line 15: >>><<<
   SemicolonSym Expected`. A trailing module-level ENDDEF, when present, must be
   terminated with `;`. Grammar change: base_picture_module's `(ENDDEF_KW ... ";"?)?`
   became `(ENDDEF_KW ... ";")?`, so the ENDDEF stays optional but its `;` does not.
   Scoped deliberately: RECORD ENDDEFs (`record` rule) and ScanGroup ENDDEFs keep
   their optional `;`, which UnCompressedFullGrammar.s relies on and which the real
   tool compiles cleanly. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF
