# AGENTS.md

## If you are a reviewer or a probe of the annotation pipeline

This applies to the roles `reviewer_semiblind`, `reviewer_full_sample`,
`reviewer_full_window` and every `probe_*`. Neither this file nor `CLAUDE.md` is
written for you. Your prompt in `docs/prompts/<role>.md` is binding and names
everything you may read: the prompt itself, your workspace and `schema/review.py`.
Do not open `CLAUDE.md`, `docs/annotation_checklist.md`,
`docs/annotation_pipeline.md`, `docs/plans/general.md`,
`docs/prompts/definitions.md`, other roles' prompts or the proposer's material
(`docs/question_templates.md`, `docs/sample_examples.jsonl`). They hold the
rules of other roles, and reading them changes what you measure. The interpreter is
`/home/user/conda/bin/python3`. Skip the rest of this file except the last
paragraph, on compaction.

## Repo context
`CLAUDE.md` is written for agents that work on the project itself: its code,
schemas, documentation and the pipeline. It holds the repository layout, the two
Python environments (always name the interpreter explicitly) and the pipeline
docs. Read it before you edit any of these.

## Role prompts (annotation pipeline)
Roles of the pipeline, one prompt each in `docs/prompts/`:

- `proposer` — step 1: bundle -> candidate questions;
- `reviewer_full_sample`, `reviewer_full_window`, `reviewer_semiblind` — step 3:
  whole-sample review, per-window review, semi-blind (blind) review;
- `probe_frame`, `probe_full`, `probe_text`, `probe_vision`, `probe_verify` —
  step 3: probes measuring answer availability and left boundaries;
- `coordinator` — steps 4-6: applies fixes, derives flags, decides sample fate.

When acting as a pipeline agent, the prompt in `docs/prompts/<role>.md` is
binding for that role. After any session compaction, re-read the full current
role prompt before doing any annotation work. A compaction may look like
receiving a "HANDOFF SUMMARY" in the last message.
