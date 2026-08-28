# Coordinator decision — q13, review version 3

Validated after metadata-only onset and provenance repair.

- Cheap round 1 established `blind=false`, `text=false`, `vision=true`, `frame=false`, `solvable=true`, and `audio_dependency=unnecessary`; the participant-visible question never changed.
- Full rounds 1–2 exposed that the literal shaded-area/white-graph distinction begins near 890 rather than 905/893, and that provenance incorrectly said the earlier `a`/`x−a` notation appeared immediately before. The coordinator moved `t_start` to 890.2, aligned distractor/evidence, and corrected provenance.
- Fresh `semiblind.3.json` finds the integer-frame `t_val=891.0`, consistent with the subsecond 890.2 onset. Fresh `full_sample.3.json` and `full_window0.3.json` both return `PASS`.
- Final decision: `validation.status=validated`; all modality flags remain unchanged.
