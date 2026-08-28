# Coordinator decision — q08, review version 5

Final decision: **validated**.

- The original question was rewritten after full review found that the author's own explanation supplied the old answer; all pre-rewrite reviews are audit history.
- Fresh participant-visible round 3 asks for the screen color plus a counterfactual evaluation at `x=1`. semiblind could derive the algebra but could not identify the unseen color, so `blind_solved=false`.
- Fresh cheap evidence gives `textonly_solved=false`, `visiononly_solved=true`, `frozenframe_solved=true`; therefore `solvable=true` and `audio_dependency=unnecessary`.
- Boundary reviewers differed by one second during the fade. The coordinator conservatively retained trigger start `572.0`, ended the distractor there, and kept ideal `573.0`; semiblind.4 confirmed the repaired distractor is clean.
- full_sample.3 correctly reclassified the task from L2 to L3. full_sample.4 verified the repaired L3 design and mathematics; its sole substantive finding was that the cited frames preceded the exact displayed facts. Provenance and `evidence_span` were moved to stable frames `478.3` and `574.0` without changing the participant-visible question.
- full_sample.4 disclosed that an initial metadata search exposed the handed q08 annotation and prior-review filenames, but no prior findings or verdicts. The review remains usable because the annotation was identical to the supplied sample and the substantive provenance observation was independently checked by the targeted window review.
- full_window0.5 returned PASS after the metadata repair: `[572.0,590.5)` is usable, `[478.3,574.0]` reaches the last required evidence, `depends_on` is correctly absent, and no finished composite L3 answer appears through `t_end+10`.
- Because the last changes affected only reasoning metadata and evidence/provenance—not the participant-visible question—the targeted re-reviews are sufficient under coordinator.md.
