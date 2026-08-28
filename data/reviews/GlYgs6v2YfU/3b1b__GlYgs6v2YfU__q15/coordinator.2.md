# Coordinator round 2 decision

## Reviewed

The round-1 semi-blind and modality probes, `full_sample.1.json`, `full_window0.1.json`, `semiblind.2.json`, `probe_text.2.json`, `probe_vision.2.json`, `probe_frame.2.json`, `full_sample.2.json`, and `full_window0.2.json`. Reviewer runs used GPT-5.6-Sol with medium reasoning.

## Decisions

The algebra-only draft was honestly blind-solved, but it was carried through full review and repaired instead of discarded. The accepted question adds the video-specific `p₂` green-to-red transition and still requires the algebra. Fresh semi-blind could derive generic algebra but not the index; the real transition is at `1973.0`, which is the accepted trigger and provenance time. Text alone lacks the index, vision solves the task, and one midpoint frame lacks the transition history. Full reviews pass the repair. Final flags: blind false, text false, vision true, frozen frame false. Status `validated`.
