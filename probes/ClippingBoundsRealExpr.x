"Syntax version 2.23, date: 2026-10-01-13:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-01-13:00:00.000, name: ClipBoundsRealExpr"
(*
tier 0 disambiguation: is a ClippingBounds corner expression banned, or just
   required to be real?
   EdgeCoordInvarTail.x used an INTEGER-typed expression tail, (Source + 1)
   where Source is integer, and the real tool said "The expression is of an
   invalid type Source + 1". That message is a TYPE error, not a syntax error,
   so it does not show that expressions are banned in corners.
   This probe is byte-identical except that the tail expression is REAL-typed.
   If this is accepted, the rule is a type rule (integer rejected, real fine).
   If it is rejected the same way, expressions are banned outright and the
   corner must be a plain literal pair. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Target: integer  := 0;
   Source: real  := 10.0;

ModuleDef
ClippingBounds = ( -1.0 : (Source + 1.0) , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Target = 1;

ENDDEF (*BasePicture*);
