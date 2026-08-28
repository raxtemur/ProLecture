# The annotation pipeline: who does what

The document describes how a checked set of samples is obtained from a video. It answers the
question "in what order and by whose hands", whereas
[annotation_checklist.md](annotation_checklist.md) answers the question "what exactly is
checked". The role prompts are in [prompts/](prompts/).

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
   │  generates questions│ → data/annotations/<id>.jsonl (status: draft)
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Step 2. Validator │  tools/validate_samples.py   (checklist group 1)
   └─────────┬──────────┘
             │  no errors
   ┌─────────▼──────────────────────────────────┐
   │  Step 3. Reviewers and probes               │  prompts/reviewer_semiblind.md
   │  semi-blind ─> the moment the answer became │  prompts/reviewer_full_sample.md
   │             possible, contamination flags   │  prompts/reviewer_full_window.md
   │  per sample ─> question, rubric, decoys     │  prompts/probe_*.md
   │  per window ─> boundaries, one per window   │  checklist groups 2–8
   │  probes  ──> validation.* and audio_dependency │
   └─────────┬──────────────────────────────────┘
             │
   ┌─────────▼──────────┐   not PASS
   │  Step 4. Edits     │───────────┐
   │  the coordinator   │           │  the same question goes
   └─────────┬──────────┘           │  for a repeat review
             │  all PASS            │  by fresh subagents
             ▼                      └──────────► back to step 2
   ┌─────────▼──────────┐
   │  Step 5. Checks    │  what is invisible from a single sample:
   │  across samples    │  twins and their distractors
   └─────────┬──────────┘  on a hit — back to step 4
             │  ▲__________________________________________
             │
             │
   ┌─────────▼──────────┐
   │  Step 6. A human   │  mandatory acceptance, not only on failure
   └─────────┬──────────┘
             ▼
        status: draft → ready for the measurement phase (checklist group 4)
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
and returns candidate questions, and the coordinator merges them, removes duplicates and brings
them to a common numbering. The point of the split is not speed but the coordinator's context:
looking at frames eats it fastest.

Parallel proposers **do not write into a common file**: each puts its candidates into
`data/annotations/partial/<VIDEO_ID>.<interval>.jsonl`, and only the coordinator merges them into
`<VIDEO_ID>.jsonl`, assigning end-to-end `id`s. Otherwise they would overwrite each other's file
and collide on identical question numbers.

Control twins (the same question with a different `question_time`) are created by the coordinator
at merge time, not by the proposer: a twin by definition requires seeing the pair as a whole.

## Step 2. The validator

`/home/user/conda/bin/python3 tools/validate_samples.py data/annotations/*.jsonl`

Cheap, deterministic, run after every edit — including after every edit following a review. Until
the validator is green there is no point calling the reviewers: they will spend frames on a sample
that falls apart on arithmetic.

## Step 3. Reviewers and probes

Three reviewer roles per question plus the modality probes — all in parallel. The sample under
check is passed to each **in the body of the prompt**, so that the task is set unambiguously; but
`full_sample` and `full_window` are not forbidden the annotation file — they know the reference
answer anyway, and the neighbouring questions of the same video help to see whether one moment has
been annotated twice. Truly restricted are only the semi-blind reviewer (who must know neither the
answer nor `t_start`; the upper boundary of their stretch, equal to `t_end`, is in fact given to
them — otherwise they would watch the video to the end and see the answer) and the probes (who
must not know the purpose of the measurement). The modes have different, self-contained prompts:
[prompts/reviewer_semiblind.md](prompts/reviewer_semiblind.md),
[prompts/reviewer_full_sample.md](prompts/reviewer_full_sample.md) and
[prompts/reviewer_full_window.md](prompts/reviewer_full_window.md). The common prompt with
branches was split deliberately: half of the text in it was inapplicable to the reader, and to the
semi-blind mode it was actively harmful — it names fields they must not see.

**Why the full review is split into two roles.** The contract requires a line for each item of the
mode: an item without a line is indistinguishable from a passed one. A per-window launch,
meanwhile, gives the reviewer a frame budget for one window — and among the items there were some
that need the whole video (`no-missed-trigger`) or that are identical for all windows (the text of
the question, the rubric, the reference answer). Nine reviewers of a nine-window sample would nine
times answer the same thing about the rubric and nine times put `skipped` on trigger completeness,
and `skipped` forbids `PASS` — that is, on multi-window samples the cycle would not converge by
construction. The boundary is drawn by what the item refers to: what belongs to a window is what
is settled by looking at that window and nothing more. Decoys, `provenance` references and the
reference answer do not belong to a window — they are common, and there is nothing to divide them
between launches by.

**The semi-blind reviewer** gets the text of the question, `question_time` and a working folder.
They see neither `response`, nor `rubric`, nor `provenance`, nor the annotation file, nor the
window boundaries. Their work is items 4.2, 4.3 and the material for both checks of the left
boundary: 2.3 (the answer was available even before the question was issued) and 2.2 (the answer
became possible between the issue of the question and the opening of the window).

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
`prior_answer`. The error here is always one-directional — it moves `t_start` to the left and
erases the trap the author of the question intended.

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
knows that by the end of the stretch the answer is already available, and looks for the earliest
point `t_val` from which the question can be answered on the merits.

The window boundaries are not named in the prompt: the upper boundary of the stretch is the `until`
field in the `limits.json` of their own folder.

**The distractors are passed to them — with windows and reasons.** Without this the mechanism
breaks on the sample's own traps: a reviewer who does not know that a moment is marked as a decoy
will honestly put `t_val` there, and the coordinator will derive 2.2 arithmetically and shift the
boundary left. In the pilot **8 segments out of 15** are arranged this way, that is, this is not
an edge case but the ordinary one. Passing the decoys does not weaken the check, because the
division of labour is preserved: that a decoy really is a decoy is checked by the full reviewer
under 6.2; the semi-blind reviewer takes it as given and looks for **other** moments where the
answer becomes possible. They still know neither `t_start`, nor the reference answer, nor the
rubric.

Hence a requirement on the text of `distractor.why`: it explains what makes the moment tempting and
what it lacks, but **does not name the correct answer** — otherwise passing the decoys turns into
passing the reference answer. This is item 6.4.

The folder is prepared and **extended** by the coordinator, stretch by stretch:

```bash
/home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --until <t_end of window k> --screen --out <WORKSPACE>
```

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
| reviewers, `probe_vision`, `probe_full` | yes | the index is a dense reading of their own channel |
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
themselves:

| Condition | Conclusion |
|---|---|
| `t_val[0] < question_time` | 2.3: the answer was available before the question was issued |
| `t_val[k] < t_start[k]` | 2.2: the window opens later than the answer became possible |
| `t_val[k] = null` | there is no answer where there must be one: a signal for 2.5 or 4.7 |

An insurance policy for the case where a decoy was passed on and the reviewer fell for it anyway:
before declaring 2.2, the coordinator looks at **where** `t_val` landed. Inside a declared decoy or
an optional window — not a hit. And the main thing the reviewer does not have and the coordinator
does: comparing `answer_at_t_val` against the rubric. A decoy by definition gives an **incomplete**
answer; a genuine early firing gives an answer that satisfies the rubric in full.

The separation is not cosmetic. A checker who knows the reference answer is biased in one
direction: on a half-drawn frame where the object is still arriving, they "recognise" an answer
that is not yet there and propose to shift `t_start` left. Since the coordinator applies those
proposals, over three iterations the window drifts monotonically, and oscillation — the only brake
— will not fire, because the drift is one-directional. For the same reason self-reporting on
contamination (4.2, 4.3) only makes sense before the reference answer has entered the context.

**The full reviewer** gets the whole sample and does everything else: 2.4, 2.5, group 3, 4.8,
5.2–5.4, 6.1–6.2, 7.3–7.5, 8.2–8.3.

On each stretch the reviewer returns not only `t_val` but also the **candidates**: which moments
they considered and why they discarded them. From a bare number one cannot tell a reviewer's error
from an annotation error; from the candidates one can. They must not be asked to name the moment
"when the answer became confident": stability is not correctness, and a confidently wrong answer
that stabilised early looks exactly like a right one.

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
| `frame` | [prompts/probe_frame.md](prompts/probe_frame.md) | one frame in the middle of the window | 1 per trigger | `frozenframe_solved` (4.6) |
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
$P tools/prepare_review_workspace.py <VIDEO_ID> --until <t_end> --only transcript --out <WS>/probe_text
$P tools/prepare_review_workspace.py <VIDEO_ID> --until <t_end> --only frames --screen --out <WS>/probe_vision
$P tools/prepare_review_workspace.py <VIDEO_ID> --frame <(t_start+t_end)/2> --out <WS>/probe_frame
$P tools/prepare_review_workspace.py <VIDEO_ID> --until <t_end> --screen --out <WS>/probe_full
```

A visual or full role starts with the clipped `description.jsonl` index and the
scene-change frames already present in `bundle.json["frames"]`. The coordinator does not
pre-sample the answer window or `evidence_span`. If the supplied material points to a
suspicious interval, the role may add a dense 1 fps pass itself:

```bash
$P tools/prepare_review_workspace.py <VIDEO_ID> --dense <A> <B> --step 1 --out <WS>/<ROLE>
```

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
  `checks` is preliminary, because they have nothing to compare against. An answer counts as blind
  solving when it is at once **correct** (agrees with the rubric) and **honest** (does not rest on
  assumptions about material not seen — see `prior_answer_assumptions`). A guess of the form
  "probably the screen shows the canonical textbook example, in which case you get such-and-such"
  does not count: the statement of the problem was guessed, the answer was not found. A hedged
  answer with two branches counts only if the wrong branch would have cost the participant a
  point. With `blind_solved = true` the candidate is excluded from the primary task set, but it
  continues through the review DAG. If it is otherwise correct and complete, use
  `status: validated` and retain it as a blind baseline. Use `status: rejected` only for an
  independent defect or deliberately abandoned work; a terminal rejected record is not sent
  through missing reviews merely to populate measurements;
- the answer of a probe whose `basis` says "general knowledge", or which admits that the model
  recognised the video, **does not count as a solution from the material**. Otherwise a
  `visiononly_solved = true` obtained from memory of the subject would give
  `audio_dependency = unnecessary` — the label would be derived from a recollection rather than
  from a measurement. The `basis` field exists for exactly this distinction, and the rule must be
  written down rather than implied;
- `solvable` is set by the coordinator by the rule
  `solvable = textonly_solved OR visiononly_solved OR <the answer of the full probe>`: success of
  any single-modality probe already proves solvability, and in that case the `full` probe is not
  launched at all — but the field must still be filled in, otherwise the sample will not pass into
  `validated` (`S-18`, `S-27`);
- `solvable = false` is a `CRITICAL_FAIL`: the question is not solvable even from the full material;
- `visiononly_solved` together with `solvable` give the `audio_dependency` label by the rule from
  4.5 — it is never set by hand;
- `frozenframe_solved = true` with `reasoning_level` `L2`/`L3` means the level is inflated, a
  `FIX_QUESTION` under 7.3. With `L1` this is normal and means nothing.

Dataset consumers apply the two fields independently:

```python
primary_tasks = status == "validated" and not blind_solved
blind_baselines = status == "validated" and blind_solved
invalid_samples = status == "rejected"
```

The probes are asked again pointwise if their answers diverge between iterations of the cycle. A
disagreement that persists is a signal that the wording of the question is vague: the sample goes
to a human or becomes `rejected` if the repair is abandoned.

## Step 4. Edits and a repeat review

The coordinator applies the proposed changes, re-runs the validator and sends the corrected
question for a **new** review. Each cycle ends in `PASS` or an explicit terminal rejection.

The reviews are saved: `data/reviews/<VIDEO_ID>/<SAMPLE_ID>/<role>.<ROUND>.json`, where the
per-window ones have the window number appended to the role: `full_window3.1.json`. Without this
neither the iteration counter nor the detection of oscillation would survive a restart of the
coordinator, and the human at step 6 would have nothing to be shown.

The review is checked for completeness before it is applied: it must contain a line for every item
assigned to the mode — with the value `ok`, `fail`, `skipped` or `na`. A missing line is
indistinguishable from a passed check and deprives the rule about `skipped` below of its meaning.
The review format is worth fixing with a schema (`schema/review.schema.json`) and checking with the
same, rather than by eye.

Limiters without which the cycle may not converge:

- **no more than three iterations** per question; after the third the question goes to a human
  with the accumulated reviews;
- **oscillation** (the reviewers demand opposite things in turn) is also a stop and a handover to
  a human: usually it means the wording of the question is vague, not the boundaries;
- a `CRITICAL_FAIL` **is not cured by iteration** — the sample is either rewritten from scratch or
  deleted;
- **`skipped` does not count as a passed check.** If a reviewer honestly reported that they did
  not check a mandatory item (usually because of the frame budget), the verdict cannot be `PASS`:
  the question goes for a repeat review **pointwise** — the subagent is given the list of unchecked
  items and a narrowed interval, not the whole order of checks again. Without such a mode a repeat
  launch runs into the same budget and returns the same `skipped`.
  Otherwise exhausting the budget is indistinguishable from success — and in the pilot that is not
  a rarity but the ordinary state for questions with a long waiting interval;
- **the contamination flags accumulate.** One recognised video is noise, six out of ten is a
  decision that the video is unusable. The coordinator keeps the count over the whole set and
  carries it into the step 6 report.

## Step 5. Checks across samples

Some items of the checklist are by construction invisible to an agent holding a single sample: 5.1
(agreement of the twins' rubric criteria) and 6.3 (their decoys). They are done by the coordinator
**after** all the questions have received a `PASS` — and necessarily after, because the edits of
step 4 are exactly what breaks them: moving `question_time` on one twin changes the `temporal_rel`
axis and makes the pair incomparable.

With the appearance of the `twin_of` field both moved to the validator (`S-23`, `S-24`, `S-26`),
but only on condition that both twins land **in the same run**: the checks are cross-sample and
will see nothing one file at a time. It remains for the coordinator to run the validator on the
whole set rather than on individual files.

On a hit the edit goes back to step 4, and **both** twins go for a repeat review: changing one of
the pair changes the meaning of the comparison for both.

It follows from the same that a twin is cheaper to create not when merging the partials but after
the base sample has been through the cycle: otherwise both halves drift independently and the
divergence has to be fixed twice.

## Step 6. Acceptance by a human

The extent of this step changes over time, and that is worth stating explicitly.

This step does not contradict the fact that level `[H]` in the checklist is empty: an empty `[H]`
means "no item waits for a human", while acceptance checks not the items but the checklist itself —
that it catches everything it needs to.

**For now, while the pipeline is being calibrated, acceptance is exhaustive.** We do not yet know
which errors the automatic cycle lets through, and the only way to find out is to look at
everything and compare with what the reviewers found. The side result of this step matters more
than its direct one: it yields new checklist items.

**Later it becomes selective**, plus necessarily everything the cycle could not close by itself:
questions with a `CRITICAL_FAIL`, those that went over the iteration limit, oscillating ones, and
those with `skipped` items left at the last iteration.

The human is given: the sample itself, the accumulated reviews from `data/reviews/`, the count of
contamination flags and the list of items marked `skipped` at the last iteration.

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

where `<role>` is `semiblind`, `full`, `probe_text`, `probe_vision`, `probe_frame`, `probe_full`.
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
- **what was left unresolved** — items with `skipped`, discrepancies between rounds, questions for
  the human.

Why this is needed when the coordinator remembers everything anyway: they do not. The context gets
compressed, and two rounds later there is nowhere to recover the grounds for a flag from — while
the flag will survive the session and travel into the dataset. Besides, the human at step 6
otherwise sees the result but not what it was obtained from. And most importantly: the coordinator
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
start times are never reconstructed as facts.

Before final acceptance, run:

```bash
python3 tools/coordinator_log.py <VIDEO_ID> check
```

The check validates the JSON lines and requires every recorded launch to have exactly one terminal
event. The operational log supplements rather than replaces `coordinator.<ROUND>.md`.

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
| `FIX_INTERVALS` | window boundaries, the trigger set, distractors | the coordinator; a shift of boundaries is applied as is, adding a trigger requires writing `response`, `rubric`, `evidence_span`, `trigger_modality` |
| `FIX_QUESTION` | the wording, the labels, the intent of the sample | the coordinator, with a revision of the rubric |
| `CRITICAL_FAIL` | cannot be fixed, or repair is abandoned: `status: rejected` | the coordinator; retain the record for audit |

**The mapping of checklist items to verdicts** (the default value; a reviewer may justify another):

| Item | Verdict on a hit |
|---|---|
| 2.2 the answer is possible earlier than `t_start` | `FIX_INTERVALS` |
| 2.3 the answer was available before `question_time` | `FIX_QUESTION` — the axis changes, not the window; derived from the semi-blind reviewer's `scans` |
| 2.4 the window can be narrowed | `FIX_INTERVALS`, and only if the empty part is large |
| 2.5 the answer is spoken inside the window or within 10 s after | `CRITICAL_FAIL` for `L2`/`L3`, `PASS` for `L1` |
| 3.1 an uncovered candidate for a firing | `FIX_INTERVALS` (add a trigger or a distractor) or `FIX_QUESTION` if the wording is fixed |
| 3.2 an inconsistent criterion | `FIX_QUESTION` |
| 4.8 the question rests on the topic rather than on the screen | `FIX_QUESTION` |
| 4.2 the answer was given without the video at all | set `blind_solved: true`; complete review and exclude it from primary tasks, but reject only for an independent defect or abandoned work |
| 4.3 the video was recognised | `FIX_QUESTION` plus a flag: another video may be needed |
| 4.7 the question is not solvable even from the full material | `CRITICAL_FAIL` |
| 5.x, 6.x | `FIX_QUESTION` |
| 7.3 `reasoning_level` is inflated | `FIX_QUESTION`; check **before** 2.5, whose verdict depends on the level |
| 7.4 `depends_on` is not confirmed by the rubric | `FIX_QUESTION` |
| 7.5 `evidence_span` is not on the last piece of evidence | `FIX_QUESTION` — the axis changes |
| 8.2 the reference describes something other than what is in the frame | `FIX_INTERVALS` |
| 8.3 the reference contradicts the windows | `CRITICAL_FAIL` if it confirms 2.5; otherwise `FIX_INTERVALS` |

---

## What has to be built for this

None of steps 3–4 is automated at present. In order of usefulness:

1. `tools/sample_frames.py` — cutting frames by interval and step with names by timecode, so that
   the reviewer does not have to assemble `ffmpeg` by hand and so that the frames are cached
   between subagents.
2. Sparse sampling by scenes plus a grid in `make_bundle.py` (see step 0).
3. Launch templates: the proposer by chapters, the reviewer by question, the merging of verdicts.
4. `tools/run_shortcut_baselines.py` — checklist group 4, a separate pipeline: it is not about the
   quality of the annotation but about whether the sample measures anything at all.
5. `schema/review.schema.json` plus a completeness check of the review on the coordinator's side.

## What to measure the pipeline itself with

Step 6 exists to find what the automation missed, but "finding" has to be turned into a count,
otherwise there will be nothing to improve the pipeline by. Three quantities worth counting from
the very first run:

- how many errors only the human found — that is what replenishes the checklist;
- how many of the reviewers' proposals the human rejected — the false alarm rate; it is exactly
  what decides whether selective acceptance can be adopted;
- how many items were marked `ok` but turned out to be broken — the most expensive category.

A cheap way to check the pipeline before it spoils anything: run it on the already annotated ten
samples of the pilot, some of whose errors are known, and see which of them it finds.
