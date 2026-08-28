# Coordinator decision — q01, review version 4

Final decision: **validated**.

- blind_solved=false: the round-4 prior answer required assumptions about the unseen pendulum expression; it did not satisfy the rubric honestly from the question alone.
- textonly_solved=false, visiononly_solved=true, frozenframe_solved=true; therefore solvable=true and audio_dependency=unnecessary.
- full_sample.1 found that distractor 0 covered a valid display and that the complete pendulum construction recurs in the recap near 498 s.
- Trigger 0 was corrected to [51.0, 79.8), ideal 52.0, with evidence_span=[51.0, 68.9]; semiblind.4 found t_val=51.0 and full_window0.2 returned PASS.
- The recap was added as optional trigger 1 [498.0, 507.0), ideal 499.0, with evidence_span=[498.0, 500.0]; semiblind.3 found t_val=498.0 and full_window1.2 returned PASS.
- semiblind.2 is audit history only: its stretch began at 79.8 s while the first pendulum sequence was still answer-bearing, so its t_val=80.0 was not evidence about trigger 1.
- The participant-visible question never changed, so targeted metadata re-review is sufficient under coordinator.md.
