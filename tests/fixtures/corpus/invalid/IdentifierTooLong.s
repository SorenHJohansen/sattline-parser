"Syntax version 2.23, date: 2026-11-15-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-15-12:00:00.000, name: IdentifierTooLong"
(* The language caps a declared identifier at 20 characters. The source still
   parses, so the finding is SL-V038 at the declaration rather than a lexer
   error at the twenty-first character. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   AAAAAAAAAAAAAAAAAAAAA: integer  := 0;

SUBMODULES
   'AQuotedIdentifierBodyLongerThanTwenty' Invocation
      ( 0.2 , 0.2 , 0.0 , 0.4 , 0.4
       ) : MODULEDEFINITION DateCode_ 2
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*QuotedLong*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
