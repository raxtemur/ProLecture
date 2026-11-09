# The annotation pipeline: who does what

The document describes how a checked set of samples is obtained from a video. It answers the
question "in what order and by whose hands", whereas
[annotation_checklist.md](annotation_checklist.md) answers the question "what exactly is
checked". The role prompts are in [prompts/](prompts/).

> **2026-10-12.** This document, the coordinator's prompt and the prompts of the reviewers and
> the probes follow the checklist of version 2026-10-11 (`CHECKLIST_VERSION` in
> `schema/review.py`). Where they differ, the checklist and
> [prompts/definitions.md](prompts/definitions.md) win.

The pipeline is designed around three constraints:

- **the coordinator's context is expensive** — whoever holds the whole video in their head must
  not spend the window on frames; everything that can be is done by subagents, which return a
  digest;
- **frames are expensive, text is cheap** — the transcript is read in full at any length, images
  are issued on a budget (~50 per question being checked);
- **the checker must look with fresh eyes** — the reviewer gets the sample in its current form
  and gets neither the history of edits nor the past reviews.

---

## The scheme

```
    video + scene source
             │
   ┌─────────▼──────────┐
   │  Step 0. Artefacts │  tools/fetch_video.py, tools/make_bundle.py
   │  bundle.json       │  transcript, sparse frames, formulas, chapters
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Step 1. Proposer  │  prompts/proposer.md
   │  generates questions│ → data/annotations/partial/<id>.<interval>.jsonl (status: draft)
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Step 2. Validator │  tools/validate_samples.py   (checklist group 1)
   └─────────┬──────────┘
             │  no errors
   ┌─────────▼──────────────────────────────────┐
   │  Step 3. Reviewers and probes               │  prompts/reviewer_semiblind.md
   │  semi-blind ─> the moment the answer became │  prompts/reviewer_full_sample.md
   │             possible, the blind answer      │  prompts/reviewer_full_window.md
   │  per sample ─> question, rubric, t_s        │  prompts/probe_*.md
   │  per window ─> boundaries, one per window   │  checklist groups 2–8
   │  probes  ──> validation.* and audio_dependency │
   └─────────┬──────────────────────────────────┘
             │
   ┌─────────▼──────────┐   not PASS
   │  Step 4. Edits     │───────────┐
   │  the coordinator   │           │  what the edit touched
   └─────────┬──────────┘           │  goes for a repeat review
             │  all PASS            │  by fresh subagents
             ▼                      └──────────► back to step 2
   ┌─────────▼──────────┐
   │  Step 5. Checks    │  what is invisible from a single sample:
   │  across samples    │  twin comparability (5.1)
   └─────────┬──────────┘  on a hit — back to step 4
             │  ▲__________________________________________
             │
             │
   ┌─────────▼──────────┐
   │  Step 6. Closing   │  the coordinator: every sample validated or rejected,
   │  the video         │  check --final, the files merged (tools/merge_partials.py)
   └─────────┬──────────┘
             ▼
        data/annotations/<id>.jsonl → the measurement phase
```

---

## Step 0. Artefacts

Prepared once per video, by tools rather than by a model: the `transcript` with timecodes, the
sparse frames, the list of formulas from the scene source, the chapters.

The sparse frames in `data/bundles/<VIDEO_ID>/frames/` are produced by
`tools/detect_scenes.py`; `tools/make_bundle.py` invokes the detector and stores their
timecodes and paths in `bundle.json["frames"]`. They are content-selected, settled
scene-change frames, not a uniform time grid.

The dense visual description is prepared separately by `tools/describe_video.py` as
`description.jsonl`. Reviewer workspaces receive the boundary-clipped description and
the existing scene frames first. No uniform or dense grid is pre-filled by the
coordinator; a role that is allowed to use images may request `--dense` only after the
description or a scene frame identifies a suspicious interval.

## Step 1. The proposer

Reads the transcript and the sparse frames, invents questions, annotates the answer windows,
aligns the boundaries to frames, writes the `jsonl`. The prompt is
[prompts/proposer.md](prompts/proposer.md).

If the video is long, the step is split across subagents by chapter: each gets its own interval
and returns candidate questions, and the coordinator removes duplicates and brings them to a
common numbering. The point of the split is not speed but the coordinator's context:
looking at frames eats it fastest.

Parallel proposers **do not write into a common file**: each puts its candidates into
`data/annotations/partial/<VIDEO_ID>.<interval>.jsonl`. The coordinator assigns end-to-end
`id`s across the files before the first review, edits each record in the file that holds it, and
merges the files into `<VIDEO_ID>.jsonl` only when the video is closed (step 6). Otherwise they
would overwrite each other's file and collide on identical question numbers.

Control twins (the same question with a different `question_time`) are created by the coordinator
(step 5), not by the proposer: a twin by definition requires seeing the pair as a whole.

## Step 2. The validator

`/home/user/conda/bin/python3 tools/validate_samples.py data/annotations/*.jsonl`

Cheap, deterministic, run after every edit — including after every edit following a review. Until
the validator is green there is no point calling the reviewers: they will spend frames on a sample
that falls apart on arithmetic.

## Step 3. Reviewers and probes

Three reviewer roles per question plus the modality probes — in parallel, except what waits on
another's result: `probe_full` runs after `probe_text` and `probe_vision`, stage C after the result
that gives its `t_s` (below). The sample under check is passed to each **in the body of the
prompt**, so that the task is set unambiguously; but `full_sample` and `full_window` are not
forbidden the annotation file — they know the reference answer anyway, and the neighbouring
questions of the same video help to see whether one moment has been annotated twice. Truly
restricted are only the semi-blind reviewer (who must know neither the answer nor `t_start`; the
upper boundary of their stretch, equal to `t_end`, is in fact given to them — otherwise they would
watch the video to the end and see the answer) and the probes (who must not know the purpose of the
measurement). The modes have different, self-contained prompts:
[prompts/reviewer_semiblind.md](prompts/reviewer_semiblind.md),
[prompts/reviewer_full_sample.md](prompts/reviewer_full_sample.md) and
[prompts/reviewer_full_window.md](prompts/reviewer_full_window.md). The common prompt with branches
was split deliberately: half of the text in it was inapplicable to the reader, and to the semi-blind
mode it was actively harmful — it names fields they must not see.

**Why the full review is split into two roles.** The contract requires a line for each item of the
mode: an item without a line is indistinguishable from a passed one. A per-window launch,
meanwhile, gives the reviewer a frame budget for one window — and among the items there were some
that need the whole video (`no-missed-trigger`) or that are identical for all windows (the text of
the question, the rubric, the reference answer). Nine reviewers of a nine-window sample would nine
times answer the same thing about the rubric and nine times put `skipped` on trigger completeness,
and `skipped` forbids `PASS` — that is, on multi-window samples the cycle would not converge by
construction. The boundary is drawn by what the item refers to: what belongs to a window is what
is settled by looking at that window and nothing more. The `provenance` references, the
reference answer and the shape of the trigger set do not belong to a window — they are common, and
there is nothing to divide them between launches by.

**The semi-blind reviewer** gets the text of the question, `question_time` and a working folder.
They see neither `response`, nor `rubric`, nor `provenance`, nor the annotation file, nor the
window boundaries. Their work is items 4.2 and 4.3, item 2.6 (the question holds and can be
understood at `question_time`: their first stretch begins at zero, so the material up to that
moment is theirs) and the material for both checks of the left boundary: 2.3 (the answer was
available even before the question was issued) and 2.2 (the answer became possible between the
issue of the question and the opening of the window).

**The stretch is traversed consecutively and to the end.** The end of the stretch is chosen so
that the interval needed lies within it — which means the reviewer is not looking for "is there an
answer at all" but for "did it not appear earlier", and any hole in the middle is exactly the place
where an early appearance will hide. The budget ladder (screen description and transcript →
existing scene frames → dense around a suspicion) distributes the frames but grants no right to
skip stretches: the text sources must account for the stretch in full, and real frames confirm
candidate moments. Jumping straight to the end answers a question nobody asked.

**They may answer only from what is visible.** Completing an indistinguishable caption from
knowledge of the subject, recognising a familiar textbook problem in a half-drawn frame and
substituting its numbers is forbidden at both steps: both when looking for `t_val` and when writing
`prior_answer`. The error here is always one-directional — it moves `t_start` to the left, to a
moment where nothing has appeared yet.

Why "semi-" rather than "blind". They do know the upper boundary of their stretch — without it the
task cannot be set. What they do not know is where inside the stretch `t_start` runs, and that is
exactly what the reviewer's output checks.

**Stretches, not a single prefix.** A blind reviewer given the video up to the `t_start` of the
first window checks the left boundary of that window only: of a nine-window question the other
eight are checked by nobody, and the full reviewer is forbidden 2.2 and 2.3. So the reviewer goes
through the video in stretches, **one for each window — required and optional alike**:

| Stretch | From | To |
|---|---|---|
| 0 | 0 | `t_end` of the first window |
| k | `t_end` of window k−1 | `t_end` of window k |

Optional windows are included in the partition not for completeness of the count: their left
boundary is otherwise checked by nobody, and an answer next to a badly placed optional window still
counts towards the false alarms.

The first begins **at zero**, not at `question_time`: otherwise there is nothing to check 2.3 with
— the material before the issue of the question simply never reaches the reviewer's hands.

The stretch ends at `t_end` rather than starting at `t_start`, and that is essential. The question
"could you answer?" is meaningless for a multi-trigger sample — the answer is "yes, many times,
that is the point". The question "**from what moment** can one?" is always meaningful. The reviewer
knows that by the end of the stretch the answer is already available — and walks the stretch as a
**trajectory**: at every moment where the state of the screen or the speech relevant to the task
changed they write a complete answer from what is available up to that moment, the last one at the
end of the stretch (`Candidate` in the contract). Which of those answers is the first to meet the
rubric is decided by the coordinator, not by the reviewer.

The window boundaries are not named in the prompt: the upper boundary of the stretch is the `until`
field in the `limits.json` of their own folder.

**Nothing but the material is passed to them.** Until 2026-09-07 the declared distractor windows
were handed over as exclusion zones, on the argument that otherwise the reviewer would fall into the
sample's own trap. The argument was wrong in practice: the proposer had put a gap
`[question_time, t_start)` under the name of a distractor in 19 samples of 44, its `t_end` was the
window's `t_start`, and in 19 of the 23 samples with such a decoy `t_val` landed within a second
after its end — three different models, the same behaviour. The check had become a comparison of
two numbers the annotation itself supplied. The field is gone (see the note that replaced group 6
of the checklist), and with it the leak and items 6.2 and 6.4.

**Three stages for the left boundary, two agents with opposite biases.** The semi-blind trajectory
above is **stage A**; from it the coordinator derives `t_val_A` by checking every answer against the
rubric (the adjudication table in `prompts/coordinator.md`). **Stage B**: the full reviewer, who
knows the answer, may propose `t_s` — the first moment from which, in their view, the rubric is
satisfiable, with the frame that shows it. They were forbidden the left boundary because of a known
leftward bias; the ban is lifted because a check follows. If the question has a when-clause, they
read the proposer's line `the when-event gives: item <N> — …` in `validation.notes` (checklist 1.13)
as a claim: when the transcript or the screen index shows that item's content before the event, that
earlier moment is their `t_s`. **Stage C**: if `t_s < t_val_A` or there is no `t_val_A`, a fresh
semi-blind probe (`probe_verify`, prompt `prompts/probe_verify.md`) receives the task without its
when-clause as a signal to answer (what the rest of the question refers back to in it stays) and the
material up to `t_s`, and answers. Rubric met by the route of the level or a cheaper one → `t_val =
t_s`; met only by a harder route or not met → `t_val = t_val_A`. An early correct answer of an
evaluated model at `t_m < t_start` is a ready-made `t_s`: stage C runs at `t_m` directly. So is the
end of a required window's `evidence_span`, annotated or proposed by the window reviewer, when it
lies more than 2 s before `t_val_A` (or before `t_start` with no `t_val_A`) and not before the
stretch begins (checklist 7.5); stage B still runs then. The probe's folder is prepared exactly like
the semi-blind one, with `--verify`:

```bash
/home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --sample-id <SAMPLE_ID> --annotations data/annotations/<VIDEO_ID>.jsonl \
    --role probe_verify --until <t_s> --out <WORKSPACE>
```

The folder is prepared and **extended** by the coordinator, stretch by stretch:

```bash
/home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --sample-id <SAMPLE_ID> --annotations data/annotations/<VIDEO_ID>.jsonl \
    --role semiblind --window <k> --out <WORKSPACE>
```

With `--sample-id` the script reads the boundary off the record — here `t_end` of window `k`,
required or optional — and sets the channels of the role itself (`--screen` for the semi-blind reviewer, `--verify`
for the verification probe). It leaves `<WORKSPACE>.inputs.json` next to the folder: which version
of the record the folder was cut from. `coordinator_log.py spawn --workspace` refuses a folder whose
record has changed since.

`--screen` puts in a **text index of the video track** — `screen_text.md` (what was recognised on
the screen and from which second) and `screen.jsonl` (descriptions and per-second events), cut at
the same boundary as the transcript. This changes the economics of a stretch: "where on the screen
is 1.75" becomes a single `grep` instead of an hour of viewing, and frames are spent on target.

The index is made **by a model**, not by a human, so it is a search tool and not evidence: a moment
found through it must be seen by the reviewer on a real frame before they set a timecode. This is
written in the header of both files, and the same is repeated in the role prompts.

**Who is entitled to the index is decided by the channel, not by the role.** The description is
built from frames and from frames only (`with_transcript: false` in the run metadata), that is, it
is a function of the visual channel and nothing beyond it:

| To whom | `--screen` | Why |
|---|---|---|
| reviewers, `probe_vision`, `probe_full`, `probe_verify` | yes | the index is a dense reading of their own channel |
| `probe_text` | no | it would get the visual channel in words, and `textonly_solved` would stop measuring anything |
| `probe_frame` | no | the index is a timeline, and frozen-frame is obliged to see one frame and no history |

The script enforces this itself: `--screen` refuses to work with `--only transcript` and with
`--frame`.

For `probe_vision` the index is not merely harmless but **cures a known bias**. It is written above
in this document: scene frames alone may be too sparse over a half-hour lecture,
`visiononly_solved` drifts systematically to `false`, and the `audio_dependency` label to
`required`. The index is built on a 0.5-second grid, that is, denser than any budget that can be
issued to the probe in frames.

The price is a new viewing regime, and it must be told apart from the old one: the `budget` has a
`screen_index_used` field. Without it a `visiononly_solved` obtained in the two ways looks
identical, and the label would be derived from a mixture of regimes — exactly what the `Budget`
class was written for.

The rule for a positive answer: **a "yes" must stand on a frame, not on a line of the index.**
Recognition makes mistakes, and `visiononly_solved = true` gives `audio_dependency: unnecessary` —
a label that influences conclusions. A probe that named a quantity is obliged to name the frame it
saw it on as well; a negative answer requires no such confirmation.

For the semi-blind reviewer and the probes the frames are placed as **copies** — only that way does
the folder hold the boundary. For the full reviewers, who know the reference answer anyway, the
frames are issued as a manifest: `--index-only` writes `frames.md` with a list of timecodes and a
path to the bundle, copying nothing.

The reviewer cannot go forward beyond the boundary of the folder — there is no material there;
going back is allowed and necessary. One agent for all the stretches: it moves only forward in
time, so nothing needs to be "unseen", and in total the frames come to one pass over the video
instead of N prefixes.

What the coordinator derives from `t_val` — the reviewer passes no verdicts on boundaries
themselves, and `t_val` here is the **adjudicated** one (the first answer of the trajectory that
meets the rubric by the route of the sample's level or a cheaper one, corrected by stage C under
the same route test; an earlier answer that only a harder route reaches gets an optional window,
checklist 2.2), not the reviewer's self-report:

| Condition | Conclusion |
|---|---|
| `t_val[0] < question_time` | 2.3: the answer was available before the question was issued |
| `t_val[k] < t_start[k]` | 2.2: the window opens later than the answer became possible |
| `t_val[k] = null` | no answer of the trajectory meets the rubric: a signal for 2.5, 4.7 or 8.4 (a wrong reference) |

Inside an optional window is not a hit. The main thing the reviewer does not have and the
coordinator does is the rubric: no `PASS` on 2.2 is issued without the adjudication table, and a
`t_val` compared against `t_start` without it is the pilot's mistake all over again.

The separation is not cosmetic. A checker who knows the reference answer is biased in one
direction: on a half-drawn frame where the object is still arriving, they "recognise" an answer
that is not yet there and propose to shift `t_start` left. Since the coordinator applies those
proposals, over three iterations the window drifts monotonically, and oscillation — the only brake
— will not fire, because the drift is one-directional. For the same reason self-reporting on
contamination (4.2, 4.3) only makes sense before the reference answer has entered the context.

**The full reviewer** gets the whole sample and does everything else, split between two roles:
`full_sample` — 3.1, 3.2, 3.4 (the optional triggers on elements that appear one by one), 4.8,
4.9, 5.2–5.4, 7.3, 7.8, 8.2–8.5 and the proposal `t_s` of stage B; `full_window` — 2.4, 2.5,
3.3, 7.4, 7.5. The lists are `ROLE_ITEMS` in the contract. Items 2.6 (the semi-blind reviewer's),
4.9 and 7.8 entered it on 2026-10-05; a review carries their lines from checklist 2026-10-11
on.

On each stretch the semi-blind reviewer returns the whole **trajectory**, not a single `t_val`: a
full answer at every moment where the relevant state changed. From a bare number one cannot tell a
reviewer's error from an annotation error; from the answers one can. They must not be asked to name
the moment "when the answer became confident": stability is not correctness, and a confidently
wrong answer that stabilised early looks exactly like a right one — which is exactly why the
rubric check is done by the coordinator over every point and not by the reviewer over one.

`full_window` is launched **one per window**, always, not only on multi-window samples: the frame
budget is counted per window. `full_sample` is exactly one per sample, with a budget for the whole
video. A one-window sample gets two launches instead of one, a nine-window sample ten instead of
nine, but each with a task within its means.

The reviewer **does not edit files**. They propose changes; the coordinator applies them —
otherwise parallel subagents would fight over one `jsonl`.

The reviewer gets neither the past reviews of this question nor a description of what was fixed.
The reason is the same as the one behind our adversarial reviews: knowing what has already been
"fixed" turns an independent check into a confirmation of somebody else's conclusion, and exactly
those errors that survived the edit stop being found.

### The modality probes

Group 4 is closed not by runs of the models being evaluated but by **probes** — subagents given
the question and the material of the video in one modality and asked simply to answer. A probe does
not know it is taking part in a check and sees neither the reference answer nor the rubric; the
coordinator is the one who compares its answer.

Each has its own prompt, and that is not a formality: in a common prompt with four modes the
`vision` probe would read that a `transcript.md` lies somewhere nearby — that is, would learn
exactly what it was deprived of.

Why these are separate subagents rather than stages of one: context is one-directional. An agent
that has read the transcript will not give an independent answer from frames alone — what has been
read cannot be unseen. A series of answers within one agent is legitimate only when the information
increases, and that is already taken by the semi-blind reviewer (2.2).

There is no probe "with no material at all": its role is played by step 0 of the semi-blind
reviewer, who at that moment is in exactly that position (4.2, 4.3).

Order and cost:

| Probe | Prompt | Material | Frames | Fills in |
|---|---|---|---|---|
| `text` | [prompts/probe_text.md](prompts/probe_text.md) | transcript up to `t_end` | 0 | `textonly_solved` (4.4) |
| `frame` | [prompts/probe_frame.md](prompts/probe_frame.md) | one frame in the middle of the window | one probe per required window, one frame each | `frozenframe_solved` (4.6) |
| `vision` | [prompts/probe_vision.md](prompts/probe_vision.md) | frames up to `t_end` | up to 40 | `visiononly_solved` (4.5) |
| `full` | [prompts/probe_full.md](prompts/probe_full.md) | transcript and frames | up to 40 | `solvable` (4.7) |

The isolation of a probe rests on three things, and it is worth naming them honestly, because the
first of them is not a guarantee. The **prompt** forbids obtaining another modality, and that is a
request. The **script** does not let the material of two modes be mixed in one folder: it places a
`mode.json` marker next to `limits.json` and refuses to work if the directory was assembled by a
different mode (this can be bypassed with `--force`, deliberately). The **self-report** in
`violations` is the last line: a probe that did read something extra is obliged to say so. What is
missing is launching subagents in a restricted directory, so a probe that names a different `--out`
will get anything at all. For now this is accepted as it is.

The folders are prepared by the coordinator under
`$PROJECT/.review_ws/<VIDEO_ID>/<QUESTION>/<SUBAGENT_NAME>/`:

```bash
P=/home/user/conda/bin/python3
R="--sample-id <SAMPLE_ID> --annotations data/annotations/<VIDEO_ID>.jsonl"
$P tools/prepare_review_workspace.py <VIDEO_ID> $R --role probe_text   --out <WS>/probe_text
$P tools/prepare_review_workspace.py <VIDEO_ID> $R --role probe_vision --out <WS>/probe_vision
$P tools/prepare_review_workspace.py <VIDEO_ID> $R --role probe_frame --window <k> --out <WS>/probe_frame<k>
$P tools/prepare_review_workspace.py <VIDEO_ID> $R --role probe_full   --out <WS>/probe_full
```

The text, vision and full probes get the material up to `t_end` of the last required window, the
frame probe the middle frame of required window `k` — one per required window, logged as
`probe_frame<k>`. The script derives these from the record; the explicit forms (`--until`,
`--only`, `--frame`) remain for a look outside a launch.

A visual or full role starts with the clipped `description.jsonl` index and the
scene-change frames already present in `bundle.json["frames"]`, together with the frames at
both edges of its stretch: the script cuts them from the video whatever the scene detector
picked, so the screen at `until` itself is always there, and a `--dense` grid likewise ends
on its upper edge. Nothing later than `until` gets in. The coordinator does not
pre-sample the answer window or `evidence_span`. If the supplied material points to a
suspicious interval, the role may add a dense 1 fps pass itself:

```bash
$P tools/prepare_review_workspace.py <VIDEO_ID> --dense <A> <B> --step 1 --out <WS>/<ROLE>
```

With `--sheet` (at most 16 frames) the same call also tiles the frames into one image with
the second stamped on each cell. That is the default for a quick look: it costs one image,
and a gradual change is visible only side by side.

This permission is unchanged: it applies to the visual/full probes and reviewers, not to
`probe_text` or `probe_frame`. The description makes the initial search dense and
cheap; the on-demand real frames verify only the intervals that matter.

The actual grid goes into the `budget` of the review file. When the viewing regime changes there
will otherwise be nothing to tell old measurements from new.

The folders are **different**: one per probe. A common folder nullifies the whole design — the
`vision` probe need only open `transcript.md`, and `visiononly_solved`, from which
`audio_dependency` is derived, stops measuring anything. The `frame` folder does not even have a
`limits.json`: the boundaries file itself would tell the probe up to what moment the video runs,
and it must see one frame and nothing around it.

`full` is launched **only** if `text` and `vision` both answered incorrectly: a positive answer
from either already proves solvability, and there is no reason to pay for another viewing. In
practice this means the fourth probe is launched rarely.

What the coordinator does with all this:

- `blind_solved` is set by the **coordinator**, not by the semi-blind reviewer: the line in their
  `checks` is preliminary, because they have nothing to compare against. Whether the blind
  answer meets the rubric is scored by the evaluation judge (`coordinator_log.py blind-judge`);
  the coordinator departs from that verdict only by a logged `blind-ruling` that names its
  grounds, and a rewrite that keeps the rubric keeps the flag. When an answer counts as
  blind solving is defined in [prompts/definitions.md](prompts/definitions.md), "`blind_solved`":
  it is at once **correct** (it meets every substantive rubric item) and **honest** (it does not
  rest on assumptions about screen content not seen). A guess of the form "probably the screen
  shows the canonical textbook example, in which case you get such-and-such" does not count: the
  statement of the problem was guessed, the answer was not found. A hedged answer is not credited
  with the better of its branches: an answer that offers alternatives for one rubric item does
  not meet that item, in a blind answer and in a probe's answer alike (checklist 4.2); if the
  alternatives come from two readings of the question, that is a defect of the question. With
  `blind_solved = true` the candidate is excluded from the primary task set, but it
  continues through the review DAG. If it is otherwise correct and complete, use
  `status: validated` and retain it as a blind baseline. Use `status: rejected` only for an
  independent defect or deliberately abandoned work; a terminal rejected record is not sent
  through missing reviews merely to populate measurements;
- the answer of a probe whose `basis` says "general knowledge" in place of the material, or
  which admits that the model recognised the video, **does not count as a solution from the
  material**. Otherwise a `visiononly_solved = true` obtained from memory of the subject would
  give `audio_dependency = unnecessary` — the label would be derived from a recollection rather
  than from a measurement. Nor is it a measurement that the modality failed: such an attempt is
  repeated once (the repeat rule below), and the outcome of the repeat is final. The `basis`
  field exists for exactly this distinction, and the rule must be written down rather than
  implied;
- `solvable` is set by the coordinator by the rule
  `solvable = textonly_solved OR visiononly_solved OR <the answer of the full probe>`: success of
  any single-modality probe already proves solvability, and in that case the `full` probe is not
  launched at all — but the field must still be filled in, otherwise the sample will not pass into
  `validated` (`S-18`, `S-27`);
- `solvable = false` is a `CRITICAL_FAIL`: the question is not solvable even from the full
  material. Before setting it, rule out a wrong reference (checklist 8.4): a discrepancy between
  the probe and the reference means either that the probe failed or that the reference is wrong;
- `visiononly_solved` together with `solvable` give the `audio_dependency` label by the rule from
  4.5 — it is never set by hand;
- a modality counts as sufficient if its probe answered correctly on at least one **required**
  window (checklist 4.1);
- the coordinator copies the judge's item-by-item verdict on the blind answer into
  `coordinator.<ROUND>.md`, so that it is visible what the sample rests on (4.2);
- when the 2.5 checks of several required windows give different levels, the sample takes the
  **lowest** of them (2.5), and the coordinator reads every 2.5 verdict against the level settled
  by 7.3: the two items belong to different roles and run in parallel;
- `frozenframe_solved = true` with `reasoning_level` `L2`/`L3` is checked item by item
  (checklist 4.6): for each rubric item the probe got right, does the frame show the value the
  item asks for, or only the values it is computed from? If it shows the value of every such
  item, the level is inflated — `FIX_QUESTION`, relabelled `L1`, though never a `predict`,
  `counterfact` or `extend` (7.9): there the frame means a reveal inside the window (2.5 for a
  `predict`) or a wrong act (7.9). If at least one item had to be worked out, there is no
  contradiction, and the level is re-derived by the work left. With `L1` a positive answer is
  expected and means nothing.

Dataset consumers apply the two fields independently:

```python
primary_tasks = status == "validated" and not blind_solved
blind_baselines = status == "validated" and blind_solved
invalid_samples = status == "rejected"
```

Every probe is presented once, and the flags are set from the probe outcomes only (checklist
4.1). An outcome is positive when the answer, scored against the rubric item by item, is correct
and does not rest on a guess about material the probe was not given, nor on general knowledge in
place of the material or on recognising the video (the bullet on `basis` above). A positive
outcome stands. A negative one may be measured again at most once per probe and version of the
sample: on the stronger model of the run profile if the probe ran on a weaker one, otherwise on
the same model and only when the defect of the attempt can be named with evidence — a misread
frame, missing material, or an answer from memory named in `basis`. The flag is the outcome of
the last run. A probe that fails because the question omits a convention exposes a defect of the
question: the question is fixed. A disagreement between probes is a signal that the wording of
the question is vague.

## Step 4. Edits and a repeat review

The coordinator applies the proposed changes, re-runs the validator and sends for a **new**
review what the edit touched: a move of a boundary by 2 s or less and a `metadata` edit need no
second review; an edit of the windows that leaves the wording alone needs the `full_window`
review of the touched windows and a rerun of every probe whose material moved — `probe_frame` of
a moved window, and `probe_text`, `probe_vision`, `probe_full` when the `t_end` their material
runs to moved; the flag of the old run does not carry over; a new wording of the question is a
new version and goes through the full cycle (checklist, group 2 and 2.2). Each cycle ends in
`PASS`, an explicit terminal rejection or a rebuild as a new sample.

The reviews are saved: `data/reviews/<VIDEO_ID>/<SAMPLE_ID>/<role>.<ROUND>.json`, where the
per-window ones have the window number appended to the role (`full_window3.1.json`,
`probe_frame3.1.json`), and `probe_verify` the number of its `t_s` within the round
(`probe_verify2.1.json`). Without this
neither the iteration counter nor the detection of oscillation would survive a restart of the
coordinator.

The review is checked for completeness before it is applied: it must contain a line for every item
assigned to the mode — with the value `ok`, `fail`, `skipped` or `na`. A missing line is
indistinguishable from a passed check and deprives the rule about `skipped` below of its meaning.
The format is the contract `schema/review.py`, and a review is checked with its `--check`, not by
eye.

Limiters without which the cycle may not converge:

- **no more than three iterations** per question; after the third the coordinator stops editing
  and closes the question on what it has: `rejected` by the rules that reject, `validated`
  otherwise, with the objections still open written down;
- **oscillation** (the reviewers demand opposite things in turn) is also a stop, closed the same
  way: usually it means the wording of the question is vague, not the boundaries;
- **the first measurement stands.** If two reviewer measurements of the same edge disagree within
  2 s, the first stands and the second is a note, and no verdict may hinge on such a gap
  (checklist, preamble of group 2);
- a `CRITICAL_FAIL` **is not cured by iteration** — the sample is rejected, or its idea is
  rebuilt as a new sample (another moment for the question, another question or another level)
  that goes through the full cycle ([prompts/definitions.md](prompts/definitions.md),
  "`CRITICAL_FAIL`"). Lowering the level to `L1` without changing the windows or the wording
  needs no second review; it is legitimate only if the question does not itself give the answer,
  and never for a `predict`, `counterfact` or `extend`, which are never `L1` (7.9);
- **`skipped` does not count as a passed check.** If a reviewer honestly reported that they did
  not check a mandatory item (usually because of the frame budget), the verdict cannot be `PASS`:
  the question goes for a repeat review **pointwise** — the subagent is given the list of unchecked
  items and a narrowed interval, not the whole order of checks again. Without such a mode a repeat
  launch runs into the same budget and returns the same `skipped`.
  Otherwise exhausting the budget is indistinguishable from success — and in the pilot that is not
  a rarity but the ordinary state for questions with a long waiting interval;

## Step 5. Checks across samples

One item of the checklist is by construction invisible to an agent holding a single sample: 5.1
(agreement of the twins' rubric criteria). It is done by the coordinator
**after** all the questions have received a `PASS` — and necessarily after, because the edits of
step 4 are exactly what breaks them: moving `question_time` on one twin changes the `temporal_rel`
axis and makes the pair incomparable.

With the appearance of the `twin_of` field it moved to the validator (`S-23`, `S-24`), but only
on condition that both twins land **in the same run**: the checks are cross-sample and
will see nothing one file at a time. It remains for the coordinator to run the validator on the
whole set rather than on individual files.

On a hit the edit goes back to step 4, and **both** twins go for a repeat review: changing one of
the pair changes the meaning of the comparison for both.

It follows from the same that a twin is cheaper to create not when numbering the partials but
after the base sample has been through the cycle: otherwise both halves drift independently and the
divergence has to be fixed twice.

## Step 6. Closing the video

The coordinator closes every sample itself: `rejected` by the rules that reject, `validated`
otherwise. Nobody accepts the samples after it, so no sample is left in `draft`: a `draft` would
be neither measured nor rejected. A sample whose cycle ran past the iteration limit or oscillated
is closed the same way, with the objections still open written in its `coordinator.<ROUND>.md`.

When every sample is closed and `tools/coordinator_log.py <VIDEO_ID> check --final` passes, the
coordinator runs `tools/merge_partials.py <VIDEO_ID>`. It refuses while a sample is in `draft`,
an `id` is not end-to-end or repeats, the validator or `check --final` fails, or
`data/annotations/<VIDEO_ID>.jsonl` already exists (an earlier annotation of the video is never
overwritten); otherwise it writes that file in the order of the `id`s and removes the files from
`partial/`. A video is closed when its file in `data/annotations/` exists.

Reading the closed videos is outside the pipeline: it corrects the roles, the checklist and the
tools, not the statuses (see "What to measure the pipeline itself with").

Recorded separately is **which model played the proposer and the reviewers**: the plan requires it
to be excluded from the final table of results, and that can only be done after the fact if the
role was written down.

---

## The review contract

The contract is given by pydantic classes in [../schema/review.py](../schema/review.py) rather than
by a JSON schema: it is read not only by a human but by a model — which fills it in through
constrained decoding, and `Field(description=...)` reaches it verbatim.

The subagent **saves the filled-in object to a file** and returns textual reasoning to the
coordinator, not json:

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/<role>.<ROUND>.json
```

where `<role>` is a value of `Role` in the contract: `semiblind`, `full_sample`, `full_window`,
`probe_text`, `probe_vision`, `probe_frame`, `probe_full`, `probe_verify` — with the window
index after `full_window` and `probe_frame`, and the number of the `t_s` after `probe_verify`.
Reviews are not overwritten: the accumulated rounds make oscillation visible, which a single last
file hides. The folder goes under git — otherwise the plan's requirement "generator ≠ judge ≠
participant" cannot be checked after the fact: the sample remembers the flags but does not remember
who measured them.

### The coordinator's record

The subagents report with a structure, the coordinator with free text, and that is not an
indulgence. Everything they do is decisions on top of other people's answers: compare, derive a
flag, apply an edit. What gives checkability here is not a schema but the link "these json files →
these changes", and it is enough to write that down in words.

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/coordinator.<ROUND>.md
```

`<ROUND>` is the newest review iteration consolidated by the decision, not an independent
counter of coordinator invocations. A record may cite earlier reviews as history, but its
filename and heading must match the current review version.

What must be in it, one paragraph per decision:

- **which files were read** — list the paths of this round's reviews and probe answers;
- **which flag was set and why** — what the probe answered, what the reference answer says,
  credited or not. This is exactly where the "qualitative judgement" lives that we deliberately did
  not turn into a numeric scale: since there is no scale, at least a sentence of text must remain;
- **what was derived arithmetically** — 2.2/2.3 from `t_val`, the dependence label from the probe
  flags, `solvable` from the single-modality ones. It is enough to name the rule and the numbers
  substituted;
- **what was changed in the sample** — the field, before, after;
- **what was left unresolved** — items with `skipped`, discrepancies between rounds, objections
  still open at the iteration limit.

Why this is needed when the coordinator remembers everything anyway: they do not. The context gets
compressed, and two rounds later there is nowhere to recover the grounds for a flag from — while
the flag will survive the session and travel into the dataset. Besides, whoever reads the closed
video later would see the result but not what it was obtained from. And most importantly: the coordinator
is the only participant who both **edits the samples** and **judges the probe answers**. We have
deliberately not separated those roles for now; in that case the only thing distinguishing a
decision from arbitrariness is the recorded grounds.

### Coordinator operational log

The per-question record explains decisions; a separate append-only log preserves their chronology:

```
data/reviews/<VIDEO_ID>/coordinator.log
```

The coordinator writes one JSON object per line through `tools/coordinator_log.py`. Record `spawn`
immediately after a subagent is successfully launched, `finish` when it completes, fails or is
interrupted, and `sample-edit` after a change is actually applied. The finish summary names the
artifact and the approximate result; the edit summary names the changed fields and the review that
caused them. Timestamps come from the coordinator process in ISO 8601 with an offset. Subagents do
not write this file, resumed sessions append to it rather than truncating it, and unknown historical
start times are never reconstructed as facts. No line is edited after it is written. The tool
refuses an `adjudicate` row that would not pass the check of its stretch before writing it, and a
wrong row already written is corrected by logging its stretch anew with `adjudicate --correction`
([prompts/coordinator.md](prompts/coordinator.md), §6, "Correcting a stretch").

Before closing the video, run:

```bash
python3 tools/coordinator_log.py <VIDEO_ID> check --final
```

The check validates the JSON lines and requires every recorded launch to have exactly one terminal
event. `--final` also fails on an edit whose reruns have not happened (a terminally rejected sample
owes none) and on a modality probe whose last run was cut at material the record no longer gives.
`spawn` records the workspace and the version of the record it was cut from, and `finish` the role
and verdict of the artifact; a finish under a name with no open launch is refused. The operational
log supplements rather than replaces `coordinator.<ROUND>.md`.

Before reporting, the subagent checks itself:

```bash
/home/user/conda/bin/python3 schema/review.py --check <file>
```

Three things the contract is written this way for.

**Items are addressed by name, not by number.** The numbering of the checklist changes — in a
single session group 4 moved as a whole — and a review saved under the key `"4.6"` reads, after the
rearrangement, as a review of a different item, silently. The contract holds `Group` and `Item`
(`answer-possible-before-start`, `rubric-within-question`); the numbers stayed in the checklist for
people.

**The order of fields inside a check is the order of reasoning** (Schema-Guided Reasoning):
`looked_at` → `findings` → `criterion` → `steps` → and only then `result`. Under constrained
decoding the fields are generated top to bottom, so the verdict is written after the grounds have
been fixed, not the other way round. The side benefit matters more than the direct one: when two
reviewers disagree, the `steps` show **at which step** they diverged — not merely that the verdicts
differ.

**Completeness is checked by the schema.** `ROLE_ITEMS` sets which items each mode is obliged to
close; a review without a line for an item of its mode simply will not be saved. A missing line is
indistinguishable from a passed check — exactly the substitution `skipped` was introduced to
forbid. Other people's items are rejected too: the full reviewer knows the reference answer and
therefore cannot judge the left boundaries, while the semi-blind reviewer does not see `t_start`
and therefore passes no verdict on them at all — the coordinator derives it from `scans`.

`"result": "skipped"` is a legitimate and necessary answer when the budget is exhausted, but it
does **not** yield a `PASS`: see the limiters of step 4.

**The verdicts**, in increasing order of severity; the final one equals the worst that fired:

| Verdict | Meaning | Who fixes it |
|---|---|---|
| `PASS` | keep as is | — |
| `FIX_INTERVALS` | window boundaries, the trigger set | the coordinator; a shift of boundaries is applied as is, except that a span is first checked against `t_val` (checklist 7.5); adding a trigger requires writing `response`, `rubric`, `evidence_span`, `trigger_modality` |
| `FIX_QUESTION` | the wording, the rubric, the labels; the sample keeps measuring what it measures | the coordinator, with a revision of the rubric |
| `CRITICAL_FAIL` | cannot be cured by moving boundaries or by rewording while the sample keeps measuring what it measures: `status: rejected`, or the idea is rebuilt as a new sample that goes through the full cycle | the coordinator; a rejected record is retained for audit |

**The mapping of checklist items to verdicts** (the default value; a reviewer may justify
another):

| Item | Verdict on a hit |
|---|---|
| 2.2 the answer is possible earlier than `t_start` | `t_val` is the first passing answer by the route of the sample's level or a cheaper one, from stage A or stage C. When it is the author's own answer on an `L2`/`L3`/`predict` sample, no window moves onto it: the verdict of 8.3 for the author's answer before the window. An earlier answer that only a harder route reaches gets an optional window (`FIX_INTERVALS`). Then by the gap `t_start − t_val`: up to 2 s `FIX_INTERVALS` applied as a nudge — the edge moves to the measured value with no second review; 2–10 s `FIX_INTERVALS`, `t_start` moves together with `evidence_span`, the touched window is reviewed again and the probes whose material moved are rerun; over 10 s `FIX_INTERVALS` (an early optional window) for a substantive when-clause, `FIX_QUESTION` for an empty one — the ladder of checklist 2.2 |
| 2.3 the answer was available before `question_time` | derived from the adjudicated `t_val` (by the route of the level or a cheaper one). A gap of up to 2 s: `question_time` moves to `t_val` with no second review, and 2.2 measures `t_start` against the same `t_val`. A larger gap: `FIX_QUESTION` — the axis changes, not the window; step 2 of the ladder of checklist 2.2: `question_time` moves back to `t_val` as a new version of the question where the wording allows it at that moment (2.6), otherwise the window opens at `question_time` and the axis is derived as `at`/`post` |
| 2.4 the window can be tightened | `FIX_INTERVALS`, and only if the empty part is more than 2 s; a window whose answer is the event itself is not narrowed below 5 s past the event |
| 2.5 the author gives the answer inside the window or within 10 s after it | by the split of the rubric items (checklist 2.5), recorded in the `split` of the check; `schema/review.py` refuses a verdict the split does not allow. Given after the window: `FIX_INTERVALS` or `FIX_QUESTION`, the level stays; the window is fixed first and split again. Given inside the window: the level is re-derived from the residue — `ok` if it stays, `FIX_QUESTION` if it changes; the windows stay. An empty residue in a required window of an `L2`/`L3` sample: `CRITICAL_FAIL`, or `FIX_INTERVALS` when the `proposal` names a new `t_end` at which the window still contains what the answer is worked out from, lasts at least 5 s and closes 10 s before the author's answer. An empty residue in an optional window of an `L2`/`L3` sample: `FIX_INTERVALS` (the window closes 10 s before the author's answer or is removed), but `CRITICAL_FAIL` if a later required window scores the same items. When items the question itself hands over empty the residue, `FIX_QUESTION`: rewording returns them to it. On `L1` an empty residue is the norm, provided the question itself does not give the answer; a question that hands over every item: `FIX_QUESTION`. On a `predict` an item the author reveals inside the window takes the verdicts of an empty residue, or `FIX_QUESTION` when the revealed items can leave the rubric and something is still left to predict; an item the question itself gives away: `FIX_QUESTION` |
| 2.6 the question does not hold or cannot be understood at `question_time` | `FIX_QUESTION`: the coordinator rewords the question |
| 3.1 an uncovered candidate for a firing | `FIX_INTERVALS` (add a trigger) or `FIX_QUESTION` if the wording is fixed |
| 3.2 an inconsistent criterion | `FIX_QUESTION`; `FIX_INTERVALS` when the cure is removing the trigger |
| 3.4 elements appear one by one, no optional triggers on them | `FIX_INTERVALS`; `FIX_QUESTION` if the wording insists on "simultaneously" without a reason |
| 4.2 the answer was given without the video at all | set `blind_solved: true`; complete the review, try to anchor the answer to video-specific content under 4.8, and exclude the sample from primary tasks; reject only for an independent defect or abandoned work |
| 4.3 the video was recognised | no verdict: the flag stays in the review as data for the separate measurement of how well models remember the videos |
| 4.6 a single frame is enough on `L2`/`L3` | `FIX_QUESTION` with the level lowered to `L1` only if the frame shows the value of every item the probe got right; otherwise the level is re-derived by the work left. Never `L1` on a `predict`, `counterfact` or `extend` (7.9): on a `predict` the frame is the author's reveal inside the window, and the verdicts are those of 2.5 for a `predict`; on a `counterfact` or an `extend` the act is wrong, the cure of 7.9 |
| 4.7 the question is not solvable even from the full material | `CRITICAL_FAIL`, once 8.4 has ruled out a wrong reference |
| 4.8 the question asks for no scientific content of this video | (a) no scientific target: `CRITICAL_FAIL`; (b) the question rests on the topic rather than on this video: `FIX_QUESTION` |
| 4.9 the outcome of a check does not depend on the video | `CRITICAL_FAIL`; if the reviewer sees how to rebuild the question so that its check could fail, the `proposal` says how |
| 5.x | `FIX_QUESTION` |
| 7.3 `reasoning_level` is inflated | `FIX_QUESTION`; the level is that of the cheapest route to the rubric; the verdict of 2.5 depends on it, and the coordinator reads 2.5 against it |
| 7.4 `depends_on` is not confirmed by the rubric | `FIX_QUESTION` |
| 7.5 `evidence_span` is not on the last piece of evidence | `FIX_INTERVALS`. The coordinator first checks the span against `t_val` of its stretch (checklist 7.5): a span that ends more than 2 s before `t_val_A` may be a `t_s` for stage C, and a proposed span that then disagrees with `t_val` is not applied. Then: when the derived axis changes, a `boundary` edit with the rerun of the window; when it does not, a `metadata` edit with no second review, provided the validator passes; a disagreement of 2 s or less about where a span ends is not applied (checklist, preamble of group 2) |
| 7.8 the `act` does not match the video | `FIX_QUESTION`; for a `predict` the author never answers, the `proposal` names the act the question is (`extend`, `counterfact`) |
| 8.2 the reference describes something other than what is in the frame | `FIX_INTERVALS` |
| 8.3 the reference contradicts the windows | a reference that places before the window what the answer is worked out or read from: its moment is `t_s`, and the verdict is that of 2.2 (of 2.3 before `question_time`); one that places the author's own answer before the window of an `L2`/`L3`/`predict` sample: `CRITICAL_FAIL`, or `FIX_INTERVALS` when the window can close 10 s before that answer, last at least 5 s and keep what the answer is worked out from; lowering to `L1` does not cure it |
| 8.4 the reference answer or a rubric item is wrong | `FIX_QUESTION`: the reference and the rubric are rewritten; `CRITICAL_FAIL` only when the question has no correct answer the video supports |
| 8.5 the twins' reference answers diverge in substance | `FIX_QUESTION` |

---

## What is automated

Steps 0 and 2 are tools, step 1 is the proposer agent. Steps 3–6 are run by the coordinator agent
from its prompt, with
`tools/prepare_review_workspace.py` (the workspaces of the roles, dense frames and sheets on
request), `tools/coordinator_log.py` (the operational log), `tools/merge_partials.py` (closing
the video) and the contract `schema/review.py` (the completeness of a review, `--check`). Launching the roles and merging their verdicts are not
automated: the coordinator does both by hand.

## What to measure the pipeline itself with

Reading the closed videos exists to find what the automation missed, but "finding" has to be
turned into a count, otherwise there will be nothing to improve the pipeline by. Three quantities
worth counting from the very first run:

- how many errors only the reader found — that is what replenishes the checklist;
- how many of the reviewers' proposals the reader would have rejected — the false alarm rate;
- how many items were marked `ok` but turned out to be broken — the most expensive category.

A cheap way to check the pipeline before it spoils anything: run it on the already annotated ten
samples of the pilot, some of whose errors are known, and see which of them it finds.
