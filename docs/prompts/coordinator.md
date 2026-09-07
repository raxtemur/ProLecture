# Prompt: the coordinator. Acceptance methodology

The coordinator's prompt to itself. The role is steps 4–6 of the pipeline
[../annotation_pipeline.md](../annotation_pipeline.md): apply the fixes on top of the
subagents' reviews, derive the flags, decide the fate of the sample.

**Only the non-obvious is written here.** Anything that already follows from the
checklist, the contract or common sense is not repeated. Every item is a decision arrived
at by agreement, usually after the opposite behaviour has already done damage once. Each
one records **why**: without that, two rounds later the rule looks arbitrary and gets
repealed all over again.

This is not a replacement for [annotation_checklist.md](../annotation_checklist.md) (what
is checked) and not a replacement for
[annotation_pipeline.md](../annotation_pipeline.md) (in what order and by whose hands).
It is a third thing: **how to judge** where somebody else's structured answer has to be
turned into a decision.

---

## 1. Blind solving: a guessed statement of the problem does not count

**The rule.** The semi-blind reviewer's answer, obtained before viewing, counts as
compromising the sample (`validation.blind_solved = true`) only if it satisfies **both**
conditions:

- **correct** — it agrees with the rubric;
- **honest** — it follows from the available context and prior knowledge, without
  assumptions about unseen screen content.

Recalling a known historical or textbook fact counts as blind solving. Predicting which
values, example, layout or other content will appear on screen does not, even when the
prediction is exactly right. A non-empty `prior_answer_assumptions` is strong evidence of
such guessing: if different screen content would make the answer wrong, the task was not
solved blind.

**Why.** Blind solving measures whether the answer is available without the video, not
whether a reviewer can luckily reconstruct unseen screen content from a familiar genre.

**A hedged answer** ("2.5, and if otherwise then 2.0") counts only when the wrong branch
would have cost the participant a point. Otherwise it is enough to list the plausible
options to declare anything at all solved blind.

**A caveat about notation, colour or verbatim wording is not an assumption about content**
(rule of 2026-09-07; the boundary between "guessed the concrete data", "recalled the data
as a known fact" and "could not guess a colour or another when-condition unrelated to the
science" is still under discussion). Two answers that
look alike are scored differently:

- "2.5, if the screen shows the standard example 1/2, 1/4, 1/8, 1/8" — the correctness
  depends on an assumption about the screen: a guess, `prior_answer_assumptions` non-empty,
  `blind_solved = false`. The rule above, unchanged.
- "pᵢ f′(qᵢ) = λ → q f′(q) = λ → f = λ log q; which notation and colours the screen uses
  I cannot say" — the correctness of the chain does not depend on the screen. Score
  `prior_answer` against the rubric **item by item, ignoring the caveat**: substantive
  items (a quantity, a relation, a derivation) the reviewer named are met; items about the
  screen itself (a colour, a notation, a displayed number) that the reviewer did not name
  are not. **Only the substantive items decide `blind_solved`.** If all of them are met,
  the sample is solved blind, and a rubric item about a colour does not rescue it: such a
  sample tests colour recognition, not the science, and is not the `L1` alarm the benchmark
  wants — it is repaired or kept as a blind baseline like any other. Name in
  `coordinator.N.md` which items were met blind, so that it is visible what the sample
  rests on.

The reviewer is asked for content, not a meta-statement about it ("known only the general
Lagrangian derivation" scores nothing; the derivation itself does). A `prior_answer` that
is a sentence *about* the reviewer's knowledge is sent back for the content before it is
scored — that is a follow-up to the same subagent, not a new round. A strong reviewer is an
upper bound on blind solvability, and that strictness is deliberate.

**A blind-solved sample is carried to the end of the cycle.** Keep the contamination flag
on the version that was measured, run `full_sample` and every `full_window`, and try to
repair it by making the answer depend on a screen-specific value, relation, transition or
counterfactual. Changing only *when* to repeat the same known fact is not a repair.

After a substantive rewrite, set the sample back to `draft` and follow the question-version
rule in section 3: rerun the complete review cycle on the rewritten wording. Only the new
reviews can clear `blind_solved`. If the completed cycle finds the sample otherwise correct,
it may finish as `status: validated` with `blind_solved: true`; keep it out of the primary
benchmark and retain it as a blind baseline. Use `rejected` only for an independent defect or
when repair/review is deliberately abandoned, and record that reason.

**A consequence for the wording.** A question whose condition is named in full in the
question itself and which requires the model to retrieve a known fact from memory is
neither `L3` nor `predict`: it is an `L1` alarm, "recall something known and say it at the
right moment", however hard the topic may sound.

---

## 2. The verdict on 4.2 is set by the coordinator, not the reviewer

The `solvable-without-video` line in the semi-blind reviewer's review is **preliminary**.
They compare their answer not against the rubric but against their own impression of the
material: they have no reference answer and must not have one. So their `result` is read
as a self-report, and `validation.blind_solved` is derived by the coordinator under rule
1.

The same holds in reverse: an `ok` from the semi-blind reviewer does not mean the sample
is clean. They may have failed to recall a fact another model will recall.

---

## 3. The order of the roles: five cheap ones first, then full review for every candidate

Use a **work-conserving, cheap-first scheduler** across questions. Whenever a slot is free,
give priority to a runnable `semiblind`, `probe_text`, `probe_vision` or `probe_frame` job.
These four roles are independent and should run in parallel. There is no global stage
barrier: one question may advance as soon as its own prerequisites are satisfied while
cheap work for other questions continues to fill the remaining slots.

Normally, do not repair a question from the first cheap result while its other cheap
reviewers are still running. Collect all four results for the same question version,
consolidate their findings together, resolve disagreements once, and apply one coherent
set of cheap fixes. This avoids serial boundary changes and repeated semiblind cycles.

Before launching `full_sample` or any `full_window`, the question must pass this barrier:

- all four initial cheap reviews refer to the exact current `question` version;
- the coordinator has consolidated all four results;
- `blind_solved`, `textonly_solved`, `visiononly_solved`, `frozenframe_solved`,
  `solvable` and `audio_dependency` have been derived;
- conditional `probe_full`, if required, has finished;
- cheap fixes have been applied, and every cheap role affected by a metadata-only fix has
  been rerun;
- the current JSONL passes `tools/validate_samples.py`.

Only then is that question eligible for the expensive queue. Runnable cheap jobs retain
priority over full reviews. Once scheduled, run `full_sample` and one `full_window` per
trigger independently; both are required for every non-terminal candidate, including one
marked `blind_solved`. Do not schedule a sample already terminally `rejected` merely to fill
missing measurements: rejection means an independent defect remains or the work was
deliberately abandoned.

**Why.** Full reviewers are the most expensive in frames and context. The barrier keeps
them from judging wording or boundaries that a cheap result is about to invalidate. They
still run for every candidate because they inspect rubric alignment, trigger completeness
and shape, provenance and window semantics needed either for acceptance or repair — and
because `full_sample` supplies the stage-B proposal `t_s` (section 6).

**`probe_full` is conditional.** Launch it exactly when `probe_text` and `probe_vision`
both answered incorrectly; a positive answer from either already proves solvability.

**A changed participant-visible question creates a new review version.** Set
`validation.status` back to `draft`; retain old reviews as audit history, but do not use
their verdicts or modality flags for the new wording. Return the question to the start of
the cheap queue and pass the barrier again before launching fresh `full_sample` and every
`full_window` with new iteration numbers and separate workspaces.

If the participant-visible `question` is unchanged, an interval, provenance, rubric or
other metadata-only repair needs only the roles whose owned checks or expected answer may
have changed. Consolidate all relevant findings before applying the repair, then rerun
those affected roles; unaffected evidence may remain.

**A follow-up is part of the same reviewer run.** It may ask an existing subagent to
clarify or complete its current finding before a proposed edit is accepted, but it retains
the agent's prior context and is not independent evidence. After any applied sample edit,
for a new iteration or role/modality, or whenever independent confirmation is required,
spawn a fresh subagent with a separate workspace and iteration.

**Coordinator records use the review-version number, not a separate consolidation count.**
Write the decision as `coordinator.<ROUND>.md`, where `<ROUND>` is the newest review
iteration consolidated by that decision. The record may cite earlier reviews as history,
but its filename and heading must match the current review version. Never call the second
coordinator pass `coordinator.2.md` when it consolidates reviewer iteration 3 or 5.

**Keep one append-only operational log per video.** Immediately after every successful
subagent launch and terminal result, call `tools/coordinator_log.py <VIDEO_ID> spawn` or
`finish`; after an applied sample change, call `sample-edit`. Only the coordinator writes
`data/reviews/<VIDEO_ID>/coordinator.log`, never truncates it, and runs `check` before final
acceptance. The log records scheduling and edits; it does not replace per-question
`coordinator.<ROUND>.md` decisions.

---

## 4. The screen index is due to the `vision` probe, but a "yes" is checked against a frame

The text index of the video track (`screen_text.md`, `screen.jsonl`) is built **from the
frames and from nothing but the frames** — the metadata of the description run says
`with_transcript: false`. So for `probe_vision` it is not somebody else's modality but a
dense reading of its own, and it must be handed over.

**Why it must be, not merely may be.** Without the index the probe gets forty frames for a
half-hour video — one frame every forty-five seconds. Then `visiononly_solved = false`
means "they showed me forty pictures" rather than "vision was not enough", and the
`audio_dependency` label, which is derived straight from that flag, drifts systematically
to `required`. The index is built on a 0.5-second grid — denser than any budget that could
be handed to the probe as frames. That is, it moves the measurement towards honesty rather
than away from it.

**The asymmetry of the check.** A `false` answer is accepted as is: the probe looked
denser than usual and still did not find it. A `true` answer requires confirmation from a
frame — `audio_dependency: unnecessary` is derived from it, and recognition makes
mistakes: it confuses similar digits and finishes off things that are not there. Check
`looked_at`: there must be a frame in there, not a line of the index. One frame per
positive answer is cheap, and positive answers are few.

**Who is not given the index.** `probe_text` — it would receive the visual channel in
words, and `textonly_solved` would stop measuring anything. `probe_frame` — the index is a
timeline, and a frozen-frame probe must see one frame and no history. The script enforces
both bans itself.

**Measurements with the index and without it are not comparable**, which is why the
`screen_index_used` flag exists in `budget`. When assembling the set, look at it: a
`visiononly_solved` obtained the two ways looks the same from outside.

---

## 5. Reviewer workspaces are per role and are deleted after consolidation

Use exactly one workspace per reviewer role:

```
$PROJECT/.review_ws/<VIDEO_ID>/<QUESTION>/<SUBAGENT_NAME>/
```

Use this source matrix; a boundary-clipped source is clipped to the permitted interval for the role:

| Role | Transcript | `description.jsonl` index | Initial real frames | On-demand `--dense` |
|---|---|---|---|---|
| `semiblind` | clipped | clipped | existing scene frames, copied | allowed |
| `full_sample` | full | full | existing scene frames or manifest | allowed |
| `full_window` | clipped | clipped | existing scene frames or manifest | allowed |
| `probe_text` | clipped | forbidden | forbidden | forbidden |
| `probe_vision` | forbidden | clipped | existing scene frames, copied | allowed |
| `probe_frame` | forbidden | forbidden | exactly one frozen frame | forbidden |
| `probe_full` | clipped | clipped | existing scene frames, copied | allowed |
| `probe_verify` | clipped to `t_s` | clipped to `t_s` | existing scene frames, copied | allowed |

The initial visual material is the permitted part of `description.jsonl` plus the
existing scene-change frames listed in `bundle.json["frames"]`. Those frames were
produced by `tools/detect_scenes.py`; the coordinator must not pre-fill a uniform or
dense grid. A role marked `allowed` may call `--dense A B --step 1` after the
description or scene frames identify a suspicious interval.

After a review passes `schema/review.py --check` and its decisions have been incorporated
into `coordinator.<ROUND>.md`, remove that role's reproducible workspace:

```bash
python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --cleanup --out "$PROJECT/.review_ws/<VIDEO_ID>/<QUESTION>/<SUBAGENT_NAME>"
```

Keep an invalid or unconsolidated workspace for diagnosis. Never ask a validator to delete
it, and never share one workspace between roles.

---

## 6. The left boundary: stages A–C and the adjudication table

**The rule.** No `PASS` on 2.2 or 2.3 without an adjudication table, and no comparison of a
`t_val` against `t_start` that the table did not produce.

**Why.** On the pilot the semi-blind `t_val` was compared against `t_start` as two numbers,
and in 19 of the 23 samples where a declared decoy abutted the window `t_val` was a
function of the decoy's end, not of the video. The reviewers had written full answers
about moments inside the decoys ("supplies all four concrete values and signs") and nobody
read the phrase as "the rubric is met". The table makes the coordinator read every answer.

**Vocabulary.** *Blind* — the answer before any material (`prior_answer`). *Semi-blind* —
material up to `until`, no answer, no rubric, no `t_start`. *Sighted* — the full reviewer,
with the rubric.

**Stage A.** The semi-blind reviewer returns, per stretch, a trajectory: a `Candidate` with a
full answer at every change of the relevant state, the last at the end of the stretch. The
coordinator checks **every** answer against the rubric of the corresponding window, item by
item. The first answer that meets all required items is `t_val_A`. The reviewer's own
`t_val` and `sufficient` flags are self-reports and carry no status.

**Stage B.** `full_sample` may return `t_s`, the sighted proposal for the first moment the
rubric is satisfiable, with a frame in `t_s_basis`. If `t_s` is null or `t_s ≥ t_val_A`,
nothing more is needed: `t_val = t_val_A`.

**Stage C.** If `t_s < t_val_A`: prepare a fresh workspace with `--until <t_s> --screen
--verify`, spawn `probe_verify` with the prompt `prompts/probe_verify.md`, giving it the
task **without its when-clause** (strip the "when …" part by hand; if the clause defines
the object of the task, give the task whole and treat "the object is not there yet" as an
answer). Check its `answer` against the rubric. Met → `t_val = t_s`. Not met →
`t_val = t_val_A`. One call, short material, only on disagreement.

An early **correct** answer of an evaluated model at `t_m < t_start` (from
`data/outputs`) is a ready-made `t_s`: skip stage B and run stage C at `t_m`. The absence
of such an answer means nothing — the models are weak.

**Then** derive 2.2 and 2.3 from `t_val` as before (`t_val[0] < question_time` → 2.3;
`t_val[k] < t_start[k]` → 2.2). Inside an optional window is not a hit.

**The table**, one per sample and iteration, in `coordinator.<ROUND>.md`:

| t | answer (short) | rubric items ✓/✗ | reviewer's own view | classification |
|---|---|---|---|---|
| 704.0 | signs 0, −, 0, + via the cosine derivatives | 0 ✓ 1 ✓ 2 ✓ 3 ✓ | sufficient, high | **t_val_A** |
| 718.0 | the same | all ✓ | sufficient, high | confirmation |
| 737.0 | the same, through f | all ✓ | sufficient, high | (annotated t_start) |
| 690.0 (t_s) | — | — | sighted proposal | verified: not met → stays t_val_A |

Classifications: `t_val_A`, `confirmation`, `partial` (some items ✗ — name them), `no answer`,
and one row for `t_s` with the stage-C outcome. Then record the decision in the log:

```bash
python3 tools/coordinator_log.py <VIDEO_ID> adjudicate --sample-id <SAMPLE_ID> \
    --iteration <ROUND> --t-val-a 704.0 --t-s 690.0 --verified no --t-val 704.0 \
    --source semiblind.<ROUND>.json
```

**What to do on a hit** is unchanged (checklist 2.2): move `t_start` to `t_val`, or keep the
window and add an optional trigger for the early form when the condition in the question is
substantive. Either is an interval edit; the windows it touches are re-reviewed by
`full_window`.
