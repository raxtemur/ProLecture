# Coordinator decision — q13, review version 1

Cheap barrier passed after a metadata-only repair; full review pending.

- Read `semiblind.1.json`, `probe_text.1.json`, `probe_vision.1.json`, and `probe_frame.1.json` for the unchanged question.
- The blind prior lacked the displayed symbols, so `blind_solved=false`. Vision reproduced the requested triangle with base `x-a` and height from the local slope, while text and the frozen frame did not reproduce the required `a`/`x` mapping: `textonly_solved=false`, `visiononly_solved=true`, `frozenframe_solved=false`.
- Thus `solvable=true`, conditional `probe_full` is unnecessary, and `audio_dependency=unnecessary`.
- Semiblind found the first complete answer at `905.0`, earlier than the proposed `909.0`. Trigger and evidence start were moved to `905.0`, ideal to `906.0`, and provenance aligned to `905.0`; the question stayed unchanged. The current JSONL passes `tools/validate_samples.py`.
