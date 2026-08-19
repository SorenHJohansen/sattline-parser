"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: DeeplyNestedComments"
(* EDGE CASE: comments nest structurally, so depth is not capped by the
   lexer. Deeply nested comment runs inside a ModuleCode body must still
   parse and round-trip as a single CodeComment. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Value: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   (* level1 (* level2 (* level3 (* level4 (* level5 *) level4 *) level3 *) level2 *) level1 *)
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      (* a (* b (* c *) b *) a *)
      Value = Value + 1;

ENDDEF (*BasePicture*);
