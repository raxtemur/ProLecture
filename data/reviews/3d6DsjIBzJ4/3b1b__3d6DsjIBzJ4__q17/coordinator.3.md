# Coordinator decision — q17, review version 3

Validated after metadata-only trigger and provenance repair.

- Cheap round 1 established `blind=false`, `text=false`, `vision=true`, `frame=true`, `solvable=true`, and `audio_dependency=unnecessary`; the participant-visible question never changed.
- Full rounds 1–2 showed the original 1204 pass used the wrong in-boundary probe, located the literal beyond-right firing at 1217, and found that a one-frame provenance record overclaimed four successive states. The coordinator aligned trigger/distractor/evidence to 1217 and split provenance across four real frames.
- Fresh `semiblind.3.json` confirms `t_val=1217.0` and the ordered relations. Fresh `full_sample.3.json` and `full_window0.3.json` both return `PASS`.
- Final decision: `validation.status=validated`; all modality flags remain unchanged.
