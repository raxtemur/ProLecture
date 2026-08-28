# Coordinator decision — q10, review version 2

Cheap barrier passed after metadata-only repair; full review pending.

- Consolidated `semiblind.1.json`, `semiblind.2.json`, `probe_text.1.json`, `probe_vision.1.json`, and `probe_frame.1.json`; the participant-visible question is unchanged.
- The blind prior lacked the derivative values, so `blind_solved=false`. Text and vision reproduce the four mappings; the frozen frame gives a different guessed pattern and is insufficient. Thus `textonly_solved=true`, `visiononly_solved=true`, `frozenframe_solved=false`, and `solvable=true`; `probe_full` is unnecessary.
- From vision=true and solvable=true, `audio_dependency=unnecessary`.
- Round 1 located the answer near 745 s. Fresh round 2 established that 745 is transitional and `t_val=746.0`; trigger/evidence/distractor/provenance were aligned to 746.0 without changing the question. The current JSONL passes `tools/validate_samples.py`.
