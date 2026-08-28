# Coordinator decision — q14, review version 1

Cheap barrier passed after pointwise clarification; full review pending.

- Consolidated `semiblind.1.json`, `probe_text.1.json`, `probe_vision.1.json`, and `probe_frame.1.json` for the unchanged question.
- The blind prior cannot know the presentation-specific color mapping. Text recovers the three terms but not their colors; vision and the single frame recover all mappings. Thus `blind_solved=false`, `textonly_solved=false`, `visiononly_solved=true`, `frozenframe_solved=true`, and `solvable=true`.
- Hence `audio_dependency=unnecessary`; no `probe_full` is needed. Frozen-frame success is normal for L1.
- Semiblind initially reported 1021 because a failed subsecond extraction reused whole-second filenames. A same-run pointwise rebuild established that the complete equation and all pieces are already visible at 1020, agreeing with the independent visual probe. No interval edit was required. The current JSONL passes the validator.
