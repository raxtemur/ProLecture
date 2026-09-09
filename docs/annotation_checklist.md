# Annotation verification checklist

A living document: it grows every time a new class of error is discovered.

**The numbering is frozen.** New items are added at the end of their group; existing ones
are not renumbered. An item that has to be removed is marked as withdrawn, but its number
and slug stay taken — otherwise saved reviews will start reading as reviews of other
items. The details are in "How items are addressed".

## Why it exists

A benchmark sample is a standing instruction (the question) issued at the moment
`question_time`, plus one or more **answer windows** `[t_start, t_end)`. The model must
speak inside a window and stay silent outside it. Everything else in the annotation exists
so that this requirement is satisfiable and unambiguous.

Hence the main principle of the checking:

> An annotation error is any situation in which **a model reasoning correctly is
> punished** and one reasoning incorrectly is rewarded.

Such situations almost never look like an error in the JSON. The file passes the schema,
the numbers are consistent, and the sample is broken all the same. So there are three
levels of checking.

## The three levels of checking

| Tag | Who checks | What it can catch |
|---|---|---|
| `[A]` | `tools/validate_samples.py` | everything derivable from the numbers in the file itself |
| `[M]` | a verifier model: a VLM over frames, an LLM over the transcript | whether the annotation matches the content of the video |
| `[H]` | a human | what the fix cycle did not close by itself |

**"`[H]` is empty" and "every sample is accepted by a human" are not a contradiction:
these are two different ways a human enters.**

- *By checklist item* — none at the moment. Every item that used to require a human has
  been reduced either to arithmetic or to a question a subagent answers from the text of
  the sample. So no item blocks an automatic run while waiting for a human.
- *By exhaustion of the cycle* — escalation: `CRITICAL_FAIL`, running past the iteration
  limit, oscillation, a persistent disagreement between reviewers. That is what `[H]` as a
  level actually contains.
- *Acceptance* — step 6 of the pipeline, applied to everything while the pipeline is being
  calibrated. It is not tied to items at all: the human looks at the whole sample and
  thereby checks **the checklist itself** rather than the sample against the checklist. Its
  by-product is new items.

The first may grow over time, the second will always remain, the third shrinks to spot
checks. The details are in "The order of application" and in
[docs/annotation_pipeline.md](annotation_pipeline.md), step 6.

The `[M]` items are the specification for the verifier; until it is written they are
checked by hand, and it is they that take most of the annotation time.

Within each group the items run in the order `[A]` → `[M]` → `[H]`: the cheap and
automatic ones first, the ones needing a human at the end.

## Why `t_ideal` means nothing

The field is in the schema, but it should not be relied on, and that is a deliberate
decision rather than something left unfinished.

`t_ideal` was conceived as the peak of the metric — the moment an answer at which is
rewarded most. To set it, one has to know **how long the required work will take the
model**: reading four bars off a graph takes longer than hearing a phrase. We do not know
that and cannot know it in advance, and guessing would mean writing an assumption about
the speed of one particular model into the annotation. Worse, a peak placed early rewards
whoever blurted out a guess, and one placed late penalises whoever answered straight away,
even though sooner is always better.

Hence: **latency is measured from `t_start`**, and `t_start` is defined as the moment at
which a model reasoning instantaneously could already have answered. From that follows the
rule `t_start ≥ evidence_span[0]` (1.1) — the left boundary must coincide with the
appearance of the evidence, otherwise the origin of the measurement is shifted.

`t_ideal` remains in the schema as `t_start + 1` and is filled in mechanically. If it is
ever genuinely needed — after generation latency has been measured on real models — the
definition will have to be written afresh.

## How items are addressed

Every item has two names: a **number** (`2.2`) and a **slug**
(`answer-possible-before-start`). The number is for humans, the slug is for machines, and
that is not a matter of taste.

The numbering changes: in a single session group 4 moved wholesale — the former 4.7 became
4.3 and the former 4.3 became 4.6. A review saved under the key `"4.6"` reads, after such a
reshuffle, as a review of **a different** item, silently and irreversibly. So the review
contract ([../schema/review.py](../schema/review.py)) holds the slugs, while the numbers
stay here.

Two rules follow. Items may be added anywhere — saved reviews will survive it. They must
not be deleted: the slug of a deleted item stays in `Item` with a note, otherwise old
reviews stop being readable.

The agreement between the checklist and the contract is checked automatically, in both
directions:

```bash
/home/user/conda/bin/python3 schema/review.py
```

An item that is in the contract and not here is a requirement on the reviewer that they
will never read anywhere; the converse is an item nobody will report on.

The *Frequency* line shows whether an item ever fired on real annotation. Items that have
never fired were added by reasoning and may turn out to be unnecessary — they are not the
ones to spend time on first.

## Notation

| Field | Meaning |
|---|---|
| `question_time` | the moment the question is issued; before it the model does not know the question |
| `[t_start, t_end)` | the answer window: an answer counts only inside it |
| `t_ideal` | a service field, `t_start + 1`; latency is measured from `t_start`, see "Why `t_ideal` means nothing" |
| `evidence_span` | where in the video the **latest** piece of evidence needed for the answer lies; not the corroboration — that is in `provenance.evidence` (1.9) |
| `trigger_modality` | which modality the signal comes from: `visual` / `sound` / `speech` |


## Viewing operations

The `[M]` items are carried out by a subagent with a budget: **no more than ~50 images per
question checked**. The common order is progressive:

| Operation | What it is | Cost |
|---|---|---|
| **reading the transcript `[a, b]`** | every available line with its timecode | cheap, taken in full in any quantity |
| **reading the screen description `[a, b]`** | the boundary-clipped records from `description.jsonl`, read in full over the stretch rather than searched; a model-made text, not evidence | cheap, taken before opening frames |
| **scene-frame viewing `[a, b]`** | existing content-selected frames from `bundle.json["frames"]`, produced by `detect_scenes.py` | moderate |
| **dense viewing `[a, b]`** | an on-demand grid requested with `--dense`; start at 1 fps (`--step 1`) | expensive: 50 frames cover at most 50 s at 1 fps |

Hence the working rule: **description first, existing scene frames second, targeted dense
viewing last.** The coordinator prepares only the clipped description and existing scene
frames. It does not pre-fill a uniform grid or dense target/evidence intervals. A reviewer
uses `--dense` only after the cheaper material identifies a suspicious stretch.

The description was produced by a model and cannot prove a visual fact. A positive visual
claim must still cite a real scene frame or an on-demand dense frame in `looked_at`.
`probe_text` receives neither the visual description nor frames; `probe_frame` receives
exactly its one frozen frame and cannot call `--dense`.

---
## 1. Formal integrity of the file

The group is entirely automatic and entirely implemented. It is also the specification of
`tools/validate_samples.py`: every check in the code must have an item here, and vice
versa (see 9.4).

- `[A]` **1.1. Answer window geometry.** · `window-geometry`

  *Statement.* The window is not inverted (`t_start < t_end`), does not run past the
  duration of the video, does not overlap a neighbouring window of the same sample,
  `t_ideal` lies inside its own window, and `t_start` is not earlier than `question_time`
  — otherwise the start of the window is unreachable: the model does not know the question
  yet. Separately for `evidence_span`: non-empty, inside the video, beginning before
  `t_end` (otherwise the evidence appears after the window closes and a correct answer is
  unreachable in principle).

  **The window does not open before the evidence: `t_start ≥ evidence_span[0]`.** Between
  the opening of the window and the appearance of the evidence there would be a zone where
  an answer counts while there is nothing yet to answer from — that is, guessing would
  count. A separate rule is needed because its neighbours cannot see this: 2.2 catches the
  converse (the answer became possible **earlier** than `t_start`), and
  `evidence_span[0] < t_end` guards the right edge.

  The right edge is guarded by `S-35`: `evidence_span[1] ≤ t_end`. By the definition of the
  field (1.9) what lies there is the **last** piece of evidence needed for the answer; were
  it to appear after the window closes, the reference answer would be unreachable inside
  the window.

  On the pilot the left rule fired straight away on 13 triggers out of 25: the windows had
  been set on round numbers while the line carrying the evidence began a second or three
  later. All of them were aligned to the evidence.

  **What this pair of rules does not do.** Together they mean "the evidence began to appear
  no later than the opening of the window and finished no later than its closing", and not
  at all "the evidence lies inside the window": containment would require the opposite
  inequality on the left. As soon as the evidence moves entirely to the left of the window
  — which is legitimate both for `post` (the material went by before the question was
  issued) and wherever the information was accumulated before the formal condition in the
  text of the question fired — both inequalities hold trivially and check nothing.

  So **whether the `t_start` boundary itself is right is not checked by the machine and
  cannot be**: that would require the moment the formal condition fires, and the annotation
  does not store it. That is the reviewer's work — items 2.4 ("the window can be tightened")
  and 3.3 ("the event does not begin earlier than its window"). Introducing a separate
  field for a machine check was tried and abandoned: it would almost always coincide with
  `t_start`, that is, the rule would degenerate into "the window opens when it opens", while
  the annotator would gain one more thing to get wrong.

  **Exact coincidence is not required — a little slack is better than flush.** The rule is
  one-sided: `t_start` is not earlier than the evidence. Keeping it to the second is
  unnecessary and harmful: annotating boundaries from frames is itself accurate to about a
  second, an animation "arrives" smoothly, and too early a left boundary catches the moment
  when the object is still being drawn. Slack of one to three seconds is normal; it is
  checked by eye (2.2 and 2.4), not by arithmetic. Symmetrically for `t_end`: better to let
  the model finish the phrase than to cut the window off exactly on the last word.

  *Checking algorithm.* Arithmetic over the fields of the sample.

  *Status.* Implemented; the left boundary against the evidence is `S-29`, the right one is
  `S-35`.

  *Frequency.* Regularly, mostly as overlapping windows after a boundary was moved by hand.

- ~~1.2. Distractor geometry~~ · `distractor-geometry` — **retired 2026-09-07** together with the
  `distractor_windows` field; the reason is in the note that replaced group 6. The rules `S-14`,
  `S-15`, `S-16`, `S-31` and `S-37` (a decoy on a window boundary, with its ten-second warning
  under 2.5) were removed from the validator; `S-04` with 1.5 and `S-26` with 6.3. The name stays in the contract so
  that the reviews saved under checklist 2026-08-24 still read.

- `[A]` **1.3. Basic integrity of the sample.** · `sample-integrity`

  *Statement.* There is at least one required trigger; the `idx` values of the triggers run
  consecutively from zero (otherwise `depends_on` refers somewhere other than it appears
  to); the order of `idx` matches the chronological one, that is, `t_start` is
  non-decreasing; `question_time` is not greater than the duration; `id` values are unique
  across the whole set.

  The requirement of chronological order is not cosmetic. The `temporal_rel` axis is
  derived from the evidence of the **first and last** required triggers, and they are taken
  by their place in the list. Reordered triggers give an axis derived from the wrong
  windows.

  *Checking algorithm.* Arithmetic and sets over the fields.

  *Status.* Implemented.

  *Frequency.* Caught: inserting a new trigger in the middle of the list without
  renumbering. A violation of the order used to be diagnosed as "the window overlaps the
  previous one" — a message correct as a matter of fact but misleading.

- `[A]` **1.4. `depends_on` points strictly backwards.** · `depends-on-backwards`

  *Statement.* A dependency may refer only to a trigger with a smaller `idx`. A forward
  reference or a self-reference makes the chain uncomputable.

  *Checking algorithm.* Comparison of indices.

  *Status.* Implemented. The substantive side of the field is in 7.4.

  *Frequency.* Never.

- ~~1.5. A multi-trigger sample has at least one distractor~~ · `multitrigger-has-distractor` —
  **retired 2026-09-07**. Talking non-stop is punished by the false-alarm rate and by the number
  of answers per sample (plan §3, item 3), and both are always computed; a spammer lands in any
  interval, so an annotated one added nothing. What the rule did do was make the proposer
  invent a distractor for every multi-trigger sample — and, read as "for every sample", for 19
  of the 44: a gap `[question_time, t_start)` whose end betrayed `t_start` to the semi-blind
  reviewer (see 2.2). Rule `S-04` removed.

- `[A]` **1.6. `video.duration` is cross-checked against `bundle.json`.** · `duration-matches-bundle`

  *Statement.* The duration is duplicated in the annotation for the sake of the file being
  self-contained, and therefore diverges from the truth if the video is re-downloaded.
  Every boundary check rests on it, so a divergence makes them all meaningless.

  *Checking algorithm.* Comparison against `bundle.json` with a tolerance of a second.

  *Status.* Implemented.

  *Frequency.* Never — the check was added as insurance before the second video.

- `[A]` **1.7. `audio_dependency_claim` does not contradict the trigger modalities.** · `claim-matches-modalities`

  *Statement.* The annotator's opinion about the role of the audio cannot be "the audio is
  unnecessary" if every trigger is spoken, and cannot be "the audio is required" if there is
  neither speech nor sound among the modalities. This is a check of the internal
  consistency of an opinion, not a measurement (the measurement is in 4.5).

  *Checking algorithm.* Comparing `audio_dependency_claim` against the union of
  `trigger_modality`.

  *Status.* Implemented.

  *Frequency.* Never.

- `[A]` **1.8. The file conforms to the JSON schema.** · `json-schema`

  *Statement.* `schema/sample.schema.json`, `additionalProperties: false` at every level: a
  typo in a field name must be an error rather than a silently ignored key.

  *Checking algorithm.* Schema validation before all the semantic checks.

  *Status.* Implemented.

  *Frequency.* Regularly, as typos in field names.

- `[A]` **1.9. Every trigger has an `evidence_span`.** · `evidence-span-present`

  *Statement.* The field states where the latest piece of evidence needed for the answer
  lies, and the `temporal_rel` axis is derived from it (7.1). If the field were optional and
  the answer window were substituted for it when absent, the derivation of the axis would
  degenerate into comparing `question_time` with `t_start`, that is, it would measure
  exactly what must not be measured.

  The practical consequence of such a substitution had already appeared: an unfilled field
  gave the right axis for `pre` and `at` (where the evidence and the window nearly coincide)
  and **the wrong one** for `post` — there the evidence lies before the window, and without
  the field `post` is indistinguishable from `at`. That is, the substitution worked exactly
  up to the first `post` question.

  *Checking algorithm.* The field is in the trigger schema's `required`; there is no
  substitution in the validator — if the field is absent, the schema fails.

  **How to annotate the span for different modalities.** For speech it is the interval of
  the line in which the evidence is finished: "I will share one at the end" — `[37.2, 40.5]`.
  For a picture it runs from its appearance to the end of its availability inside the
  window: the graph stays on screen, and as long as it is there the evidence is available.
  The difference matters for deriving the axis (7.1): if visual evidence is treated as
  instantaneous, a question asked five seconds after the graph appears comes out as `post` —
  "answer from memory" — even though the graph is still in front of the model's eyes and it
  is simply looking at it.

  **Evidence is not corroboration.** `evidence_span` holds the material from which the
  answer **follows by the moment `t_end`**; what we use to establish that the reference
  answer is correct at all lives separately, in `provenance.evidence`, where a reference may
  point at a part of the video after the window or at an external computation entirely
  (`type: other`). The distinction shows on two kinds of task. For `predict` the
  corroboration arrives after the window by construction: in `q08` the window is
  `[1259, 1283)`, while Betty and "the brain as a model of language" are at 1336.6 and
  1444.1, and they are in `provenance`. For `counterfact` there is no corroboration in the
  video at all: the author never speaks the answer to "what would happen if", otherwise it
  would not be a counterfactual. Putting the corroboration into `evidence_span` is not
  allowed — `S-35` guards it there, and the corroboration would break it.

  *Status.* Implemented. The pilot has been **filled in for real**: for 24 triggers out of
  25 the span points at a specific line or at the interval a picture is visible for. The
  exception is `q07`, trigger 1: there the evidence appears at the start of the window and
  remains visible to its end, so the span coincided with the window on the merits rather
  than out of laziness. Previously 24 out of 25 were copies of the window, which made the
  derivation of the axis degenerate into comparing `question_time` with `t_start`.

  A by-product of filling it in: on 13 triggers out of 25 it turned out that the window
  opened a second or three before the evidence — aligned under `S-29`.

  *Frequency.* Discovered on the pilot on 24 triggers out of 25 at once; closed.

- `[A]` **1.10. A trigger does not rest on `sound` alone.** · `sound-only-trigger`

  *Statement.* `trigger_modality` has the value `sound`, but there is nothing to check it
  with: `probe_text` reads the **transcript**, that is, the text of the speech rather than
  the sound; `probe_vision` looks at frames. A trigger for which `sound` is the only
  modality is checked by no probe, and its `visiononly_solved = false` means nothing: the
  `audio_dependency` label would be derived from a measurement that never happened.

  The value was deliberately not removed from the schema: sound triggers can be meaningful
  (a change of musical theme, a characteristic click), and when a sound probe appears the
  ban will be lifted in one line. Until then such a trigger must rest on something else as
  well.

  *Checking algorithm.* `trigger_modality == ["sound"]` is an error. Combinations of `sound`
  with `speech` or `visual` are legitimate.

  *Status.* Implemented, `S-28`.

  *Frequency.* Never on the pilot — `sound` was not used.

- `[A]` **1.11. The answer window is no shorter than five seconds.** · `window-not-too-narrow`

  *Statement.* The width of a window is set by the content of the video, and the content has
  no reason to coincide with how long a model spends on its answer. A model in streaming
  thinks and generates for **seconds**; on a nine-second window with `ω = 0` a five-second
  latency eats more than half the area under the curve, and on a five-second one a correct
  answer simply does not make it in time. PAUC then measures generation speed rather than
  understanding — that is, exactly the substitution the criterion of the whole annotation is
  written to forbid.

  Five seconds is not a measured quantity but the first deliberate constraint. The exact
  value will be derived from measuring the end-to-end latency of one model (Phase 4); until
  then the floor exists so that narrow windows do not appear silently.

  *Checking algorithm.* `t_end - t_start >= 5.0` on every trigger, required and optional
  alike.

  *Status.* Implemented, `S-36`.

  *Frequency.* Not caught on the pilot: the narrowest window is 9.0 s (`q06`, idx 3). Nine
  of the 25 windows are shorter than 13 s, so there is not much room.

---
## 2. Answer window boundaries

The most expensive group. It helps to keep in mind which boundary exactly has moved, and in
which direction:

```
        0                question_time            t_start        t_end   +10 s
        |                      |                      |            |       |
        |<------- 2.3 -------->|<------- 2.2 -------->|<-- 2.4 --->|<-2.5->|
        | the answer was       | the answer is        | the window | the   |
        | available before     | already possible     | can be     | answer|
        | the question →       | here → the window    | tightened  | is    |
        | this is not a pre    | opened late          |            | spoken|
```

Most of the errors here have one common cause: **the window is set by the speech while the
information appears on screen earlier.** The author regularly shows a table or the values
tens of seconds before speaking them aloud, and then re-animates them to fit the words.
Checking the frames around the line does not see this — that is precisely where the repeat
animation is running, and the picture looks incomplete.

- `[A]` **2.1. A boundary shared by two neighbouring windows does not cut a line in half.** · `shared-boundary-not-mid-cue`

  *Statement.* The item is narrow and its limits matter. It is **only** about a moment that
  simultaneously closes one window of a sample and opens the next. An answer given in the
  first second of a phrase that falls on such a join is counted into the previous window
  and judged against the wrong rubric.

  It does not apply to single boundaries: outside a window an answer does not count anyway,
  and there is no "wrong rubric" there.

  *Checking algorithm.* Collect the moments where the `t_end` of one trigger equals the
  `t_start` of the next. For each, check whether it lies strictly inside a transcript line.
  On a hit, propose the nearest line boundary, but do **not** require the move
  automatically: the move competes with 2.2 and 2.4, and a human decides.

  ⚠ *A warning against a naive implementation.* It is tempting to state the rule more
  broadly — "window boundaries must fall into the pauses between lines" — and that is a
  trap. The subtitles of educational videos are nearly continuous: on the pilot video the
  median gap between neighbouring lines is **zero**, and only 193 of the 527 joins have a
  pause longer than 0.3 s. A broad rule would have fired on 38 of the 50 boundaries,
  including the obviously correct ones, and would have forced windows to be moved in direct
  violation of 2.2. There is currently one shared boundary on the pilot — in `q06` at
  1851.0 — and it does not cut a line.

  *Status.* Implemented, `S-33`: the rule is narrow — only the **shared** boundaries of
  neighbouring windows are checked, where an answer really can drift into the wrong rubric.

  *Frequency.* Caught once, on a shared boundary of neighbouring windows; a second time in
  `q07`, where the boundary 957.0 lay inside a line. Cured with a gap between the windows
  instead of a shared boundary.

- `[M]` **2.2. The answer becomes possible earlier than `t_start`.** · `answer-possible-before-start`

  *Statement.* The key check of the whole checklist. By the moment `t_start` the information
  for the answer must suffice **for the first time**. If it was available earlier, then a
  model that answered as soon as it could gets a false-positive penalty — that is, the
  annotation punishes exactly the behaviour the benchmark is supposed to reward.

  Sufficiency is judged from everything the model has seen and heard since the start of the
  video, not from the current frame alone: if the numbers needed were shown ten minutes ago
  and what is on screen now is only a reminder, the count runs from the first showing.

  The commonest and least obvious variety is **the same information in another form**. The
  question is phrased through a visual condition ("when the graph appears …"), the condition
  honestly has not occurred, and the data the answer is computed from are already on screen
  in another representation: as a table, a diagram, the captions of a previous animation. A
  checker looking for the condition to be met will find nothing; a checker who tries to
  answer will answer.

  *Checking algorithm.* Three stages, two of them by agents who do not know the reference
  answer, one by an agent who does — and each is used where it is not biased. The
  vocabulary: *blind* is the answer before any material (step 0, `prior_answer`);
  *semi-blind* is an agent with material up to `until` and neither answer, nor rubric, nor
  `t_start`; *sighted* is the full reviewer with the rubric.

  **Stage A — the semi-blind trajectory.** The video is split into stretches, one per
  **every** window, required and optional alike: stretch `k` runs from the `t_end` of the
  previous window to the `t_end` of its own. The reviewer receives the transcript, the
  description of the video track and the scene frames up to the upper bound of the
  stretch, reads the description of the stretch **in full** (not searches it), and at
  **every** moment where the state of the screen or the speech relevant to the task
  changed writes a complete answer from what is available up to that moment — the
  `Candidate` records of the contract, the last one at the end of the stretch. They do not
  answer "could I answer?" — for a multi-window sample that question is meaningless. They
  answer at every point, and whether an answer is good enough is not theirs to decide: a
  confidently wrong answer that settled early looks exactly like a right one. Points they
  call sufficient, and any point where the description is ambiguous (the middle of an
  animation), are confirmed on real frames.

  **Adjudication.** The coordinator, who has the rubric, checks every answer of the
  trajectory item by item and takes the first one that meets all the required items as
  `t_val_A` (the table format is in `prompts/coordinator.md`). The reviewer's own `t_val`
  is a self-report and has no status. Comparison: `t_val_A[k] < t_start[k]` is a hit.

  **Stage B — the sighted proposal.** The full reviewer, who knows the answer, may name
  `t_s`: the first moment from which, in their view, the rubric is satisfiable, with the
  frame that shows it. They used to be forbidden the left boundary outright because of a
  known bias — knowing the answer, they "recognise" it in a half-drawn frame and pull the
  boundary left. The ban is lifted because a check now follows.

  **Stage C — the semi-blind verification.** If `t_s < t_val_A`, a fresh semi-blind probe
  (`probe_verify`) receives the task **without its when-clause** and the material exactly
  up to `t_s`, and answers. Rubric met → `t_val = t_s`: the sighted reviewer found an
  earlier form of the information that stage A walked past, and it objectively exists.
  Not met → `t_val = t_val_A`: the sighted reviewer recognised the answer in a half-frame.
  If `t_s ≥ t_val_A`, stage C is not needed. An early **correct** answer of an evaluated
  model at `t_m < t_start` is a ready-made `t_s`: stage B is skipped and stage C runs at
  `t_m` directly.

  Nothing in the material names the window boundaries: the upper bound of the stretch is
  the `until` field in the `limits.json` of the workspace, and `t_start`, which is exactly
  what is being checked, is shown to nobody who is semi-blind. Hence the "semi-": they know
  the end of the stretch from the structure of the task, and not the quantity under test.
  **Nothing else may be passed to them either.** Until 2026-09-07 the declared distractor
  windows were handed over as exclusion zones, and their `t_end` coincided with `t_start`
  in 23 samples of 44; `t_val` landed within a second after that end in 19 of the 23 —
  three different models, the same behaviour. The check had become a comparison of two
  numbers the annotation itself supplied. The field is gone, and with it the leak.

  Why a trajectory and not "the first moment you find sufficient": the pilot reviewers
  wrote "supplies all four concrete values and signs" about a moment they then excluded,
  and nobody read the phrase as "the rubric is met". A full answer per point makes the
  hit visible to whoever has the rubric. The variety "the same information in another
  form" is caught by construction: the reviewer is not looking for the condition of the
  question to occur, they are answering.

  The split into stretches is there for coverage. A single prefix up to the `t_start` of the
  first window checks the left boundary of that window only; on the nine-window `q06` the
  other eight are checked by nobody.

  "On the merits" here is a qualitative judgement against the rubric rather than a score: a
  numeric scale is needed by the metric that evaluates models, and at the annotation stage it
  would only create an appearance of precision.

  On budget: the transcript in full (free), the description of the stretch in full (about
  8 KB per 20 s of gap on the pilot videos, free), the scene frames of the stretch (2–10),
  and a dense pass at 1 fps only to confirm a chosen moment or to take apart the middle of
  an animation. The description was made by a model: a number or a verbatim text is
  confirmed on a frame before it goes into the review.

  *What to do on a hit.* First measure the gap `t_start − t_val` and ask what the
  when-clause of the question contributes to the answer.

  **A gap of up to 10 s** is a boundary error, not a design error: move `t_start` to
  `t_val` together with `evidence_span`, re-review the touched window with `full_window`,
  and that is all. The constant is the same as the slack in 2.5 — the scale of a streaming
  model's generation latency; two constants for one scale would be a second thing to
  calibrate. A sub-second gap the tooling cannot resolve (frames are cut at whole seconds)
  is recorded in the adjudication table and is not a hit.

  **A larger gap is a question about the when-clause.** Test: which rubric items become
  satisfiable only once the event named in the clause has occurred? If some do, the clause
  is **substantive**: keep the window and add an **optional** trigger for the early form —
  then both an early answer and silence until the main window are correct. If none do, the
  clause is **empty** — an anchor for the timer, not part of the task — and it gives no
  right to `pre`: a model that answers before the anchor is right, not early. The remedy is
  then a ladder, taken strictly in this order, after one preliminary step:

  0. **Referents.** Re-read the question without its when-part and check that every
     referent ("the blue target function", "the controlling coefficient") resolves to
     exactly one object on the material up to `question_time`. A clause that contributes
     no rubric item may still be the only thing that fixes what the question is about —
     item 5.3 checks the same property from the sighted side. If a referent does not
     resolve, the clause is not dropped but **replaced by a discriminator**: by preference a
     mathematical property that singles the object out ("the coefficient that controls the
     tangent slope at x=0"), which depends on no frame; the state at the moment of the
     question ("now on the screen") when no such property exists; a colour or the appearance
     of a symbol last of all, since that is a when-clause under another name.

     The same step asks a second question: does the clause keep the **trigger unique**? A
     question without a when-clause names a *state*, and if that state recurs later in the
     video — the derivative column beside the cosine again at 400 and 544 — every recurrence
     is an uncovered firing (3.1). Then the clause is not dropped either: it is narrowed to a
     time qualifier that holds throughout the window and fails afterwards ("while the
     quadratic coefficient is still displayed as free to change"). "Contributes no rubric
     item" is necessary for dropping a clause, not sufficient.
  1. **Open an early window on the evidence; the showing stays the required one.** Add an
     **optional** trigger `[t_val, old t_start)`; the window of the explicit showing stays
     **required**. Silence until the showing and an early answer are then both correct.
     The clause is dropped or weakened (step 0) just enough that the wording no longer
     forbids the early answer. Make the early window the required one only when the showing
     is not a separate event worth a window of its own. If `t_val ≥ question_time` this is
     the whole fix and the sample stays `pre`.

     Two mechanics of the cut, both missed five times in one round. **Both windows get a
     fresh `evidence_span`**: the early window's from `t_val`, the required window's on the
     last piece of real evidence — never on the cut itself. The cut is a moment of the answer
     window, not of the evidence, and an `evidence_span` ending at its own `t_start` is the
     signature of the mistake (7.5). And **the two windows do not share a boundary**: 2.1
     forbids a join inside a transcript line, so the early window closes at the start of the
     line the old `t_start` falls in, and the gap between them is that line — 0.1 s or 1.3 s,
     whatever it measures, not a fixed half-second.
  2. **If `t_val < question_time` (a hit of 2.3 as well):** move `question_time` back to
     `t_val` when every referent of the wording has been introduced by then — the sample
     stays `pre`. Otherwise the early optional window opens at `question_time`, the required
     window's `evidence_span` stays on the real evidence, and `temporal_rel` is derived by
     the validator as `at` or `post`. That is an honest label, not a demotion: a `pre` a
     model may ignore with impunity measures nothing.
  3. **Reject** only when after step 2 the sample measures nothing.

  On every step `reasoning_level` is re-derived by the rule of 7.3 — the cheapest legal
  route to the full rubric, **including the right to wait for the required showing**: if
  the value is read off the screen there, the sample is `L1`, however it could have been
  derived earlier. Steps 0–2 change what the participant sees or the axis of the sample,
  so they go through `draft` and the question-version rule of the coordinator's prompt, §3
  (a fresh review cycle on the new wording). Only the two repairs that leave the wording
  alone — the 10-second move, and the optional trigger added for a **substantive** clause —
  are interval edits and need only the `full_window` re-review of the touched windows. The
  ladder is the coordinator's to apply; a hit reaches the human only when it ends in
  rejection.

  *Status.* Not implemented as code. In the pipeline it is the semi-blind reviewer's
  `scans[].candidates` (stage A), the full reviewer's `t_s` (stage B), the `probe_verify`
  role (stage C) and the coordinator's adjudication table; the verdict is derived by the
  coordinator, because the reviewer has no `t_start`.

  *Frequency.* Caught repeatedly, in both varieties. The commonest substantive annotation
  error. The audit of 2026-09-05 found that 7 of the 11 early correct answers of the
  evaluated model on the pilot were 2.2 hits the previous form of the check had missed.

- `[M]` **2.3. The answer was available even before `question_time`.** · `answer-available-before-question`

  *Statement.* A continuation of 2.2 to the left of the moment the question is issued, but
  the consequence is different, hence a separate item. If all the information needed went by
  **before** the question was asked, then this is not a "pre" question with waiting: the
  model is entitled to answer straight away, while the annotation expects the answer later
  and penalises timeliness.

  On the `temporal_rel` axis such a sample in fact belongs to `at` or `post` (the evidence
  is present at, or went by before, the moment the question is issued), and the fix here is
  not a move of the window but a correction of the design. The remedy is the ladder of 2.2:
  a gap `question_time − t_val` of up to 10 s is closed by moving `question_time` back to
  `t_val`, provided every referent of the wording exists by then; a larger gap means the
  when-clause is empty, and step 2 of the ladder applies — `question_time` back to `t_val`
  where the referents allow it, otherwise the window opening at `question_time`,
  `evidence_span` on the real evidence, and the label derived as `at`/`post`, with the
  level re-derived by 7.3. The result is a legitimate `at`/`post` sample, not a rejected
  one. `pre` is preferred and worth fighting for by the first two steps, but not at the
  price of a when-clause that carries no information.

  *Checking algorithm.* It requires no separate work: it is the same number `t_val` as in
  2.2, only compared against a different quantity. The semi-blind reviewer's zeroth stretch
  begins **at zero** rather than at `question_time` — otherwise the material before the
  question was issued simply never reaches the reviewer and there is nothing to check with.
  After that it is arithmetic:

  | Condition | Conclusion |
  |---|---|
  | `t_val[0] < question_time` | 2.3 fires |
  | `question_time ≤ t_val[0] < t_start[0]` | 2.2 fires |
  | `t_val[0] ≥ t_start[0]` | both items pass |

  *Status.* Not implemented as code. Derived by the coordinator from the adjudicated
  `t_val` of the first stretch (stage A of 2.2).

  *Frequency.* First checked systematically in the round of 2026-09-07: 8 hits of 18 on the
  2017 video, 1 of 16 on the 2026 video. Almost every hit was an empty when-clause over
  data shown minutes earlier — the "same information in another form" variety of 2.2.

- `[M]` **2.4. The window can be tightened.** · `window-can-be-tightened`

  *Statement.* A soft item: inside the window an answer must be possible throughout. On the
  left the window is sometimes open while the object is still being drawn (manim animations
  last 1–3 s, and an intermediate frame looks plausible but is incomplete); on the right,
  after the object has left the screen and there is nothing left to confirm the answer with.

  Slack of one or two seconds does not break the picture and is not worth a fix. It is an
  error when the empty part of the window is large: the sample then quietly changes what it
  tests, for example from perception to memory.

  For a question explicitly anchored to a state at its first appearance, later animation does
  not make the answer unavailable: a streaming model has already observed that state and may
  finish generating from it. The mandatory minimum window exists precisely to absorb generation
  latency. Do not tighten such a window below the legal minimum merely because the current frame
  advances while the answer is being generated; tighten only when the question asks for the
  current state or the earlier state was never fully observable.

  *Checking algorithm.* Dense viewing and the transcript of `[t_start, t_end]`. Determine the
  sub-interval over which the answer really does follow, and propose tightening the window to
  it.

  *Status.* The work of the per-window reviewer. Verdict `FIX_INTERVALS`, and only if the
  empty part is large.

  *Frequency.* Caught on both sides. Lower priority than 2.2, 2.3 and 2.5.

- `[M]` **2.5. The author speaks the answer inside the window or right after it.** · `author-says-answer-in-window`

  *Statement.* If the answer is spoken by the video soon after the window opens, the task
  degenerates: the model has no need to reason, repeating what it heard is enough. A level of
  `L2`/`L3` then effectively drops to an `L1` alarm, and the sample stops measuring what it
  was created for.

  Simply moving `t_end` back does not cure this. A model in streaming spends several seconds
  on its answer, and in that time the next chunk of the stream will bring it the author's
  answer: formally it answered inside the window, in fact it copied. So what is checked is
  not the window but the window plus slack, and the result is binary.

  **A hedge in the text of the question does not cure it either.** The temptation is great:
  add "be in time before the author tells it himself" and declare the model warned. But a
  warning does not change what is being measured. Between "the answer became possible" and
  "the author spoke the answer" lies a fixed stretch of video; if it is short, victory goes to
  whoever generates faster rather than to whoever reasons better. A model that thought for ten
  seconds and answered correctly loses to a model that blurted out a guess at once — that is,
  exactly the inversion the checklist exists to prevent.

  What actually cures it, in decreasing order of preference:

  1. move the question to a place in the video where there are minutes rather than seconds
     between the appearance of the evidence and the author's explanation;
  2. ask about something the author does not say at all — a consequence, the direction of an
     error, an application to another case;
  3. honestly accept the sample as an `L1` alarm: "report when the author names X". Then the
     window coinciding with the author's speech is a design decision rather than a defect,
     and 2.5 does not apply. That is a weakening rather than a repair: the sample starts
     measuring timeliness instead of reasoning.

  *Checking algorithm.* The transcript and dense viewing (step 1 s) of the interval
  `[t_start, t_end + 10]`. The reviewer splits the rubric in two: the items whose content
  the stream **hands over** in that interval — spoken or shown in finished form, a number,
  a term, a formula that can be repeated — and the **residue**, the items that still have
  to be worked out from them. Which items went into which half is written in the `findings`
  of the 2.5 check itself — a structured field the contract requires, not the five-line
  `notes` of the whole review; the coordinator checks the split, not the verdict alone.

  **The residue is empty** — the whole answer is in the stream. For a sample of level
  `L2`/`L3` the sample is compromised in its entirety: a verdict of the "reword the question
  or delete it" kind, by the three routes above, rather than "adjust the intervals". For
  an `L1` sample, which was designed as an alarm in the first place, this is normal and
  does not count as something to fix.

  **The residue is not empty** — the stream hands over a discriminating item (the four
  terms, say) but not the answer built from it (their sum). That is not a failure: the
  sample still measures something, only less than it was designed to. The level is
  **re-derived from the residue** by the rule of 7.3, as if the handed-over items merely
  had to be heard or read: a residue of one step of arithmetic over displayed values is
  `L2`, an empty residue would be `L1`. The verdict is `FIX_QUESTION` with the proposed
  level, and the sample keeps its windows. `reasoning_level` is one field per sample while
  2.5 is checked per window: when several windows propose different levels, the coordinator
  takes the **lowest** — by the cheapest-route rule of 7.3 the participant scores on the
  cheapest window anyway. A hedge in the wording ("show all four terms so
  that the answer cannot be guessed") does not move an item from the residue into the
  handed-over half: what counts is what the stream shows, not what the question demands.

  The ten-second rule for `t_end` in the proposer's prompt is about the **whole** answer: a
  window may close right before the author names a single ingredient, at the price of the
  level.

  *Status.* Not implemented, checked by hand.

  *Frequency.* Caught — in the "the answer is inside the window" variety. On the pilot `q03`
  was taken apart under this item: between the appearance of the formula (1585) and the
  author's explanation (1621.8) there were 36 seconds, while the window closed 0.8 s before
  his line. Converted to `L1` by the third route; the former window became a distractor.

---
## 3. The trigger set against the criterion of the question

The group answers one question: does the actual set of windows match what the wording
promises? A divergence in either direction punishes a model that reasons correctly.

Three checks: 3.1 is completeness (was a moment meeting the criterion missed), 3.2 is
precision (did anything superfluous get into the triggers), 3.3 is the start of the window
coinciding with the start of the event.

**Applicability.** The whole group applies to any sample, not only to a multi-trigger or an
exhaustive one:

- 3.2 and 3.3 work on each trigger separately, and a lone trigger is checked by them exactly
  as a ninth one is;
- 3.1 is always needed: a moment that a model will in good faith take for a firing but that
  is not marked as a trigger turns a correct answer into a false alarm — regardless of how
  many windows the sample has.

**Exhaustiveness** — questions of the form "every time when …", "keep track of which
quantities the author defines formally" — changes not the applicability of 3.1 but the
**cure**:

| Question | An uncovered candidate is found |
|---|---|
| exhaustive | add a trigger: it promised to react to every such moment |
| not exhaustive ("when for the first time …") | refine the wording so the candidate falls out of it; if the candidate is a genuine earlier form of the answer, it is a 2.2 hit and the window moves (or an optional trigger is added) |

⚠ There is no formal marker of exhaustiveness in the annotation: two samples on the pilot
are exhaustive, and they have different `act` (`monitor` and `ground`), while being
multi-trigger does not coincide with being exhaustive. The checker reads the wording and
proposes a cure based on it; the choice between "trigger" and "wording" is made by the
coordinator. Whether to introduce an explicit flag — see "Open questions"; it no longer
affects how the group works.

- `[M]` **3.1. No firing was missed.** · `no-missed-trigger`

  *Statement.* The set of triggers must cover every moment of the video that falls under the
  condition of the question. A keyword search is not enough for that: the condition is
  stated in terms of meaning, and the author expresses one and the same meaning in different
  words.

  *Checking algorithm.* Reading the transcript `[0, duration]` **line by line, in sequence**
  asking "does this line fall under the condition of the question?". Not by the occurrences
  of words found, but over every line: the transcript is cheap, and reading it whole is
  cheaper than hunting for a gap afterwards.

  For visual conditions — sparse viewing of the whole video. If a stretch is found that is
  covered by no trigger and that looks like a firing, dense viewing of its surroundings
  follows, to confirm it and pin down the moment it begins.

  The result is checked against the trigger set: everything found must be either a trigger or
  excluded by the wording of the question itself. There must be no third state — "the moment
  meets the criterion but is not in the annotation" — for it is exactly that which punishes
  the model for a correct answer.

  What cures a candidate that has been found depends on whether the question is exhaustive
  (the table in the group's preamble). The checker proposes an option based on the wording
  and does not decide for the coordinator.

  *Status.* Not implemented, checked by hand.

  *Frequency.* Caught many times, and the same sample was topped up by several independent
  passes — manual checking here is systematically unreliable. The first candidate for
  automation.

- `[M]` **3.2. Every trigger satisfies the criterion from the question.** · `trigger-matches-criterion`

  *Statement.* The reverse side of 3.1. There it was checked that nothing suitable was
  missed; here, that nothing superfluous was included. An annotator collecting firings
  imperceptibly widens the criterion: the question asks for one thing to be marked, and what
  gets into the triggers is something similar but different.

  The error is expensive in both directions. A superfluous trigger demands an answer from the
  model where the text of the question says none should be given — and silence is penalised
  as a miss. On top of that the question itself breaks: if the actual set is wider than the
  declared criterion, no model will be able to derive the rule from the wording, because the
  rule in the wording is a different one.

  *Checking algorithm.* For every trigger separately: does this moment fall under the
  criterion **literally as it is written in the question**? Not "does it look like the other
  triggers" — comparison with neighbours is exactly how a widened criterion gets smuggled in.

  If several triggers fail the check in the same way, that usually means not "remove them"
  but "the question is worded more narrowly than intended": the wording is then fixed, and
  3.1 is run again afterwards.

  *Status.* Not implemented, checked by hand.

  *Frequency.* Caught.

- `[M]` **3.3. The event does not begin earlier than its window.** · `event-not-earlier-than-window`

  *Statement.* The same as 2.2 but for events: if the trigger condition is the event itself
  (the typical case is `monitor`, but not only), the window must open at the moment it
  begins, not when it is convenient to talk about it.

  The difference from 2.2 is in the question being asked: not "what is the answer" but "when
  did the event begin". Both questions are worth asking during one and the same viewing.

  *Checking algorithm.* For every trigger, find in the transcript the first line where the
  event has already begun, and compare it with `t_start`. For visual events — dense viewing
  of `[t_start - 15, t_start]`.

  *Status.* Not implemented, checked by hand.

  *Frequency.* Caught.

- `[M]` **3.4. A task over elements that appear one by one has optional triggers on the elements.** · `elementwise-optional-triggers`

  *Statement.* When the task is a mapping over N elements that the author draws in sequence
  (three coloured pieces and the three terms they stand for), and the rubric splits into one
  item per element, the best proactive behaviour is to report each element as it appears.
  An annotation that opens the only window at "all N simultaneously complete" punishes
  exactly that behaviour: on the pilot the evaluated model narrated blue at its appearance,
  yellow at its appearance and pink at its appearance — and would have been charged two false
  alarms out of three answers. `general.md` already defines an optional window as "do not
  penalise an answer here".

  The wording "simultaneously complete" is legitimate only when the joint state is needed
  for the answer — a comparison between the elements — and not for the annotator's
  convenience.

  *Checking algorithm.* Does the rubric split by elements? Do the elements appear with gaps
  of more than 3 s between them (scene frames, then dense viewing around the appearances)?
  If both — every element whose appearance precedes the required window gets an **optional**
  trigger from its appearance to the appearance of the next element, with the rubric item(s)
  it makes answerable; the required trigger stays on the completion with the full rubric.
  Windows must not overlap and are subject to 1.11 (no shorter than five seconds) and 2.1.
  If the question insists on "simultaneously" without a reason — `FIX_QUESTION`, otherwise
  `FIX_INTERVALS`. `na` when the rubric does not split by elements.

  *Status.* Not implemented. The sample reviewer, with the frames of the assembly.

  *Frequency.* Caught once (`3d6DsjIBzJ4` q14), from the traces of the evaluated model.

---
## 4. Solvability that bypasses the video

The main risk of a benchmark built on popular educational videos: they are famous, and their
content has most likely made it into pre-training. A sample that can be answered without
watching the video measures none of what it was created for.

The group answers one question: **what is the minimum needed in order to answer?** The answer
is recorded in `validation.*` and in the derived label `audio_dependency`.

There are no runs of the models being evaluated here, no scoring judge and no "k of n"
protocol. All of that belongs to the measurement phase; at the annotation stage we ask
**direct questions of subagents** and read their answers. That is cheaper, more reproducible
and, above all, more honest: a shortcut run on one particular model measures its knowledge
rather than a property of the sample, and carrying that result into the dataset as a property
of the sample was a substitution.

The numbering of the group has been rewritten. The former 4.6 (a priori solvability) was
merged into 4.2; the former 4.7 (recognising the video) became 4.3; the former 4.3
(frozen-frame) became 4.6; 4.7 is now a new solvability check.

- `[M]` **4.1. The probe protocol.** · `probe-protocol`

  *Statement.* The requirements common to 4.2–4.7. A **probe** is a subagent that is given
  the question and the material of the video in one modality and asked **to answer**. It
  checks nothing and does not know it is taking part in a check: its answer is raw material.
  The answer is compared against the reference answer under the rubric by the coordinator,
  because only they have the reference answer.

  There are several probes per question, and they must be **different subagents** rather than
  stages of one. The reason is technical: context is one-directional. An agent that has read
  the transcript cannot "unsee" it and give an independent answer from frames alone. A series
  of answers inside one agent is legitimate only when the information increases — which is
  exactly what the semi-blind reviewer does in 2.2.

  The launch order is by increasing cost: first the free ones (4.2, 4.3), then the text one
  (4.4), then the frame ones (4.5, 4.6). Probe 4.7 is launched **only** if 4.4 and 4.5 both
  answered negatively: if one modality was already enough, solvability is proved and there is
  no reason to pay for another viewing.

  *Aggregation over windows.* A sample can have nine windows. A modality counts as sufficient
  if the probe answered correctly on **at least one required** window: a sample one of whose
  windows can be taken by a short cut is no longer measuring what it was created for.

  *Repeats.* A single answer is not a sentence, but there is no "k of n" protocol here
  either: every probe is presented once. If the probe answers diverge between iterations of
  the cycle, the disputed flag is asked again once or twice **pointwise**, and if the
  disagreement persists the sample goes to a human or is thrown out. A disagreement between
  probes is itself a signal that the question is worded vaguely.

  *Status.* Not implemented. The prompts are `docs/prompts/probe_text.md`, `probe_vision.md`,
  `probe_frame.md`, `probe_full.md`: each probe has its own, so that it does not learn from
  the prompt about material it was not given.

  *Frequency.* —

- `[M]` **4.2. The question is solvable without the video at all.** · `solvable-without-video`

  *Statement.* The answer follows from general knowledge of the subject, without a single
  frame and without the transcript. Such a sample measures neither perception nor streaming —
  it measures how well the model knows the topic.

  What has to be checked is the **substantive part** of the answer, not whether the question
  contains a requirement to wait for a moment. "I will answer, but I do not know when" is a
  question solved blind: timing without content does not measure understanding, and a
  benchmark of proactivity cannot be built on timing alone.

  The former check of a priori solvability is merged in here: if the answer follows from a
  priori knowledge, that is blind solving, and no separate item is needed.

  *Checking algorithm.* The first question to the **semi-blind reviewer**, before any viewing
  (their step 0): "answer this question on the merits, relying only on general knowledge". The
  answer goes into the review verbatim, and the coordinator compares it against the rubric and
  writes `validation.blind_solved`.

  No separate probe is needed for this: at step 0 the semi-blind reviewer is in exactly the
  state of a probe — they have not opened the material yet.

  **The verdict is set by the coordinator, not by the reviewer, and that is not a
  formality.** The semi-blind reviewer does write a line in `checks`, but it is preliminary:
  they have no reference answer, and they judge "it matched" by eye against their own answer.
  The item stands in both `ROLE_ITEMS[SEMIBLIND]` and `COORDINATOR_ITEMS` of the contract —
  the overlap is deliberate and means exactly this division.

  An answer counts as blind solving when it satisfies **two** conditions at once:

  - **correct** — it agrees with the rubric;
  - **honest** — it does not stand on assumptions about material that was not seen. An answer
    of the form "probably the screen shows the canonical example 1/2, 1/4, 1/8, 1/8, in which
    case you get 2.5" is not a solution: the statement of the problem was guessed, the answer
    was not found. That is what the `prior_answer_assumptions` field in the contract exists
    for; a non-empty list is almost always a sign that the agreement was bought with guessing.

  **A hedged answer ("X, and if not, then Y") counts only when the wrong branch would have
  cost the participant a point.** A model that named two numbers is penalised in the
  measurement for the wrong one; a reviewer who named two numbers must not be credited with
  the better of them — otherwise it is enough to list the plausible options to declare any
  sample solved blind.

  **A caveat about notation, colour or verbatim wording is not an assumption about
  content** (rule of 2026-09-07; the boundary between a guessed datum, a recalled datum and an
  unguessable colour is still under discussion). Two answers that look alike are scored differently:

  - "2.5, if the screen shows the standard example 1/2, 1/4, 1/8, 1/8" — the correctness of
    the answer depends on an assumption about the screen. A guess; `prior_answer_assumptions`
    is non-empty; `blind_solved = false`. This is the rule above, unchanged.
  - "pᵢ f′(qᵢ) = λ → q f′(q) = λ → f = λ log q; which notation and colours the screen uses
    I cannot say" — the correctness of the chain does not depend on the screen. The caveat
    concerns what the rubric may demand *beyond* the content. Here the coordinator scores
    `prior_answer` against the rubric **item by item, ignoring the caveat**: substantive
    items (a quantity, a relation, a derivation) the reviewer named count as met; items
    about the screen itself (a colour, a notation, a displayed number) that the reviewer
    did not name count as not met. Only the substantive items decide `blind_solved`: if all
    of them are met, the sample is solved blind, and a rubric item about a colour does not
    rescue it — such a sample tests colour recognition, not the science, and is not the
    `L1` alarm the benchmark wants. The verdict names in `coordinator.N.md` which items
    were met blind, so that it is visible what the sample rests on.

  The reviewer, in turn, is asked for **content, not a meta-statement about it**: "known
  only the general Lagrangian derivation" is not an answer, the derivation itself followed
  by the caveat is. A strong reviewer is an upper bound on blind solvability, and that is
  the deliberate strictness of the criterion.

  *The pilot example the rule was written for.* The semi-blind reviewer on `q01` (the
  counterfactual "swap the code words") honestly wrote: "I cannot name an exact number, I was
  given neither the code words nor the probabilities" — and then offered a conditional guess
  of 2.5 with 2.0 as an alternative. They gave themselves a `fail`. Under both rules above
  this is **not** blind solving: the statement of the problem was guessed, there are two
  branches, and all that was taken blind was the arithmetic. The sample stayed.

  *What to do on a hit.* Set `blind_solved: true`, finish the review cycle and try to anchor
  the answer to video-specific evidence under 4.8. Blind solving excludes the sample from the
  primary benchmark, but is not itself a correctness defect: an otherwise correct and complete
  sample finishes as `status: validated` and remains available as a blind baseline. Use
  `status: rejected` only for an independent defect or deliberately abandoned work.

  **Do not delete a validated blind baseline.** The plan (Phase 3) compares the share of
  blind-solvable samples on the 2026 video against the 2017 control. The selection rules are:

  ```python
  primary_tasks = status == "validated" and not blind_solved
  blind_baselines = status == "validated" and blind_solved
  invalid_samples = status == "rejected"
  ```

  *Status.* Not implemented.

  *Frequency.* Caught at the wording stage: the first revision of one of the questions turned
  out to be a pure textbook exercise, solvable without any video.

- `[M]` **4.3. Recognising the specific video.** · `video-recognized`

  *Statement.* A stronger form of 4.2: the model does not derive the answer from knowledge of
  the subject but remembers this particular video.

  It is separated from 4.2 because it is cured differently. Solvability from the subject is
  fixed by rewording the question; recognising the video is not fixed by rewording — it raises
  the question of whether the video is usable at all and of the need for a control video with
  a different release date.

  *Checking algorithm.* The second question to the semi-blind reviewer at step 0, together
  with the title of the video: "do you recognise this video and this moment; could you name
  the answer from memory of the video?" The answer is a flag in the review, not a field of the
  sample.

  *What to do on a hit.* Count it over the whole set. One recognised video is noise; a share
  of recognised ones comparable to a half is a decision about the video being unusable in its
  entirety.

  *Status.* Not implemented.

  *Frequency.* —

- `[M]` **4.4. Is the transcript alone enough.** · `transcript-enough`

  *Statement.* Whether the visual part is needed at all. A positive answer is not a flaw:
  spoken samples are legitimate, with `trigger_modality: ["speech"]`. This is an attribute
  rather than a rejection.

  *Checking algorithm.* A probe with the material "`transcript.md` up to `t_end`, not a single
  frame". The result is `validation.textonly_solved`.

  *Status.* Not implemented.

  *Frequency.* —

- `[M]` **4.5. Are the frames alone enough, and deriving `audio_dependency`.** · `frames-enough`

  *Statement.* The mirror image of the 4.4 probe; it is also the one legitimate source of the
  `audio_dependency` label.

  **A caveat to keep in mind and to carry into the limitations of the work.** Both probes read
  **text**: `probe_text` reads the human subtitles, `probe_vision` reads frames. Neither hears
  sound. So `required` means "the content of the speech is needed" rather than "the sound is
  needed", and it can be worked around with an ASR front end. The label is honest exactly
  within those limits, and we are not going to rename it yet — but it must not be presented as
  a measured dependence on audio. A related case where the same reasoning is taken as far as a
  ban is 1.10: a trigger whose only modality is `sound` is checked by nothing at all.

  *Checking algorithm.* A probe with the material "frames up to `t_end`, not a line of the
  transcript". The result is `validation.visiononly_solved`.

  **This probe's visual search is specified separately, and that is not a detail.**
  The `text` probe gets the whole transcript — it is free. The `vision` probe starts
  with the boundary-clipped visual description and existing scene-change frames. The
  description searches the full visual history cheaply; a positive answer is then
  verified against a real frame.

  If those sources identify a suspicious interval but do not expose a readable frame,
  the probe may call `--dense` there at 1 fps. The coordinator does not pre-sample the
  answer window or `evidence_span`: deciding where denser evidence is needed belongs to
  the probe and must be visible in its `looked_at` and `budget`.

  The actual grid is recorded in the `budget` of the review file. Without that number a
  negative answer cannot be interpreted, and when the viewing regime changes there will be
  nothing left to tell old measurements from new.

  The label is derived from the flag:

  ```
  visiononly_solved == true                        ->  unnecessary
  visiononly_solved == false and solvable == true  ->  required
  otherwise                                        ->  null
  ```

  The intermediate grade `helpful` was removed from the label: two bits cannot tell it apart,
  and we now have no numeric scale and will not have one at this stage. The annotator's opinion
  still lives in `audio_dependency_claim`, where `helpful` remains permitted — but that is an
  opinion and does not affect any conclusion.

  Note that `textonly_solved` and `visiononly_solved` can both be true **at once**. That is not
  a contradiction but the ordinary case — one and the same thing was both said and shown.

  *Status.* The probe is not implemented. **Comparing the label against the flag is
  automatic**, see 7.6: deriving the label is arithmetic, and keeping it under an `[M]` item
  was a violation of 9.4.

  *Frequency.* —

- `[M]` **4.6. Is a single frame enough.** · `single-frame-enough`

  *Statement.* The probe is given a single frame at the **middle of the window**,
  `(t_start + t_end) / 2`, with no history.

  The middle rather than `t_ideal`: the latter is set mechanically as `t_start + 1` and means
  nothing, while a frame in the first second of the window is a frame where the animation is
  often still arriving. The measurement would then answer the question "is the answer visible
  in the first second" rather than "is a single frame enough", and would be biased towards
  `false` everywhere the discriminating detail appears a little later. The middle is the most
  neutral point: by then the window has substantively opened and has not yet closed.

  A positive answer **does not reject the sample**. It says the task reduces to recognising a
  moment — and that is a legitimate class and one we need: an `alert` question is precisely
  about noticing an event in the frame. The item works as a check of **consistency** with 7.3
  and `act`:

  - `L1`, `act` = `alert` or `monitor` — a positive answer is expected, all is well;
  - `L2`/`L3` — a contradiction: connecting moments far apart, or a derivation, was declared,
    and yet a single frame sufficed. The level is inflated, and that is `FIX_QUESTION` under
    7.3.

  *Checking algorithm.* A probe with one frame per required trigger, the frame taken at
  `(t_start + t_end) / 2`. The result is `validation.frozenframe_solved`.

  *Status.* Not implemented.

  *Frequency.* —

- `[M]` **4.7. The question is solvable at all.** · `solvable-at-all`

  *Statement.* The other side of the whole group, without which it is lopsided: we carefully
  check that a question is **not** solvable by a short cut, and never check that it is solvable
  by the long one. A sample that cannot be answered even from the full material punishes every
  model equally and is useless in a benchmark.

  A full reviewer cannot check this: they know the reference answer and will therefore solve
  anything. What is needed is a probe that has not seen the reference answer.

  *Checking algorithm.* A probe with the full material up to `t_end` — the transcript and the
  frames together. It is launched only if 4.4 and 4.5 are both negative: a positive answer from
  either already proves solvability. The result is `validation.solvable`.

  Hence the filling rule, without which the field stays empty in the commonest case (the probe
  was not launched because there was no reason to):

  ```
  solvable = textonly_solved OR visiononly_solved OR <the answer of probe 4.7>
  ```

  That is, the flag is set by the coordinator and not only by the probe: success of any
  single-modality probe is already proof of solvability, and `solvable = true` is derived from
  it arithmetically. The converse does not hold: `solvable = false` is set **only** after a
  negative answer from probe 4.7, because "it was not solved from one modality" does not mean
  "it is not solvable at all". Consistency is guarded by `S-27`.

  *What to do on a hit.* `solvable == false` is a `CRITICAL_FAIL`: either the question demands
  something that is not in the video, or the rubric demands something other than what is in the
  video. It is not cured by iterating on boundaries.

  *Status.* Not implemented.

  *Frequency.* Never — the check did not exist until now.

- `[M]` **4.8. The wording of the question is anchored to the screen, not to general knowledge.** · `question-anchored-to-screen`

  *Statement.* Prevention instead of cure. A question worded through the properties of a
  specific image ("for which values of the parameter are the bars drawn") cannot be solved from
  memory of the subject, even if the subject is familiar. A question worded through the topic
  ("how does such-and-such a function behave") is solved blind as a textbook exercise, and no
  hedge in the rubric fixes that.

  *Checking algorithm.* Structural rather than substantive: name the words in the text of the
  question that point at a specific screen — objects, their position, captions, values on the
  axes. If not one is found and the question rests on the topic alone, that is a hit.

  The check does not require solving the question and is therefore not spoiled by knowing the
  reference answer: it is about the wording, not about the answer. That is what distinguishes
  it from 4.2, which catches the same defect empirically and is therefore given to the
  semi-blind reviewer.

  *Status.* Step 0 of the sample reviewer, no frames needed. Verdict `FIX_QUESTION`. It is
  cheapest to do this while the question is being written — after 4.2 fires, rewording creates
  a new question version and forces the complete review cycle to run again.

  *Frequency.* Caught.

---
## 5. Consistency of question, answer and rubric

This group is about the **participating model** — the one the benchmark will evaluate at
measurement time (the plan, §1.3: generator ≠ judge ≠ participant). It will be given **only
the `question` string**. Neither `response`, nor `rubric`, nor `question_time_note`, nor
`validation.notes` will be shown to it: the rubric is an instruction to the judge, not part of
the problem.

The checker, by contrast, sees the whole sample, and that is the entire point of the group: to
compare the criterion available to them against what the participant will get. A discrepancy
is exactly the situation the checklist was written for: the participant reasons correctly but
is penalised for a distinction they were never told about.

Items 5.2–5.4 are checked against the text of the question and the rubric, no frames needed,
so they are done by the **full** reviewer (not the semi-blind one: they have neither `response`
nor `rubric`) at step 0, before a single frame is spent. The check is cheap, and the meaning of
the expensive ones depends on it: if the rubric demands something other than what the question
asks, there is no point arguing about window boundaries.

- `[A]` **5.1. Control twins share the criteria of the rubric.** · `twins-share-rubric`

  *Statement.* Twins are two samples with the same question and a different `question_time`;
  the difference between their metrics is meant to be the price of timing. If the criteria have
  diverged, the difference measures a change in the judge's requirements.

  What must be compared is the criteria, not the bytes: the wording of the expected answer
  legitimately differs between twins.

  *Checking algorithm.* Collect the twin groups by the `twin_of` field and compare the `rubric`
  lists of the **required** triggers. An optional window that one twin has and the other lacks
  is excluded from the comparison: with `at`/`post` the answer window starts at the moment the
  question is issued, and there simply is no preceding optional window there. Along the way
  `act`, `reasoning_level` and the video are compared, and `question_time` is required to
  differ — otherwise the pair measures nothing.

  The `twin_of` link is undirected: it is enough to set it on one of the pair, the validator
  joins the group itself. A group may be larger than two.

  *Status.* Implemented: `S-23` (integrity of the link) and `S-24` (agreement of the criteria)
  in `tools/validate_samples.py`. These are the only checks for which a single sample is not
  enough, so they live in `cross_sample_checks` rather than `semantic_checks` and require the
  twins to land in the same validator run.

  *Frequency.* Caught: the twins' rubrics diverged immediately after the pair was created.

  *Additionally.* Even with matching criteria the twins differ in window width — an
  irremovable confound, to be kept in mind when reading the result.

- `[M]` **5.2. The rubric does not demand what the question did not ask for.** · `rubric-within-question`

  *Statement.* The classic desynchronisation: the question asks to name one object, the rubric
  awards points for listing two. A model that answered exactly the question asked loses a point.

  *Checking algorithm.* Go **through the items of the rubric**, not through the question: for
  each item find in the text of the question the requirement it follows from. The direction
  matters — reading from the question, a superfluous rubric item simply never catches the eye.
  Do not accept "but it is obvious from the context": the context belongs to the annotator, and
  the participating model has one line of question.

  An item with no corresponding requirement in the question is cured in one of two ways: remove
  the item or add the requirement to the question. Which one is the coordinator's decision; the
  reviewer names the item and the missing requirement.

  *Status.* Step 0 of the sample reviewer, no frames needed. Verdict `FIX_QUESTION`.

  *Frequency.* Caught.

- `[M]` **5.3. Everything that separates a right answer from a wrong one is in the question itself.** · `discriminator-in-question`

  *Statement.* The condition by which the correct answer differs from a plausible wrong one
  — an early value later refined, a similar wording used about another object, the same
  number with a different origin — is often formulated for the first time in a service
  note or in an excluding rubric item, and stays there. The model does not see it and is
  caught on a distinction it was never warned about.

  *Checking algorithm.* Take every excluding item of the rubric ("do NOT credit X") and every
  plausible wrong answer visible in the material before or beside the window, and show
  which word or phrase of the question cuts it off. If there is no such word, the model is
  penalised for a distinction it was not told about.

  Look especially carefully at the cases where **the value of the answer itself** coincides
  and the distinction rests only on its origin or on an accompanying condition. Such
  distinctions are legitimate, but only provided the origin is named in the question.

  **A rubric checks the string of the answer, not the route to it.** "Read from the screen,
  not reconstructed" is a checkable item only when reading and reconstructing produce
  different strings; when `1⁴/4!` read off the frame and `1⁴/4!` obtained by substituting
  x = 1 are the same characters, the item is dead and the leak it was meant to close stays
  open. The cure is paired and lives in the question, not in the rubric alone: put into the
  wording something that is visible only on the screen — the form of the notation, how the
  neighbouring entries are drawn — and let the rubric check that; then measure the new
  wording with a fresh blind probe rather than accept it. A rubric edit on its own either
  changes nothing or fires 5.2.

  *Status.* Step 0 of the sample reviewer, no frames needed. Verdict `FIX_QUESTION`.

  *Frequency.* Caught.

- `[M]` **5.4. The rubric does not penalise a correct detail beyond what was expected.** · `rubric-not-punishing-extra`

  *Statement.* Items of the form "the list contains exactly one element" penalise the model for
  mentioning something correct that the annotator did not foresee. The penalty must be for the
  wrong, not for the superfluous.

  *Checking algorithm.* In two passes, because the item is half textual and half needs a frame.

  At step 0 write out all the **restrictive** items of the rubric — those containing "exactly",
  "only", "the single", "at most" or a closed enumeration. Items of the form "X is named" are
  not restrictive and are not considered further.

  At the window-viewing step (frames are taken there anyway for 2.4 and 2.5) ask, for each item
  written out: is there anything else in the frames of the window that falls under the wording
  of the question? If so, either soften the item or narrow the question; the latter is usually
  better, because it also removes the ambiguity for the participating model.

  *Status.* Steps 0 and 2 of the sample reviewer. Verdict `FIX_QUESTION`.

  *Frequency.* Caught.

---

## 6. Distractors — retired 2026-09-07

The group and the `distractor_windows` field it checked were removed. The numbers 6.1–6.4 are
not reused; the names `distractor-fully-covered`, `distractor-not-correct-answer`,
`twins-keep-legal-distractor`, `distractor-why-hides-answer` stay in the contract so that the
reviews saved under checklist 2026-08-24 still read.

Why. The plan gave the field three jobs, and none of them needed it. (1) Template 2, "an
answer in the early window must lower the score": an early answer, right or wrong, lies
outside every window, earns no PAUC and raises the false-alarm rate — the score is lowered
without an annotated interval. (2) Anti-spam for multi-trigger samples: a spammer lands in
any interval, and the false-alarm rate plus the answers-per-sample count from the same
paragraph of the plan catch spam more directly. (3) The trap rate: it measured hits on an
**a priori guessed** decoy, and not one of the 44 was ever checked to catch anybody; the
diagnostic "what do models fall for" is obtained honestly after the fact, by clustering the
false alarms of several models in time.

What the field cost. To satisfy the former 1.5 the proposer put a gap `[question_time,
t_start)` under the name of a distractor in 19 samples of 44 — an interval that describes the
*absence* of an answer, not a *wrong* one. Handed to the semi-blind reviewer as an exclusion
zone, its end gave away `t_start`, and the key check 2.2 became a comparison of two numbers the
annotation itself supplied (see the *Checking algorithm* of 2.2). The four items here, the
passing of decoys to the reviewer and the "insurance policy" of the coordinator all rested on
that field.

What remains of template 2 is a property of the wording: an early plausible but wrong value
before the correct one. The proposer's intent is recorded, when they wish, in the optional
`provenance.trap_note` — a string with no interval, not validated, not scored, shown to no
reviewer.

---
## 7. Labels

- `[A]` **7.1. `temporal_rel` is derived, not set by hand.** · `temporal-rel-derived`

  *Statement.* The "pre / at / post" axis is determined by the position of `question_time`
  relative to the **evidence** (`evidence_span`), not relative to the answer window and not by
  "where the model takes the answer from" — the latter is the `reasoning_level` axis, and the
  two are easy to confuse.

  The geometry that follows from this, and that is useful to keep in mind while annotating:

  | Axis | `question_time` relative to the evidence | answer window |
  |---|---|---|
  | `pre` | earlier than the evidence appeared | opens where it appeared |
  | `at` | inside the evidence | usually `t_start = question_time` |
  | `post` | not earlier than the evidence ended | usually `t_start = question_time` |

  The coincidence of `t_start` and `question_time` for `at` and `post` is not a formal rule but
  a consequence of the meaning: there is nothing to wait for, the information is already there
  or is arriving right now. An exception occurs with `at`, when the object is still being drawn.

  *Checking algorithm.* The value is computed from `question_time` and the `evidence_span` of
  the first and last required trigger and compared against the recorded one.

  *Status.* Implemented. It used to degenerate when `evidence_span` was empty (the answer window
  was substituted); the field is now mandatory — see 1.9.

  *Frequency.* Caught across the whole set at once: the axis was initially misunderstood.

- `[A]` **7.2. `audio_dependency` is empty until the probes have answered.** · `audio-dependency-empty-in-draft`

  *Statement.* This is the result of probe 4.5, not the annotator's opinion. The label is legal
  exactly when both flags it is derived from are filled in — `visiononly_solved` and
  `solvable` — and is obliged to agree with what the rule from 4.5 derives. Symmetrically:
  the `validated` status requires all five `validation.*` flags to be filled in.
  `solvable = false` is incompatible with `validated`; `blind_solved = true` is compatible
  because it controls primary-set eligibility rather than correctness.

  **The condition is completeness of the measurement, not the status.** Draft and rejected
  records may retain measurements for repair or audit, but no lifecycle status permits an
  opinion-based `audio_dependency` value.

  > **Blind-solved candidates go through probes and full review on an equal footing.** A
  > completed, correct candidate becomes a validated blind baseline. A terminal rejected
  > sample is already known to be incorrect or deliberately abandoned and need not be sent
  > through missing roles merely to complete its modality flags.

  *Checking algorithm.* Checking `audio_dependency` for compatibility with the probe flags
  (S-17, S-25) and `validation.status` against the filled-in fields (S-18).

  *Status.* Implemented.

  *Frequency.* Caught once — by the rule itself: the coupling with the status jammed rejected
  samples between S-17 and S-25.

- `[M]` **7.3. `reasoning_level` is not inflated.** · `reasoning-level-not-inflated`

  *Statement.* `L1` — the answer is read off the screen or off the speech directly; `L2` — one
  has to connect moments separated in time; `L3` — one has to derive something that is not in
  the video at all.

  **The level is that of the cheapest legal route.** A sample usually admits several ways to
  the full rubric: recall the fact from the topic, read it off a frame shown three minutes
  earlier and multiply by two, derive it from scratch. The participant will take the
  cheapest one, so the label describes that one, not the route the question was written
  around. Two conventions close the gaps between the three definitions:

  - if all the facts the answer is made of are spoken in a single utterance, or stand on a
    single frame, it is `L1`, however complex the sample may look from the outside;
  - one step of arithmetic over values that are displayed — the sum of four shown terms,
    the doubling of a shown curvature — is `L2`, not `L3`: the result is "not in the video"
    only in the letter of the definition, and nothing is derived. `L3` is for a derivation
    whose ingredients the screen does not hand over.

  The same rule is applied when a sample is re-labelled after a hit of 2.2/2.3 (the ladder
  there) or after 2.5 with a non-empty residue: the level is recomputed from what the new
  window leaves to be done.

  *Checking algorithm.* Compare the level against the placement of the answer's facts in the
  transcript and against the cheapest route the window admits. It is checked first of all in
  step 0: the verdict of item 2.5 depends on the level — for `L1` the author's answer sounding
  nearby is normal, for `L2`/`L3` it compromises the sample.

  *Status.* Step 0 of the sample reviewer, no frames needed. Verdict `FIX_QUESTION`.

  *Frequency.* Caught.

- `[M]` **7.4. `depends_on` means dependence, not order.** · `depends-on-is-dependency`

  *Statement.* The field exists so that the share of correctly built chains can be counted. If
  it is set on every pair of neighbouring triggers in a row, the chain metric stops measuring
  anything. Set it only where the rubric has an item requiring a reference to the previous
  state.

  *Checking algorithm.* For each link, find in the rubric of the dependent trigger an item that
  cannot be satisfied without the previous answer. If none is found, the link is superfluous.
  The work is purely textual: two rubric lists are compared, no frames needed.

  The other side of the same thing: if such an item is in the rubric but the link is not set,
  the window drops out of the denominator of the chain metric. It must be checked in both
  directions.

  **A required trigger cannot depend on an optional one.** An optional window is one where the
  rubric explicitly permits silence. A model that lawfully kept silent there automatically
  breaks the chain and loses the required window, that is, it is penalised for behaviour the
  annotation declared correct. That is arithmetic, not judgement, and `S-30` guards it.

  A caveat that nonetheless remains: a model may be obliged to **remember** what happened in an
  optional window without being obliged to speak there. That is dependence on an event, not on
  an answer, and `depends_on` is not suited to it — the field counts chains of answers. Such a
  link lives in the rubric of the dependent trigger ("refer to the quantity introduced
  earlier"), where it is also checked.

  *Status.* The work of the per-window reviewer, no frames required. Verdict `FIX_QUESTION`.
  The formal side of the field is in 1.4, the ban on depending on an optional one is `S-30`.

  *Frequency.* Caught twice: a chain was set end-to-end while the real dependence was on one
  window only; in `q05` a required trigger depended on an optional one whose rubric permitted
  silence.

- `[M]` **7.5. `evidence_span` points at the last piece of evidence.** · `evidence-span-is-last`

  *Statement.* The formal presence of the field (1.9) does not guarantee its correctness, and an
  error here silently changes the `temporal_rel` axis. The interval must cover the moment when
  the **last** fact necessary for the answer appears, not the first and not the most noticeable.

  The typical way to go wrong here is to take **confirmation** for evidence: the place where the
  author himself pronounces the answer. It comes later and does not go into `evidence_span`
  (see 1.9); its place is `provenance.evidence`. The question this item answers is "when did the
  answer **become derivable**", not "when was it named".

  *Checking algorithm.* The same pass as in 2.2: the moment where the answer first coincides
  with the reference one is the right boundary of the evidence. It costs no separate frames —
  the result is taken from the viewing already carried out.

  *Status.* Not implemented.

  *Frequency.* Not checked: the field is filled in almost nowhere.

- `[A]` **7.6. `audio_dependency` agrees with what the probes derive.** · `audio-dependency-matches-probes`

  *Statement.* Deriving the label itself (4.5) is arithmetic over two flags, and keeping it
  inside an `[M]` item was a violation of 9.4: the check lived in the validator while the item
  for it was listed as "model's work". Now split: the probe is the model's work (4.5), comparing
  the label against its result is the validator's.

  The point of the comparison: the label is not set by opinion. A discrepancy means somebody
  wrote `audio_dependency` by hand over the measurement — exactly the substitution the field was
  split into `audio_dependency` and `audio_dependency_claim` to forbid.

  *Checking algorithm.* Recompute the label by the rule from 4.5 and compare. An unfilled label
  is permissible only while the sample is not `validated`.

  *Status.* Implemented, `S-25`.

  *Frequency.* —

- `[A]` **7.7. The probe flags do not contradict one another.** · `probe-flags-consistent`

  *Statement.* The five `validation` flags are related in meaning, and some combinations are
  impossible. Success of any single-modality probe proves solvability, so `solvable = false`
  alongside it is a contradiction. A single frame is a subset of the frames, so
  `frozenframe_solved = true` alongside `visiononly_solved = false` is one too.

  The rule for filling in `solvable` (4.7) exists precisely for this reason: without it the
  field stayed empty in the commonest case — probe 4.7 was not launched because there was no
  reason to — and the sample would not reach `validated`, that is, the check blocked itself.

  *Checking algorithm.* The lattice of implications between `solvable`, `blind_solved`,
  `textonly_solved`, `visiononly_solved`, `frozenframe_solved`.

  *Status.* Implemented, `S-27`.

  *Frequency.* —

---
## 8. Provenance

`provenance.evidence` holds references to where the reference answer was taken from. They exist
so that the annotation can be re-checked, and are therefore obliged to be correct in themselves.

- `[A]` **8.1. The timecodes in the references exist.** · `timecodes-exist`

  *Statement.* A reference points at an existing moment: the frame lies within the duration, the
  speech interval is not inverted, and both of its boundaries **coincide exactly with the
  boundaries of utterances** in the transcript — the start with the start of some utterance, the
  end with the end of some utterance.

  This is not a formality. A reference that breaks off in the middle of a phrase cannot be
  checked by eye: opening the transcript at that place, the reader sees a fragment rather than
  what was referred to.

  The rule is deliberately asymmetric in the cost of an error. Capturing an extra neighbouring
  phrase is harmless — the reference stays readable and checkable; cutting off a needed one is
  not. So the interval should be aligned **outwards**, to the end of the last utterance touched,
  rather than inwards. Completeness of coverage and consistency matter more here than precision
  of the boundary.

  *Checking algorithm.* Parsing the structured `evidence` records and comparing them against the
  duration and the transcript from `bundle.json`.

  *Status.* Implemented. It became possible after `evidence` moved to a structured format: over
  free prose the regular expression saw only records of the form `frame t=<number>` and only
  going beyond the duration — speech intervals and second timecodes inside a line were invisible
  to it.

  *Frequency.* Never.

- `[M]` **8.2. The content at the reference matches its description.** · `reference-matches-description`

  *Statement.* A reference can be valid and still describe something other than what is in the
  frame: a typical situation is a description saying "the table is shown in full" while at the
  frame named the animation is still running (see 2.4).

  *Checking algorithm.* Show the VLM the frame named together with the text of the description
  and ask whether one corresponds to the other.

  *Status.* Not implemented, checked by hand.

  *Frequency.* Caught.

- `[M]` **8.3. The references do not contradict the windows of their own sample.** · `references-consistent-with-windows`

  *Statement.* One combination shows up: `evidence` records "the author himself pronounces the
  answer starting from such-and-such a moment", and at the same time the answer window opens
  later than that moment. Each statement is true separately; together they mean a broken sample.
  This is item 2.5, detectable for free, without going to the video.

  The contradiction here is one-sided. A reference **later** than the window is the norm, not an
  error: `provenance.evidence` holds the confirmation, and with `predict` it arrives by
  construction after the model was supposed to answer (1.9). What breaks the sample is only a
  reference implying that the answer was available or pronounced **before** the window opened.

  *Checking algorithm.* Feed an LLM the texts of all the `evidence` records together with the
  window boundaries and ask whether there is a contradiction between them — in that direction
  specifically.

  *Status.* Not implemented.

  *Frequency.* Caught.

- `[M]` **8.4. The reference answer is correct.** · `reference-answer-verified`

  *Statement.* The blind spot of the whole checklist: groups 2–8 check the consistency of the
  annotation with itself and with the video, and not one of them checks that the answer recorded
  in `response` is **right**. A wrong reference breaks the sample twice over — a model that
  answered correctly gets zero, and a model that repeated the annotator's mistake gets a point.

  Worse, the mechanism masks the error. Probe 4.7 answers from the full material independently;
  the coordinator compares its answer against the wrong reference, gets a discrepancy, sets
  `solvable = false` and throws out a **good** sample with a `CRITICAL_FAIL` verdict. With this
  arrangement, the hypothesis "the reference is wrong" never surfaces.

  *Checking algorithm.* Recompute the answer **independently**, without looking at `response`,
  and only then compare. For computational answers (`act: counterfact`, level `L3`, any numbers
  in the rubric) — symbolically or numerically, not in one's head: the result of the
  recomputation goes into `provenance.evidence` as an `other` record with the formula and the
  number obtained. For qualitative answers — name the place in the video the answer follows
  from, and check that it follows from there rather than from general knowledge of the subject.

  The coordinator is obliged to hold two hypotheses rather than one: a discrepancy between probe
  and reference means either "the probe failed" or "the reference is wrong", and telling them
  apart is the work of this item, not of 4.7.

  *What to do on a hit.* `CRITICAL_FAIL` if the answer is wrong on the merits; `FIX_QUESTION` if
  it is right but written down in a way that makes it impossible to accept as right.

  *Status.* Not implemented. The sample reviewer, item `reference-answer-verified`.

  *Frequency.* Never — the check did not exist until now.

- `[M]` **8.5. The twins' reference answers agree in substance.** · `twins-agree-on-substance`

  *Statement.* A twin pair (`twin_of`) exists so that the difference between their metrics reads
  as **the price of timing alone**: the same question, the same material, a different moment of
  issue. If their reference answers have diverged not in wording but in content, the difference
  no longer measures timing but the difference between two tasks — and the conclusion the pair
  was created for becomes wrong. The judge sees exactly the `response`, so a discrepancy here
  costs more than a discrepancy in any other field.

  A discrepancy in **wording** is legitimate and expected: for the `post` twin the answer
  naturally sounds in the past tense ("the author showed…"), for the `at` twin in the present.
  What is checked is the substance: the same quantities, the same objects, the same conclusion.

  This cannot be checked automatically — `S-24` compares the rubric, the modalities, the level
  and the act, that is, everything comparable as a string. Comparing the meaning of two free
  texts is left to a human or a reviewer.

  *Checking algorithm.* If the sample has a `twin_of`, write out both `response` texts and name
  point by point what coincides in them: quantities, objects, direction of the conclusion. A
  discrepancy in even one is a hit. If there is no `twin_of`, the item is `na`.

  *What to do on a hit.* `FIX_QUESTION`: the reference that diverged from the intent of the pair
  is fixed, not both at once.

  *Status.* Not implemented. The sample reviewer, item `twins-agree-on-substance`. No frames
  required — the work is textual.

  *Frequency.* Never: in the pilot both pairs (`q02`/`q02b`, `q07`/`q07b`) coincide verbatim,
  but the check did not exist until now.

---
## 9. Drift of documentation and tools

A group of its own: there are no errors in the data, but the description has fallen out of sync
with it. It is caught badly, because the eye slides over familiar text.

- `[A]` **9.1. The numbers in the documentation are recomputed from the data.** · `numbers-recomputed`

  *Statement.* Counts of samples and triggers, coverage tables, derived columns. A number
  written by hand goes stale at the very first edit of the annotation.

  *Checking algorithm.* Generate such fragments with a script, or verify them with a script
  during validation.

  *Status.* Not implemented.

  *Frequency.* Caught several times.

- `[A]` **9.2. The examples in the documentation are dumped from a live file.** · `examples-generated`

  *Statement.* An example rewritten by hand stops passing its own schema in time — and the
  reader learns from a wrong specimen.

  *Checking algorithm.* Run every JSON fragment from the markdown files through the same schema
  and the same semantic checks as the annotation.

  *Status.* Not implemented.

  *Frequency.* Caught: the canonical example in the plan did not pass its own schema.

- `[A]` **9.3. The tools are idempotent.** · `tools-idempotent`

  *Statement.* Re-running a documented command must not change the artefacts. A violation is
  dangerous because it breaks reproduction at the very first step: a person follows the
  instruction from the README and immediately gets a discrepancy.

  *Checking algorithm.* Run the pipeline again and compare **file hashes**. Checking with
  `git status` is not enough: the videos, the frames and `vendor/` are not under version control,
  and those are exactly what gets regenerated.

  *Status.* Implemented for `prepare_review_workspace.py`: a repeated `--until` rebuilds
  `frames/` and `transcript.md` from scratch, so narrowing the boundary no longer leaves material
  beyond it. In the rest of the pipeline it is maintained by discipline.

  *Frequency.* Caught twice: a change in the frame naming scheme diverged from the committed
  bundle; a repeated `--until 400` on top of `--until 1200` left frames up to 1155 s in the blind
  reviewer's folder while `limits.json` claimed 400.

- `[A]` **9.4. The checklist does not diverge from the validator.** · `checklist-matches-validator`

  *Statement.* Group 1 is declared to be the specification of `tools/validate_samples.py`. A
  check that lives in the code but is not described here is invisible to a person who reads the
  checklist as a convention; an item described here as implemented but absent from the code
  creates false confidence.

  *Checking algorithm.* Compare the two lists at every change to the validator: every check in
  the code has an `[A]` item, and every `[A]` item with the status "implemented" has a negative
  test.

  *Status.* Implemented in `schema/review.py` (the `__main__` block): it compares the names in
  both directions, requires an `S-NN` rule for every implemented `[A]` item and either a role or
  a coordinator's derivation for every `[M]`. Group 9 is excluded from the first check: its `[A]`
  items are about the code of the repository, not about a sample.

  *Frequency.* Caught: seven implemented checks were missing from the checklist, and two items
  were marked as automatic without having any code.

---

## The order of application

1. `[A]` — `/home/user/conda/bin/python3 tools/validate_samples.py data/annotations/*.jsonl`.
   Cheap, run after every edit. The interpreter is named explicitly: the project has two
   environments, and `python3` resolves differently in each.

2. `[M]` — the verifier. The order within the level is set by cost: first 4.6 and 4.7 (questions
   to oneself, zero frames), then reading the transcript, then the sparse viewing, and only at
   the end a dense viewing of the stretches the previous steps flagged as suspicious. Runs
   4.2–4.5 go as a separate pipeline and reject samples wholesale.

   The full working order of the verifier is described in
   [docs/annotation_pipeline.md](annotation_pipeline.md).

3. `[H]` — there are **no** items that would wait for a human: the last ones (4.8, 7.4) have
   been handed to the reviewer and the validator. The level remains an escalation point:
   everything the edit cycle has not closed in three iterations lands here, as do cases where the
   reviewers persistently disagree. Separate from that is acceptance (step 6 of the pipeline) —
   it is exhaustive, but it checks the checklist as a whole rather than individual items.

4. **A repeat `[A]` run.** Edits following from `[M]` and `[H]` are shifts of boundaries, and the
   boundaries are coupled: shifting `t_start` may violate 1.1, shifting `question_time` changes
   the derived `temporal_rel` label (7.1) and breaks the comparability of twins (5.1). The pass
   is not a one-off.

A separate case where the steps conflict: 2.2 requires shifting `t_start` to the first moment
where the answer is possible, while 1.1 forbids a window to start earlier than `question_time`.
If that moment turns out to be earlier than the issue of the question, this is already case 2.3:
what is fixed is not the window but the intent — either `question_time` is moved, or the sample
is re-annotated as `post`. After that 7.1 and 5.1 are re-checked.

None of the three levels replaces the others. Tellingly, independent adversarial reviews of the
pilot each found several substantive errors at a time when the validator was steadily showing
zero.

---

## Open questions

There are no open format questions at the moment. Below are the decisions reached, with the
reason: without it the same forks get discussed anew in a month.

### Closed

- **Empty when-clauses, small gaps and the "explicit answer" of 2.5** — settled 2026-09-08,
  after the first systematic run of 2.3 (8 hits of 18 on the 2017 video, 1 of 16 on the
  2026 one). A when-clause that contributes no rubric item gives no right to `pre`; a gap
  of up to 10 s is an interval edit; a larger one is cured by the ladder in 2.2 (open the
  window on the evidence → move `question_time` or re-label `at`/`post` → reject), with the
  level re-derived from the cheapest route (7.3). In 2.5 the rubric is split into what the
  stream hands over and the residue: an empty residue compromises an `L2`/`L3` sample, a
  non-empty one re-levels it. No checklist version bump: no item was introduced or retired
  and the reviews of the 2026-09-07 round stay current; the reading of 2.5 changed, so a
  `full_window` written before this date that set `CRITICAL_FAIL` on 2.5 is re-read by the
  coordinator under the residue rule. Amended 2026-09-09 from the round that applied it:
  step 0 also asks whether the clause keeps the trigger unique (3.1); after a cut both
  windows get a fresh `evidence_span` and are separated by the transcript line, not joined
  (2.1, 7.5); 5.3 records that a rubric checks the answer string, not the route to it.
- **Distractor windows** — the field `distractor_windows`, its four items (group 6) and the
  automatic rules 1.2 and 1.5 were removed on 2026-09-07. The reason is in the note that
  replaced group 6: for scoring the field duplicated the false-alarm rate, for anti-spam the
  answers-per-sample count, and in review it leaked `t_start` to the semi-blind reviewer.
  Template 2 remains as a property of the wording; the intent goes into
  `provenance.trap_note`.
- **The semantics of `provenance.chapter`** — the field has been removed. It denormalised what is
  derived from `triggers` and `info.json`, and went stale when a window shifted across a chapter
  boundary. All its uses (human navigation, diversity control, cutting the video into intervals
  for proposers) work on the computed value, and the overview notebook did exactly that from the
  start: `chapter_at(t)` takes the chapters from `bundle.json` and never read the field once.
- **A flag for the exhaustiveness of a question** — no `exhaustive` flag will be introduced.
  Group 3 has been rewritten so that it works without one: it would have influenced only the
  choice of remedy in 3.1, and the remedy is already proposed from the wording of the question.
  As a taxonomy level the attribute is not needed either — it almost coincides with
  `act` = `monitor`.
- **How control twins are linked** — the `twin_of` field, checks `S-23`/`S-24` (5.1).
- **What `audio_dependency` is measured by** — probe 4.5, by the rule deriving it from
  `visiononly_solved` and `solvable`; the `helpful` grade has been removed from the label.
- **The granularity of the shortcut flags** — there are no runs any more; the flags are filled in
  by probes over the sample as a whole, with the aggregation rule "one required window is enough"
  (4.1).
- **What to do with a sample solvable blind** — finish its review, mark `blind_solved`, and
  exclude it from primary tasks; if otherwise correct it remains a validated blind baseline
  (4.2). There will be no tests of "timing alone" in the primary set.
- **The scale of the rubric** — not needed at the annotation stage: the probe answers, the
  coordinator compares qualitatively, disputed cases are asked again pointwise and, if the
  disagreement persists, go to a human or are thrown out (4.1). Weights and thresholds are a
  question for the measurement phase, together with the metric.
