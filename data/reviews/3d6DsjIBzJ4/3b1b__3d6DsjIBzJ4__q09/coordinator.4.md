# Coordinator decision — q09, review version 4

Final decision: **validated**.

- full_sample.1 found a second literal shifted-basis event in the later `ln(x)`-around-1 scene. The participant-visible question was rewritten to require the **first** basis shift after the question, invalidating all earlier acceptance evidence.
- Fresh round 3 cheap evidence gives `blind_solved=false`, `textonly_solved=true`, `visiononly_solved=true`, and `frozenframe_solved=true`; therefore `solvable=true` and `audio_dependency=unnecessary`.
- full_sample.3 returned PASS and confirmed that the first-occurrence qualifier selects the `cos(x)`-around-`π` event while excluding the later logarithm scene.
- full_window0.3 found a metadata-only boundary defect: the shifted `P_π(x)` basis is already faint but legible at `601.0`, while the proposed window began at `602.0`. The trigger start, distractor end, and evidence-span start were moved to `601.0`; the participant-visible question did not change.
- Targeted semiblind.4 found `t_val=601.0` and confirmed `[592.5,601.0)` is a clean distractor: the marked point and blue curve are visible by `600.0`, but the shifted formula is absent.
- Targeted full_sample.4 independently inspected the disputed dense frames, confirmed no formula at `600.0` and legible `P_π(x)` / `(x−π)` terms at `601.0`, and returned PASS. The stable provenance frame remains `602.0`, which visibly contains the complete formula, target, and center.
- Targeted full_window0.4 returned PASS for `[601.0,623.8)`, confirmed `evidence_span=[601.0,613.9]`, found no finished L3 coefficient/quadratic answer through `t_end+10`, and confirmed that `depends_on` is correctly absent.
- full_window0.4 viewed 36 frames, above the prompt's approximate 25-frame guideline, to check the complete leakage tail. This is a cost overrun but not a source-contamination issue; all frames were inside the permitted workspace interval and the reviewer disclosed the count.
