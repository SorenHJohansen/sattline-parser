"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: ModuleDefTrailingEnddefSemicolon"
(*
tier 0 sweep: valid/ModuleDefTrailingEnddefSemicolon.s POSITIVE CONTROL for
   EdgeModDefNoTrail.x: the same base picture, but the trailing module-level
   ENDDEF is terminated with `;`.

   Why this probe exists: the real tool rejected the unterminated form with
   "Error on line 15: >>><<< SemicolonSym Expected". That establishes the `;` is
   required *when ENDDEF is present*, but it does not by itself prove the
   terminated form is accepted - that reading is [inferred], not [corpus].
   One GUI run closes the gap:
     - accept  -> the rule is "ENDDEF optional, its semicolon mandatory",
                  which is what the grammar now encodes;
     - reject  -> the trailing ENDDEF itself is illegal on a base picture, and
                  the grammar should drop the clause entirely rather than
                  tighten it.

   Run this alone, in its own session. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF;
