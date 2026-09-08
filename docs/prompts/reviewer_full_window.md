# Prompt: per-window reviewer (mode `full_window`)

Draft. The role is step 3 of the pipeline [../annotation_pipeline.md](../annotation_pipeline.md).
`<VIDEO_ID>`, `<SAMPLE_ID>`, `<WORKSPACE>`, `<WINDOW_IDX>` and the sample itself are
substituted in. Working in parallel with you and knowing nothing about you are the
semi-blind reviewer ([reviewer_semiblind.md](reviewer_semiblind.md)), the sample reviewer
([reviewer_full_sample.md](reviewer_full_sample.md)) and one more per-window reviewer like
you for every **other** window.

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

You **do not edit files**. You return a review per the contract at the end of this prompt.
The fixes are applied by the coordinator.

**Why the role was split off.** All the checks used to be done by a single reviewer for
the whole sample. On a question with nine windows the frame budget was enough for the
first window, the rest went to `skipped`, and `skipped` forbids `PASS` — so the fix cycle
could not converge by construction. Now every window has its own reviewer and its own
budget.

**What you are not charged with.** The text of the question, the rubric, the `provenance`
references, the reference answer and the completeness of the trigger set are the sample
reviewer's work: they are common to all windows and there is nothing to divide them along.
The left boundary of the window (2.2, 2.3) is the semi-blind reviewer's work, with a
verified proposal from the sample reviewer: you know the reference answer and therefore
"recognise" it where it is not there yet. If along the way you notice a defect outside your list — write about it **in the text
for the coordinator**, but there is no line for it in `checks` and there must not be.

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

Take frames from `<WORKSPACE>` and only with the script. Do not touch `data/bundles/` and
`data/videos/` — not for the sake of secrecy but for the sake of the budget.

The `validation.notes` you were handed are the **hypotheses** of whoever did the
annotation, not evidence. Agreeing with their opinion confirms nothing.

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

- **allowed** — finding a moment. "Where does 1.75 appear on screen" becomes a single
  `grep` instead of an hour of viewing. Having narrowed the stretch down to a couple of
  seconds, you spend frames where they count;
- **not allowed** — citing them. Before you put a timecode into the review, the moment
  must be **seen in a real frame**. Recognition makes mistakes: it confuses similar
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
abruptly. If you need it denser —
`tools/prepare_review_workspace.py --dense A B --step S --out <WORKSPACE>`, as before.

### How to obtain frames

Only through `tools/prepare_review_workspace.py`:

```bash
/home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --dense <A> <B> --step 1 --out <WORKSPACE>
```

The script keeps to the boundaries the folder was created with. Do not run your own
`ffmpeg` over `data/videos/`: it knows nothing about your boundaries.

### If a forbidden file did get read

It happens: a path turned up in `grep` output, a file was opened alongside its neighbour.
The failure is not in that but in keeping quiet about it. Fill in the `violations` field —
one line per occurrence: which path, why you opened it, what you managed to see. The
coordinator will decide whether the review stands as a whole.

---

## The order of checks

First look at the sample's `reasoning_level`: the verdict on item 2.5 depends on it, and
that is the only thing you need to know in advance.

**Item 2.5 — the author speaks the answer inside the window or right after it.** Check
`[t_start, t_end + 10]` against the transcript and the frames. A model in streaming spends
several seconds on its answer, and in that time it will get whatever the author says next
out of the stream — so what matters is what the stream hands over in that interval.

Split the rubric in two and write the split into the `findings` of this check, item by
item: the items whose content is **handed over** — spoken or shown in finished form, a number, a term, a formula that can be
repeated — and the **residue**, what still has to be worked out from them.

- **Residue empty** — the whole answer is in the stream. For `L2`/`L3` this is a
  `CRITICAL_FAIL`: not cured by a boundary, cured by moving the question to where there are
  minutes of slack, by asking what the author does not say, or by converting the sample into
  an `L1` alarm. For `L1`, designed as an alarm in the first place, coinciding with the
  author's speech is fine: `ok`.
- **Residue not empty** — the stream hands over an ingredient (the four terms) but not the
  answer built from it (their sum). Mark the item `fail` with the verdict `FIX_QUESTION` and
  propose the level the residue deserves, as if the handed-over items only had to be heard:
  one step of arithmetic over displayed values is `L2`; a residue of nothing but reading is
  `L1`. The windows stay. A hedge in the wording ("show all four terms") does not change the
  split: judge what the stream shows, not what the question demands.

**Item 2.4 — the window can be tightened.** The answer must be possible throughout the
whole window. On the left the window is sometimes open while the object is still being
drawn, on the right after it has already left the screen. A slack of one or two seconds is
not worth a fix; propose tightening only if the empty part is large.

For a question explicitly asking about the state at its first appearance, later animation
does not erase the already observed answer. The minimum window provides generation latency:
do not tighten it below the legal minimum merely because the current frame advances while
the model may still be finishing an answer about that earlier state.

**Item 3.3 — the event does not begin earlier than its window.** If the trigger condition
is an event (the typical case is `monitor`, but not only), the window must open at the
moment the event begins, not when it is convenient to talk about it.

**Item 7.4 — `depends_on` means a dependency, not an order.** The field exists so that the
share of correctly built chains can be counted; filled in along neighbouring triggers in
sequence, it zeroes that metric out. Find in the rubric of **your** window an item that is
impossible to satisfy without the answer to the window named in `depends_on` ("names what
the new quantity was obtained from"). Not found — the link is superfluous. Check in the
other direction too: if such an item exists but the link does not, the window drops out of
the metric's denominator. This is text work and needs no frames.

**Item 7.5 — `evidence_span` points at the last piece of evidence.** The interval must
cover the moment the **last** fact needed for the answer appears, not the first one and
not the most conspicuous. It costs no frames: use what you already looked at for 2.4 and
2.5. An error here silently changes the `temporal_rel` axis.

Do not confuse evidence with corroboration. The moment where the author speaks the answer
themselves is corroboration; its place is in `provenance.evidence`, and for `predict` it
legitimately lies after the window. Ask "when did the answer become derivable", not "when
was it stated"; demanding that `evidence_span` reach as far as the corroboration is not
allowed.

---

## What to return

Two things, and they are different things.

### 1. The review file

Assemble an object per the contract [../../schema/review.py](../../schema/review.py),
class `FullWindowReview`, and save it to

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/full_window<WINDOW_IDX>.<ROUND>.json
```

Reviews are not overwritten: from the accumulated files one can see that over three rounds
of fixes the question is going round in circles, and from a single last file that cannot
be seen.

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
in the contract.

Items are addressed **by name**, not by number: the checklist numbering changes, and a
review saved under the key `"2.4"` reads, after a reordering, as a review of a different
item.

Every check is filled in **top to bottom, in field order**, and that is not a formality:

1. `looked_at` — the frames and lines of speech the conclusion rests on;
2. `findings` — what you saw, as facts and without judgement;
3. `criterion` — which criterion of the item you are applying, **in your own words**. A
   restatement exposes a misunderstanding, a quotation from the checklist hides it;
4. `steps` — the intermediate answers the verdict is assembled from. Phrase them so they
   can be checked: not "is the window all right" but "the last frame in which the object
   is still changing";
5. and only now `result`, `confidence`, `proposal`.

The order exists so that the verdict comes out of the grounds rather than the grounds
being chosen to fit the verdict. The side benefit matters more than the direct one: when
two reviewers disagree, `steps` shows **at which step** they diverged.

The overall `verdict` equals the worst of the ones that fired:

| Verdict | When |
|---|---|
| `PASS` | nothing fired and nothing was skipped |
| `FIX_INTERVALS` | window boundaries, `depends_on`, `evidence_span` |
| `FIX_QUESTION` | the window cannot be fixed by boundaries: the design of the question does not work at this moment; `author-says-answer-in-window` with a non-empty residue (a re-level) |
| `CRITICAL_FAIL` | `author-says-answer-in-window` on a sample of level `L2`/`L3` with an empty residue: the whole answer is in the stream |

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
