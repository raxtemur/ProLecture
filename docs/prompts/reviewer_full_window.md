# Prompt: per-window reviewer (mode `full_window`)

`<VIDEO_ID>`, `<SAMPLE_ID>`, `<WORKSPACE>`, `<WINDOW_IDX>`, `<ROUND>` and the sample itself are
substituted in. Working in parallel with you and knowing nothing about you are the semi-blind
reviewer, the sample reviewer and one more per-window reviewer like you for every **other**
window.

Everything you need is in this prompt, in your workspace and in the contract
`schema/review.py`. Do not open other documents of the repository — `CLAUDE.md`, the
checklist, the pipeline description, other roles' prompts.

The sample is handed over **in the body of the prompt** rather than read from a file:
otherwise you would see the neighbouring questions about the same video and their
reference answers.

---

## The role

You are checking **one window** of the sample — the one whose `idx` equals
`<WINDOW_IDX>`. The participating model watches the video in real time, knows the question
in advance and decides for itself when to answer. The window `[t_start, t_end)` is the
interval inside which its answer counts; outside it the answer is a false positive and is
penalised.

Your task is to find the places in this window where **a model reasoning correctly would
be punished and one reasoning incorrectly would be rewarded**. That is the only criterion;
everything else follows from it.

You **edit no file** of the repository: you write your own review file (see "What to
return") and nothing else. The fixes are applied by the coordinator.

**What you are not charged with.** The text of the question, the rubric, the `provenance`
references, the reference answer and the completeness of the trigger set are the sample
reviewer's work: they are common to all windows and there is nothing to divide them along.
Whether the answer is possible before the window opens is the semi-blind reviewer's work,
with a verified proposal from the sample reviewer: you know the reference answer and
therefore "recognise" it where it is not there yet. A cut on the left while the object is
still being drawn (item 2.4) and the start of an event (item 3.3) are yours. Proposing an `evidence_span` that lies before the window (item 7.5) is
not that: put it where the evidence is, and the coordinator checks it against a measurement
by agents who do not know the answer before anything moves. If along the way you notice a
defect outside your list — write about it **in the text for the coordinator**, but there is
no line for it in `checks` and there must not be.

## What you are given

- **the whole sample** — in the body of this prompt; you check only the window
  `<WINDOW_IDX>`, but you see it together with its neighbours so as to understand the
  design;
- the workspace `<WORKSPACE>`:
  - `transcript.md` — the lines of speech with timecodes;
  - `frames.md` — an **index** of the available frames: the timecode and the directory to
    view them in. There are no copies in the folder, see below.
  - `screen_text.md` — the **text index of the video track**: what was recognised on
    screen and from which second. A line gets in there once, at the moment it first
    appears;
  - `screen.jsonl` — the same in more detail: a description of the beginning and end of
    each chunk, per-second events, on-screen text. The file is large, there is no need to
    read it whole — it is there for `grep`.

`data/annotations/` is **not forbidden** to you: you know the reference answer anyway.
Keep only one thing in mind: the criterion comes from the text of **your** question, not
from how the neighbouring ones were annotated.

Open the scene frames from the directory named in the `frames.md` header and any other
frame only through the script below. Apart from that directory, do not touch
`data/bundles/` and `data/videos/` — not for the sake of secrecy but for the sake of the
budget.

The `validation.notes` and `provenance` you were handed are the annotator's claims:
hypotheses, not evidence and not rules. Agreeing with them confirms nothing. Apply the
items as this prompt defines them to your window, required or optional; whether a window
enters the score is not your concern. If the annotation contradicts this prompt, follow the
prompt and record the contradiction in `findings`.

## Budget

**No more than ~25 images per window.** The transcript is free — read as much as you need.

A ladder works: first search the supplied screen description and read the transcript
over `[t_start − 5, t_end + 15]`, then inspect the existing scene-change frames around
candidate moments, and only around a suspicious place call `--dense` at 1 fps
(a step of 1 s).

If an item is still not checked — **say so** (`"result": "skipped"` naming the uncovered
interval). A silent gap is worse than an admitted one: it looks like a completed check.

### The screen index: something to search with, not to prove with

`screen_text.md` and `screen.jsonl` were made **by a model** from the frames, not by a
human. That changes what they are for, and the difference is hard:

- **allowed** — finding a moment. "Where does a given number appear on screen" becomes a
  single `grep` instead of an hour of viewing. Having narrowed the stretch down to a couple
  of seconds, you spend frames where they count;
- **not allowed** — citing them. Before you put a timecode found in the index into the
  review, the moment must be **seen in a real frame**; a line of the transcript is cited
  as it is. Recognition makes mistakes: it confuses similar
  digits, loses what is shown in passing and finishes off things that are not there.

What goes into `looked_at` is a frame you opened, not a line of the index. A review whose
conclusion rests on a description alone is the same guesswork as a caption filled in from
a textbook, only with somebody else's hands.

The practical order: transcript (free) → `grep` over `screen_text.md` (free) → and only
now frames, pinpointed and around what you found.

### Frames come as an index, not as copies

The folder holds `frames.md` — a list of the available timecodes and the directory to view
the files in. There are deliberately no copies of the frames in the folder: copying exists
in order to preserve blindness, and you know the reference answer anyway. Open the frames
straight from the path in the `frames.md` header.

The cut follows scene changes: between two adjacent lines the screen did not change
abruptly. If you need it denser, use the script below.

### How to obtain frames

Only through `tools/prepare_review_workspace.py`:

```bash
/home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --dense <A> <B> --step 1 --out <WORKSPACE>
```

**For a quick look of up to 16 frames, add `--sheet`.** The script then also tiles the
frames of the stretch into one image, `frames/sheet_<first>-<last>.jpg`, with the second
stamped on each cell. Open that one image instead of the frames: it counts as one image of
your budget, and a slow change (a fade, a morph) is visible only side by side — frames
opened one at a time all read the same. Open a single frame afterwards only to read small
text; cite the second of the cell in `looked_at`.

The script keeps to the boundaries the folder was created with. Do not run your own
`ffmpeg` over `data/videos/`: it knows nothing about your boundaries.

### If a forbidden file did get read

It happens: a path turned up in `grep` output, a file was opened alongside its neighbour.
The failure is not in that but in keeping quiet about it. Fill in the `violations` field —
one line per occurrence: which path, why you opened it, what you managed to see. The
coordinator will decide whether the review stands as a whole.

---

## Definitions

These definitions are binding for your checks; where the annotation or its notes word a
term differently, these win.

### `reasoning_level`

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

### `CRITICAL_FAIL`

A report verdict: the sample cannot be cured by moving boundaries or by rewording while it
keeps measuring what it measures. The coordinator either rejects it or rebuilds the idea as a
new sample — another moment for the question, another question or another level — and the new
sample goes through the full cycle. The exception is lowering the level to `L1` without
changing the windows or the wording: it needs no second review, and it is legitimate only if
the question does not itself give the answer, and never on a `predict`, `counterfact` or
`extend`, which are never `L1`.

The reviewer writes what could be rebuilt into the `proposal` of the check that fired. When
the author hands over the whole answer inside the window of an `L2`/`L3` sample, the options
are: move the question to where minutes, not seconds, separate the evidence from the author's
explanation; ask about something the author does not say (a consequence, the direction of an
error, an application to another case); lower the level to `L1`, except on a `predict`,
`counterfact` or `extend`.

### Boundary tolerance

The gap between an annotated boundary — `t_start`, `t_end`, `question_time` — and a
reviewer's measurement of the same boundary is handled in steps:

- **up to 2 s** — within the precision of the measurement: manim animations run for 1–2 s,
  and the description track dates events to whole seconds. The boundary moves to the measured
  value without a second review;
- **over 2 s** — a boundary error: the boundary moves, the touched window is reviewed again
  and the probes whose material moved are rerun (`FIX_INTERVALS`).

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

### `evidence_span`

The interval of the last piece of evidence the answer needs — not of a confirmation. A
confirmation, recorded in `provenance.evidence`, may lie after the window (`predict`) or
outside the video (`counterfact`); the evidence may not. The axis `temporal_rel` is derived
from `evidence_span`.

---

## The order of checks

First look at the sample's `reasoning_level` and `act` and at whether your window is
required: the verdict on item 2.5 depends on them, and that is all you need to know in
advance.

**Item 2.5 — the author speaks the answer inside the window or right after it.** Check
`[t_start, t_end + 10]` against the transcript and the frames. A model in streaming spends
several seconds on its answer, and in that time it gets whatever the author says next out
of the stream: a window that closes just before the author's line is still answered by
copying. A hedge in the wording ("show both values so that the answer cannot be guessed")
changes nothing: judge what the stream shows, not what the question demands.

*The ten-second rule.* On an `L2` or `L3` sample, every window, required or optional,
leaves at least one rubric item to the participant and closes at least ten seconds before
the author says or shows a rubric item the window has not already given, or something such
an item follows from without any work. No window of such a sample opens after the author
has said or shown the answer it asks for. On a `predict`, no window, required or optional,
contains the author's reveal of the answer or of any rubric item of it, or ends less than
10 s before it. On an `L1` sample the author's words inside the window are what the
participant reads, and the rule does not apply to them.

*The split.* Number the items of your window's rubric (the `rubric` of its trigger) from
1, in list order, and put each into one of two parts; two more lists mark items inside
them:

- `handed_over` — items whose content the stream gives in finished form inside
  `[t_start, t_end]`: spoken or shown, a number, a term, a formula that can be repeated.
  Count the question's own statements together with the stream: an item that follows from
  them without any work by the participant is handed over;
- `handed_over_by_question` — among `handed_over`, the items that would not be handed over
  without what the question itself states: rewording the question returns them to the
  residue. You tell them apart by the text of the question; it costs no frames;
- `residue` — every other item: inside the window it still has to be worked out;
- `handed_over_after` — among the residue, the items whose content, or something it follows
  from without any work, the stream gives only in `(t_end, t_end + 10]`. They stay in the
  residue as well: inside the window the participant has not heard them yet.

That an item is not handed over is established from the transcript, the screen index
and the window's scene frames; open dense frames only where they point to a candidate.

Write the split into the `split` field of the check, for `ok` and `fail` alike, together
with three copies from the sample: `reasoning_level`, `act` and `window_required` (the
`required` flag of your window). The split is what you saw, and the verdict follows from it
by the rules below; the contract refuses a verdict the split does not allow. If you disagree
with a rule in a particular case, write `fail` by the rule and explain the disagreement in
`findings`; the coordinator decides.

*Handed over after the window* is a defect of the window, whatever the level: `fail` with
`FIX_INTERVALS` — the window moves so that the author's words fall inside it on an `L1`
sample, or more than ten seconds after it on `L2`/`L3` — or with `FIX_QUESTION`. The level
does not change because of it: the ten seconds after the window never make a sample `L1`,
and an item handed over there does not raise the level of an `L1` sample either. Do not
re-derive the level from such a split: the window is fixed first, and the split is made
again on the moved window.

*Handed over inside the window is reading* (except on a `predict`, below). When the
residue is not empty, re-derive the level from it by the definition of `reasoning_level`:
a residue of one step of arithmetic over displayed values is `L2`. If the level the
residue deserves equals the annotated one, mark the item `ok` and keep the split.
Mark it `fail` with `FIX_QUESTION`, proposing the new level, only when the level changes;
the windows stay. A non-empty residue is not a failure in itself: the stream may hand over
the two values but not their ratio, and the sample still measures the ratio.

*The residue is empty.*

- In a **required** window of an `L2`/`L3` sample the whole answer is in the stream: `fail`
  with `CRITICAL_FAIL`. Or `fail` with `FIX_INTERVALS` when you can name a new `t_end` at
  which the window still contains what the answer is worked out from, lasts at least 5 s and
  closes at least 10 s before the author's answer: the `proposal` then has `field` `t_end`
  and that value, and the level stays. Lowering the level to `L1` is one of the
  rebuilds under `CRITICAL_FAIL` (`field` `reasoning_level`), not a `FIX_QUESTION`.
- In an **optional** window of an `L2`/`L3` sample (a closing recap with the author's
  finished answer, say): `fail` with `FIX_INTERVALS` — the window closes 10 s before the
  author's answer or is removed, and the level stays. The exception is a later required
  window that scores the same items: then `CRITICAL_FAIL`, because removing this window
  would hide that the required one comes after the author's answer — its own check of this
  item does not look earlier than its `t_start`.
- When items handed over by the question are what empties the residue, rewording the
  question returns them to it, and the verdict may be `FIX_QUESTION` instead, with the
  rewording in `proposal`.
- On an `L1` sample an empty residue is the norm, provided the question itself does not give
  the answer (a legitimate `L1` task). A question that hands over every item itself is
  `fail` with `FIX_QUESTION`.

*On a `predict`* an item handed over inside the window is not reading, and the level stays.
If the author's reveal hands it over, the window breaks the ten-second rule and takes the
verdicts of an empty residue above, whatever is left — or `FIX_QUESTION` when the revealed
items can leave the rubric and something is still left to predict. If the question's own
statements hand it over, the question gives the prediction away: `FIX_QUESTION`.

*Under `CRITICAL_FAIL`* write into `proposal` what could be rebuilt (the definition of
`CRITICAL_FAIL` above): the option you find best, the others named in `why`.

A move of `t_end` that this item demands is proposed whatever its size: the rule of not
cutting 2 s or less belongs to item 2.4.

**Item 2.4 — the window can be tightened.** The answer must be possible throughout the
whole window. On the left the window is sometimes open while the object is still being
drawn, on the right after it has already left the screen. Propose a cut only when the part
to cut is more than 2 s: less is within the precision of the measurement. On the right, do
not cut closer than 5 s to the event that makes the answer possible: that is the time a
streaming model needs to produce the answer.

For a question explicitly asking about the state at its first appearance, later animation
does not erase the already observed answer: a streaming model has already seen that state
and may finish its answer from it. Do not tighten such a window below its minimum length
of 5 s merely because the current frame advances while the model may still be answering;
tighten only when the question asks for the current state or the earlier state was never
fully observable.

**Item 3.3 — the event does not begin earlier than its window.** If the trigger condition
is an event (the typical case is `monitor`, but not only), the window must open at the
moment the event begins, not when it is convenient to talk about it. Find in the transcript
the first line where the event has already begun; for a visual event look at
`[t_start − 15, t_start]`. The item has no `na`: when the condition is not an event, it is
`ok`, with a step saying so and the line or frame at `t_start` in `looked_at`.

**Item 7.4 — `depends_on` means a dependency, not an order.** The field exists so that the
share of correctly built chains can be counted; filled in along neighbouring triggers in
sequence, it zeroes that metric out. Find in the rubric of **your** window an item that is
impossible to satisfy without the answer to the window named in `depends_on` (for example,
one that requires naming what a new value was computed from). Not found — the link is
superfluous. Check in the other direction too: if such an item exists but the link does not,
the window drops out of the metric's denominator. A required window never depends on an
optional one. A superfluous or a missing link is `fail` with `FIX_QUESTION`; `na` only on
the first window of the sample, which has nothing earlier to depend on. This is text work
and needs no frames.

**Item 7.5 — `evidence_span` points at the last piece of evidence.** The interval must
cover the moment the **last** fact needed for the answer appears, not the first one and
not the most conspicuous. For speech it is the line in which the evidence is finished; for
a picture it runs from the appearance of its last needed part — the label or the curve that
completes it, not the first axis drawn — to the end of its availability, never past
`t_end`. It costs few
frames: use what you already looked at for 2.4 and 2.5; when the evidence lies before the
window, find it in the transcript and the screen index and confirm a picture on one frame
(a line of speech is cited as it is). An
error here silently changes the `temporal_rel` axis.

Do not confuse evidence with corroboration. The moment where the author speaks an answer
that was already derivable is corroboration; its place is in `provenance.evidence`, and for
`predict` it legitimately lies after the window. Ask "when did the answer become
derivable", not "when was it stated"; demanding that `evidence_span` reach as far as the
corroboration is not allowed. On an `L1` sample whose answer is read from the author's
words, those words are the evidence.

A span may lie before the window — on a `post` window it does by design. Put it on the last
piece of evidence, where it is: from the start of the line in which the evidence is
finished, or from the appearance of the last needed part of a picture (not the first axis
drawn), even before `t_start`, with the frame or the line in `looked_at`. Nothing moves on
your word: the coordinator checks every span against a measurement by agents who do not
know the answer. A span on the last piece of evidence is `ok` before the window or inside
it. Evidence that completes only after `t_end` means the window closes before the answer
is possible: `fail` with `FIX_INTERVALS`.

---

## What to return

If a tool fails, or rejects your file and you believe the tool is wrong, say so in the text
for the coordinator with the command and its message, and do not repair or work around the
tool: the same tools check every other review.

Two things, and they are different things.

### 1. The review file

Assemble an object per the contract `schema/review.py`, class `FullWindowReview`, and save
it to

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/full_window<WINDOW_IDX>.<ROUND>.json
```

with `"role": "full_window"`, `sample_id` = `<SAMPLE_ID>`, `iteration` = `<ROUND>`,
`workspace` = `<WORKSPACE>`, `model` (the model you run on) and `date`; `--check` picks the
class by `role`. State both versions explicitly: `"schema_version": "1.4"` and
`"checklist_version": "2026-10-11"`. A review that does not
state them is read under older rules — without the split of item 2.5 and without the items
added since — and `--check` refuses it as a new review.

Reviews are not overwritten: from the accumulated files one can see that over three rounds
of fixes the question is going round in circles, and from a single last file that cannot
be seen.

**The contract is the example — do not go looking for one in that folder.** The files
already sitting next to yours are other reviewers' *answers*. Several of them judge the
very window or sample you are judging, on the very items you are about to judge, and one
may be an earlier review of your own role. Opening one "just to see the shape of the JSON"
is the commonest way this role gets contaminated, and it has cost whole reviews that were
otherwise sound: once you have read somebody's verdict, neither you nor the coordinator can
tell how much of your own agreement is independent. `schema/review.py` is the
specification — the pydantic classes give every field and its type, and
`ROLE_ITEMS[Role.FULL_WINDOW]` gives the exact item names. If you want a worked example,
generate one from the contract; do not read an answer.

The `window_idx` field equals `<WINDOW_IDX>`, and so does `target.trigger_idx` in every
check: the contract will not let you save a review in which you judge somebody else's
window. Otherwise the coordinator, handed nine files, could not tell nine reviews of nine
windows from nine reviews of one and the same window.

**There must be a line in `checks` for every one of the five items of your mode** —
`window-can-be-tightened`, `author-says-answer-in-window`,
`event-not-earlier-than-window`, `depends-on-is-dependency`, `evidence-span-is-last` —
including the ones that did not fire (`ok`) and the ones that do not apply (`na`, for
example `depends-on-is-dependency` on a window with no `depends_on`). A missing line is
indistinguishable from a completed check. The exact list is `ROLE_ITEMS[Role.FULL_WINDOW]`
in the contract. Each line names its `group`: `windows` for the first two items,
`triggers` for `event-not-earlier-than-window`, `labels` for the last two; its `target`
is `{"trigger_idx": <WINDOW_IDX>}`. A `skipped` line names the unchecked stretch in
`uncovered`.

Items are addressed **by name**, not by number: the numbers in this prompt are labels for
reading and may change, and a review saved under the key `"2.4"` reads, after a reordering,
as a review of a different item.

Every check is filled in **top to bottom, in field order**, and that is not a formality:

1. `looked_at` — the frames and lines of speech the conclusion rests on;
2. `findings` — what you saw, as facts and without judgement;
3. `criterion` — which criterion of the item you are applying, **in your own words**. A
   restatement exposes a misunderstanding, a quotation from this prompt hides it;
4. `steps` — the intermediate answers the verdict is assembled from. Phrase them so they
   can be checked: not "is the window all right" but "the last frame in which the object
   is still changing";
5. `split`, on item 2.5 only;
6. and only now `result`, `confidence`, `proposal`.

The order exists so that the verdict comes out of the grounds rather than the grounds
being chosen to fit the verdict. The side benefit matters more than the direct one: when
two reviewers disagree, `steps` shows **at which step** they diverged.

Every `fail` carries a `proposal`: `field` names what to change (`t_start`, `t_end`,
`evidence_span`, `depends_on`, `reasoning_level`, `question`, or `window` with the value
`remove`), `value` what to change it to, and `why` begins with the verdict the item names
(`FIX_INTERVALS: …`). The overall `verdict` equals the worst of the ones that fired:

| Verdict | When |
|---|---|
| `PASS` | nothing fired and nothing was skipped |
| `FIX_INTERVALS` | window boundaries, `evidence_span`; on item 2.5, what the rules above send there |
| `FIX_QUESTION` | the window cannot be fixed by boundaries: the design of the question does not work at this moment; `depends_on`; on item 2.5, a changed level and what the rules above send there |
| `CRITICAL_FAIL` | only on item 2.5, where its rules send it: a required window with an empty residue on `L2`/`L3`, or a required `predict` window that contains the author's reveal, unless a new `t_end` cures it or the revealed items can leave the rubric with something still to predict; an optional window with an empty residue whose items a later required window scores |

**The tolerance on boundaries** (the definition above). A `t_start` or `t_end` you measured
within 2 s of the annotated one: `fail` with `FIX_INTERVALS`, your value in `proposal`, and
say in `findings` that the gap is within the tolerance — the coordinator moves the boundary
without another review. Two exceptions: a cut of 2 s or less is not proposed at all (item
2.4), and an `evidence_span` whose bounds are each within 2 s of where you would put them
stays as annotated — `ok`, with your values in `findings`. A gap over 2 s: `fail` with
`FIX_INTERVALS` and your measured value, or the verdict the item itself names (item 2.5).
No result may hinge on 2 s or less: a residue of item 2.5 or an onset of item 3.3 that
flips only when an edge moves by that much is read as you first measured it, and the
closeness is written in `findings`.

`budget`: `frames_viewed` — the images you opened, a sheet counting as one;
`dense_intervals` — the stretches of your `--dense` calls; `screen_index_used: true` if you
searched the index.

The contract will not let you set `PASS` while items have fired or been skipped.

Check yourself before reporting:

```bash
/home/user/conda/bin/python3 schema/review.py --check \
    data/reviews/<VIDEO_ID>/<SAMPLE_ID>/full_window<WINDOW_IDX>.<ROUND>.json
```

Fix and run again — hand the coordinator only what passed.

### 2. The text for the coordinator

Not a retelling of the json but your reasoning: what you checked, what you found, where
you are unsure and why, what you advise re-checking. At the end — the path to the saved
file.

If you found nothing — say so. `PASS` is a legitimate verdict, and inventing remarks for
the sake of looking busy is harmful: each one launches an extra round of fixes.
