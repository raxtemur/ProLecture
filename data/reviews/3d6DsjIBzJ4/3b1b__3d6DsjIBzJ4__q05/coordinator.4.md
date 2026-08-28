# Coordinator decision — q05, review version 4

Final decision: **validated**.

- Cheap review established solvable=true, blind_solved=false, textonly_solved=false, visiononly_solved=true, frozenframe_solved=true, so audio_dependency=unnecessary.
- Boundary judgments differed during the value fade-in. semiblind.2/.3 and full_window0.1 found both numbers reliably readable at 334.0, while full_sample.1/.2 judged the true-value row potentially readable at 333.0.
- To avoid placing a potentially answerable frame in a distractor, the coordinator chose the conservative trigger start 333.0 with ideal 334.0 and ended the distractor at 333.0.
- Targeted semiblind.4 confirmed the repaired distractor is clean and returned t_val=334.0. full_window0.2 returned PASS, treating the one-second fade slack as permissible and confirming no finished L3 answer appears through t_end+10.
- Earlier FIX_INTERVALS reviews are retained as audit evidence for the incorporated repair.
