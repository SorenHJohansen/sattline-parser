"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: SequenceBasic"
(* Covers the core SEQUENCE constructs:
   - SEQINITSTEP with ENTERCODE and EXITCODE
   - SEQSTEP with ENTERCODE, ACTIVECODE, EXITCODE
   - SEQTRANSITION WAIT_FOR with a boolean expression
   - SeqControl and SeqTimer optional control parameters
   Expected: strict syntax-check passes. *)

BasePicture #6?
   #01 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) #8= #71 #81 1

#7<
   StartCmd#8= boolean  #8; #1<;
   StopCmd#8= boolean  #8; #1<;
   Output#8= integer  #8; 0#7;;

#6>
#65 #8? #01 -1.0 , -1.0 ) #01 1.0 , 1.0 )
#84
   #22 MainSeq #01SeqControl, SeqTimer) #88 0.0, 0.0 #89 1.0, 1.0
      #26 Idle
         #28
            Output #8? 0#7;;
         #2:
            StartCmd #8? #1<;
      #30 TrStart #31 StartCmd
      #27 Running
         #28
            Output #8? 1#7;;
         #29
            Output #8? Output + 1#7;;
         #2:
            Output #8? 0#7;;
      #30 TrStop #31 StopCmd #15 Output #05 100
      #27 Stopping
         #28
            Output #8? -1#7;;
         #2:
            StopCmd #8? #1<;
      #30 TrDone #31 #16 StopCmd
   #23

#85 (*BasePicture*)#7;;
