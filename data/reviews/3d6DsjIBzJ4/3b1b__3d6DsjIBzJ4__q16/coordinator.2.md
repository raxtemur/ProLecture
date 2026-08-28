# Coordinator decision — q16, review version 2

Validated after metadata-only repair and fresh affected-role review.

- Cheap round 1 established `blind=false`, `text=false`, `vision=true`, `frame=false`, `solvable=true`, and `audio_dependency=unnecessary`; the participant-visible question never changed.
- `full_sample.1.json` found that the response/rubric appended an undisplayed `=1/24`; `full_window0.1.json` found author-answer leakage only because the direct on-screen alarm was mislabeled L2.
- Removed the undisplayed equality and corrected `reasoning_level` to L1. These metadata changes do not affect the cheap modality evidence.
- Fresh `full_sample.2.json` and `full_window0.2.json` both return `PASS`, confirming the first crossing at 1114.0, displayed term `1⁴/4!`, subtotal `2.7083333`, provenance, and L1 treatment.
- Final decision: `validation.status=validated`; all modality flags remain unchanged.
