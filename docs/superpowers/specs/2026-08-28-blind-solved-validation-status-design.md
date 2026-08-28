# Blind-solved validation status

## Goal

Separate two independent decisions:

- `validation.status` records whether a sample is correct and its review cycle is complete;
- `validation.blind_solved` records whether it is eligible for the primary video-dependent benchmark.

The status vocabulary remains `draft | validated | rejected`.

## Semantics

- `validated, blind_solved=false`: reviewed, correct, and eligible for the primary set.
- `validated, blind_solved=true`: reviewed and correct, but excluded from the primary set because it was solved without the video.
- `rejected`: incorrect, or deliberately abandoned before all required defects and reviews were completed. Blind solving alone is not a rejection reason.
- `draft`: review or repair is still active.

Consumers should derive datasets explicitly:

```python
primary_tasks = status == "validated" and not blind_solved
blind_baselines = status == "validated" and blind_solved
invalid_samples = status == "rejected"
```

## Validator and schema

In `tools/validate_samples.py`, remove only the rule that rejects
`validated + blind_solved=true`. Keep the remaining validated-sample requirements:

- `audio_dependency` is known;
- all five measurement flags are populated;
- `solvable=true`.

Rewrite nearby S-17, S-18 and S-25 comments so they do not describe `rejected` as the
carrier for otherwise valid blind-solved samples.

Keep the status enum in `schema/sample.schema.json`. Clarify descriptions so `validated`
means correctness and completed review, `rejected` means invalid or abandoned, and
`blind_solved` controls primary-set eligibility independently.

## Coordinator and proposer behavior

Update `docs/prompts/coordinator.md` and `docs/prompts/proposer.md` to express the new
orthogonal meanings.

A blind-solved candidate still completes the review DAG. The coordinator may try to make
it genuinely video-dependent, but blindness by itself never forces `rejected`. If the
unchanged or repaired sample is otherwise correct and its cycle completes, it may finish
as `validated + blind_solved=true`. Use `rejected` only when an independent defect remains
or the repair/review is deliberately abandoned.

Do not keep scheduling a terminal rejected sample merely to complete measurements. To
avoid prematurely terminating a potentially valid blind baseline, normally decide
`rejected` only after consolidation or an explicit human/coordinator decision to abandon
it. Reviewer-role prompts do not assign final status and need no change.

## Documentation and selection rules

Update every maintained normative description that currently equates blind solving with
rejection:

- `docs/annotation_pipeline.md`
- `docs/annotation_checklist.md`
- `data/annotations/README.md`
- `docs/plans/general.md`
- `docs/presentation/prolecture.tex`

These documents must use the three selection rules above. Blind-solved validated samples
may be used as a separate baseline or audit slice, but not as primary benchmark tasks.
Rejected samples contribute only to audit/rejection accounting unless a later workflow
explicitly repairs and rereviews them.

## Existing annotations and audit history

Do not migrate `q02`, `q02b`, `q03`, or `q08` in
`data/annotations/l6DKRf-fAAM.jsonl`. Their old cycles contain missing or unresolved
reviews, so they remain `rejected` even though `blind_solved=true`.

Clarify only their current annotation notes, where necessary, to name the independent
reason: incomplete review or unresolved defects. Do not rewrite historical
`data/reviews/**` records; they remain an audit trail of the policy used at the time.
The rejected q12 in `3d6DsjIBzJ4` is unaffected.

No existing annotation is eligible for automatic status migration under the approved
criterion: migrate an old `rejected + blind_solved=true` record only when its review cycle
is demonstrably complete and it has no independent rejection reason.

## Regression coverage

Add validator tests demonstrating that:

1. a complete `validated + blind_solved=true` sample passes;
2. a validated sample with missing modality measurements still fails;
3. a validated sample with `solvable=false` still fails;
4. all current annotation files pass repository validation after the change.

## Acceptance criteria

- The schema enum is unchanged.
- No normative maintained text says that `blind_solved=true` implies `rejected`.
- Primary-set selection always requires both `status == "validated"` and
  `blind_solved == false`.
- q02, q02b, q03 and q08 retain `status: rejected` with accurate current notes.
- Historical review artifacts are untouched.
- Validator regressions and the existing relevant test suite pass.
