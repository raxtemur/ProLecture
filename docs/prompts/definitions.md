# Definitions

> **2026-10-06.** The proposer's and the coordinator's prompts and the checklist refer to this
> file. The reviewers' prompts are not yet brought in line with it; until they are, where they
> differ, this file wins. The `Copied into:` lines name the prompts that are to carry a
> copy; the copies are not there yet.

The terms the proposer and the coordinator use, defined in one place. The proposer and the
coordinator read this file once at the start of their work, and its definitions are binding
for them. Where a prompt or the checklist words a term differently, this file wins.

**Reviewers and probes do not read this file.** Each reviewer gets a copy of the definitions
its checks need, inside its own prompt. A line `Copied into: …` under a definition names those
prompts: when you edit the definition, update the copies. The split is deliberate. Some
definitions here would change what a reviewer measures: how an optional window is scored,
when a blind answer counts, what makes a when-clause empty. A reviewer who knows them starts
reasoning about the outcome instead of measuring. The probes do not know they take part in a
check at all.

---

## `act`

What the participant does when it answers; independent of the axis. Every act answers
with content, read from the video or worked out from it: "now" or "it happened" alone is
a waiting-only task.

- `alert` — report that a condition named in the question has occurred, and what
  occurred. The question states the condition as a condition ("if…"), never as a fact
  about this video.
- `monitor` — report each change of a tracked quantity or state, with its new value.
- `ground` — at an event, name where it happens or what it concerns: a region, an object,
  a quantity.
- `narrate` — explain what is happening as it happens: why a step is taken, what it does.
- `predict` — name what the video will do next, before it does. The author later says or
  shows the answer, at least 10 s after the last window; otherwise it is not a `predict`.
- `verify` — judge whether what is shown holds, and why. The outcome must depend on the
  video: an identity or a definition is not a check.
- `counterfact` — change a premise of what is shown (an input, a parameter, a law) and
  work out the result.
- `extend` — go further with the premises unchanged: the next terms, the shown method on
  a new case, the exercise the author leaves open.

The video gives the answer of neither `counterfact` nor `extend`. `predict`,
`counterfact` and `extend` are never `L1`.

Copied into: `reviewer_full_sample.md`.

---

## `reasoning_level`

`reasoning_level` is the work that the cheapest legal route to the full rubric leaves to the
participant inside the answer window, after everything the stream supplies there is accounted
for.

- `L1` — reading. Every scored item stands as it is on the screen or in the speech between
  `t_start` and `t_end`: the participant recognises it and repeats it.
- `L2` — integration or a short calculation. The participant connects what the window shows
  with something shown or said before `t_start` and no longer on the screen, compares two
  states, or does a short calculation over given values (adding up shown values, scaling a
  shown quantity by a given factor).
- `L3` — derivation or substantial computation. The participant carries out an independent
  derivation, construction or substantial computation whose result the video does not give:
  extends a sequence, fills a new table column, recomputes for a changed input or law. The
  inputs and the method may be on the screen; the work must still remain to be done.

An item is **read off** when the speech or a frame contains its value, and **computed** when
they contain only what it is computed from. Copying ten given numbers is reading; computing
ten new ones can be `L3`. Label the cheapest route, not the one the question was written
around; the topic's difficulty, the `act` and the number of items do not set the level.

The level counts only what the stream supplies inside the window, together with what the
question itself states. What the author says or shows in the ten seconds after `t_end` does
not lower the level: it is a defect of the window, cured by closing the window earlier or by
changing the question.

A `predict` sample is never `L1`: its answer has not been given in the stream yet.

**A legitimate `L1` task.** The answer is read from the video inside the window — a value, a
label, a state on the screen, the author's words — and the question itself does not give it.
A question whose answer is fixed by its own wording measures nothing but the moment of
speaking: "recall this known fact and say it in time", "report that the author has named X".
That is a waiting-only task, and such tasks are not built. There is no "`L1` alarm": raising
an alert is the act `alert`, an axis independent of the level, and an `alert` can be of any
level.

Copied into: `reviewer_full_sample.md`, `reviewer_full_window.md`.

---

## When-clause

The part of a question that ties the moment of the answer to an event in the video: "when …
appears", "after the author …".

- **Substantive** — at least one rubric item becomes available only once the event has
  occurred: the event brings a value, a relation or a transition the answer needs.
- **Empty** — the event makes no rubric item available: everything the answer needs is in the
  stream or in the question before the event, and the event only names a moment.

An empty when-clause gives no right to `pre`. The required window opens at the first moment
the answer becomes possible, its `evidence_span` sits on the real evidence, and the validator
derives the axis from it: the sample is still `pre` if that evidence comes after
`question_time` — the wait is then for the content, not for the event — and `at` or `post`
otherwise.

The proposer does not write empty when-clauses. An empty clause stays in a question only when
it is the one thing that fixes which object the question is about, or keeps the question from
firing again on a later repeat of the same state. Then it is not dropped but replaced: by a
mathematical property that singles the object out, by the state at the moment of the question
("now on the screen"), or by a time qualifier that holds throughout the window and fails
after it.

Copied into: `reviewer_full_sample.md`.

---

## Check result, report verdict, sample status

Three different layers, often confused:

- **check result** — one per checklist item in a reviewer's report: `ok` (checked, did not
  fire), `fail` (fired), `skipped` (not checked; the report names what was left uncovered),
  `na` (the item does not apply to this sample);
- **report verdict** — one per reviewer's report, the most expensive cure that any fired check
  requires: `PASS` < `FIX_INTERVALS` (move boundaries, add or remove a window) < `FIX_QUESTION` (reword
  the question, the rubric or the labels) < `CRITICAL_FAIL`;
- **sample status** — `validation.status`, set by the coordinator after all reports and
  probes: `draft` (in work), `validated` (checked and correct), `rejected` (incorrect, or the
  work was abandoned). Whether a sample enters the primary benchmark is decided separately,
  by `blind_solved`.

### `CRITICAL_FAIL`

A report verdict: the sample cannot be cured by moving boundaries or by rewording while it
keeps measuring what it measures. The coordinator either rejects it or rebuilds the idea as a
new sample — another moment for the question, another question or another level — and the new
sample goes through the full cycle. The exception is lowering the level to `L1` without
changing the windows or the wording: it needs no second review, and it is legitimate only if
the question does not itself give the answer, and never on a `predict`, `counterfact` or
`extend`, which are never `L1` ("`act`").

The reviewer writes what could be rebuilt into the `proposal` of the check that fired. When
the author hands over the whole answer inside the window of an `L2`/`L3` sample, the options
are: move the question to where minutes, not seconds, separate the evidence from the author's
explanation; ask about something the author does not say (a consequence, the direction of an
error, an application to another case); lower the level to `L1`, except on a `predict`,
`counterfact` or `extend`.

Copied into: `reviewer_full_sample.md`, `reviewer_full_window.md`.

---

## Boundary tolerance

The gap between an annotated boundary — `t_start`, `t_end`, `question_time` — and a
reviewer's measurement of the same boundary (for the earliest possible answer, `t_start −
t_val`) is handled in steps:

- **up to 2 s** — within the precision of the measurement: manim animations run for 1–2 s,
  and the description track dates events to whole seconds. The boundary moves to the measured
  value without a second review;
- **from 2 to 10 s** — a boundary error: the boundary moves, the touched window is reviewed
  again and the probes whose material moved are rerun (`FIX_INTERVALS`);
- **over 10 s** — for `t_start` against the earliest possible answer it is not a boundary
  error: the answer was available long before what the question waits for, and the
  coordinator decides it by the when-clause of the question — an early optional window when
  the event brings something the answer needs, a reworded question when it brings nothing.
  For any other boundary a gap over 10 s is a boundary error, as in the step above.

For `question_time` only the first step applies: a move of more than 2 s changes the moment at
which the question must make sense, and it goes as a new version of the question, reviewed in
full.

When a boundary is uncertain within 2 s, set the window wider rather than narrower: `t_start`
at the early edge, `t_end` at the late one, as long as the rule of the author's reveal still
holds (for `L2`/`L3` and for `predict` a window closes at least 10 s before the author says or
shows the answer).

A window is not narrowed when the part to cut is 2 s or less. When the answer is the event
itself — the author says it, it appears on the screen — the window runs at least 5 s past the
event, the time a streaming model needs to produce the answer, and it is not narrowed below
that on the right.

Copied into: `reviewer_full_window.md`.

---

## Optional window

A window (`"required": false`) in which giving part of the answer, or all of it, is legitimate
but not required. Usually the answer is possible there by a harder route than in the required
window (computing what the required window will later show), or only in part (elements that
appear one by one), or the moment is disputable (a firing of a `monitor` that a reasonable
annotator might have skipped).

The required window opens at the first moment the answer is possible by the route the
sample's level describes; an earlier, harder route gets an optional window. Example: "Name the
sine of angle B", where the angle is shown first and its sine later. An optional window runs
while only the angle is shown, and the required window starts when the sine is shown; the
level is set by the required window — reading the sine, `L1`.

A required window never depends on an optional one (`depends_on`). A `predict` sample has no
optional window after its last required one: that stretch is where the author reveals the
answer. On `L2`, `L3` and `predict` an optional window obeys the rule of the author's reveal
like any window ("Boundary tolerance").

Copied into: `reviewer_full_sample.md` (without the paragraph below).

**Scoring.** An answer inside an optional window is not counted as an answer outside the
windows (FAR), and silence there is not penalised. The window enters neither the main PAUC nor
the recall denominator.

---

## `blind_solved`

`true` when the semi-blind reviewer's answer, given before viewing, is at once:

- **correct** — it meets every substantive rubric item (a quantity, a relation, a
  derivation); items about the look of the screen — a colour, the choice of symbols,
  anything else that could differ without changing the claim — do not decide it; a sign, an
  index, a unit, or which coefficient goes with which quantity is substantive when changing
  it changes the claim;
- **honest** — it follows from the question and prior knowledge, without assumptions about
  screen content that was not seen. A reading the question's own wording forces is not such
  an assumption: the model under evaluation will make it too. A guess is a choice among
  concrete alternatives for the screen's content that the question leaves open.

Recalling a known textbook or historical fact counts as solving blind. What decides is whether
someone who knows the subject but has never seen this video could give the answer. Content only
this video has — its examples, its numbers, its construction — is not solving blind, however
the answer came by it: the test is someone who has never seen this video. Whether a model
remembers a video is not decided in the annotation; it is measured separately. Predicting which
values, example or layout the screen will show is not solving blind either, even when the
prediction is exactly right. The flag is set by the coordinator. `true` excludes the sample
from the primary benchmark but does not prevent `status: validated`.

---

## `temporal_rel`

Where the evidence lies relative to the moment the question is issued: `pre` — it appears
later, and the participant has to wait and decide when to answer; `at` — it is present at
`question_time`, perception and computation here and now; `post` — it has gone by, an answer
from memory.

Derived, not set by hand. Over **all** required windows take the earliest start `a` and the
latest end `b` of `evidence_span` — not the first and the last window of the list, since the
evidence of a later window may come earlier. Then `pre` if `question_time < a`, `post` if
`question_time ≥ b`, `at` otherwise. The validator recomputes the value and rejects a
mismatch.

---

## `audio_dependency`

Measured, not declared. The label is derived from two probe flags, `visiononly_solved` and
`solvable`, and stays `null` until both are filled in, whatever the status of the sample.
Then: `visiononly_solved = true` gives `unnecessary`; `visiononly_solved = false` with
`solvable = true` gives `required`. The annotator's opinion lives separately, in
`audio_dependency_claim`.

---

## `evidence_span`

The interval of the last piece of evidence the answer needs — not of a confirmation. A
confirmation, recorded in `provenance.evidence`, may lie after the window (`predict`) or
outside the video (`counterfact`); the evidence may not. The axis `temporal_rel` is derived
from `evidence_span`.

Copied into: `reviewer_full_window.md`.
