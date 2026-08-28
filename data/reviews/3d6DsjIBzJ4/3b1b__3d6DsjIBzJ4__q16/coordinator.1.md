# Coordinator decision — q16, review version 1

Cheap barrier passed; full review pending.

- Consolidated `semiblind.1.json`, `probe_text.1.json`, `probe_vision.1.json`, and `probe_frame.1.json`.
- The blind prior cannot know the exact displayed subtotal. Text supplies only a general-knowledge calculation without screen formatting, and the frozen frame shows the later `2.7166667` update; neither is credited. Vision tracks the sequence and gives `1^4/4!`, `2.7083333`.
- Therefore `blind_solved=false`, `textonly_solved=false`, `visiononly_solved=true`, `frozenframe_solved=false`, `solvable=true`, and `audio_dependency=unnecessary`; no `probe_full` is needed.
- Semiblind confirms `t_val=1114.0` at the proposed start. No metadata repair was needed; the current JSONL passes the validator.
