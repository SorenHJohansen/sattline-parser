"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: QuotedIdentifiers"
(* Covers quoted identifier syntax and extended-Latin identifiers.
   Quoted identifiers allow spaces and special characters in variable names.
   A declared identifier may have at most 20 characters; a longer spelling
   parses and reports SL-V038 rather than failing in the lexer.
   Keyword-prefixed identifiers (e.g. IFState, ANDFailed) are valid because
   keywords are only tokenized as standalone words.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   'Quoted Name': integer  := 0;
   'Max20CharName12345': integer  := 0;
   IFState: boolean  := False;
   ANDFailed: boolean  := False;
   NOTOGActive: boolean  := False;
   ThenValue: integer  := 0;
   ElseValue: integer  := 0;
   Sink: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      'Quoted Name' = 'Quoted Name' + 1;
      'Max20CharName12345' = 'Max20CharName12345' + 1;
      Sink = IF IFState THEN ThenValue ELSE ElseValue ENDIF;
      ANDFailed = NOT IFState AND NOTOGActive;

ENDDEF (*BasePicture*);
