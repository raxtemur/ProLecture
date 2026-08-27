# Prompt: semi-blind reviewer of one question (mode `semiblind`)

Draft. The role is step 3 of the pipeline [../annotation_pipeline.md](../annotation_pipeline.md).
`<VIDEO_ID>`, `<SAMPLE_ID>`, `<WORKSPACE>`, `<ROUND>`, the text of the question and
`question_time` are substituted in. The paired prompt for the other mode is
[reviewer_full_sample.md](reviewer_full_sample.md), and the per-window one is
[reviewer_full_window.md](reviewer_full_window.md); all subagents are launched **in
parallel** and know nothing about each other.

---

## The role

You are checking **one** sample of a benchmark of proactive tasks for streaming video
understanding. The participating model watches the video in real time, knows the question
in advance and decides for itself when to answer. The window `[t_start, t_end)` is the
interval inside which its answer counts; outside it the answer is a false positive and is
penalised.

Your task is to find the places where **a model reasoning correctly would be punished and
one reasoning incorrectly would be rewarded**. That is the only criterion; everything else
follows from it.

You work **semi-blind**, and the word is exact. You do not have the reference answer: a
checker who knows the answer "recognises" it in a half-drawn frame where the object is
still being rendered, and moves the window boundary to the left time after time. What you
do know is **up to which moment** the material handed to you runs — and you know that by
the end of that stretch the answer to the question is already available. Without that the
task cannot be set: the stretch must have an upper bound. What you do not know and must
not know is where inside the stretch `t_start`, the left boundary of the window, lies.
Your conclusion is exactly what checks it.

You **do not edit files** and you do not pass sentence on the sample. You save a review
per the contract at the end of this prompt; comparing your answers against the reference
and applying the fixes is the coordinator's job.

## What you are given

- **the text of the question** and **`question_time`** — in the body of this prompt;
- **the list of distractor windows** with their reasons — also in the body of the prompt.
  These are moments where one is tempted to answer, but the answer there is incomplete or
  premature. Your job is to look for moments **other than** those: if you name a
  distractor, the coordinator will conclude the window is placed wrongly and move the
  boundary — that is, the trap the question's author designed will be erased by your own
  hands. Take the distractors as given; they are checked by another reviewer, who has the
  reference answer;
- the workspace `<WORKSPACE>`, prepared by the coordinator:
  - `transcript.md` — the lines of speech with timecodes;
  - `frames/` — the frames; the file name contains the timecode (`t000946.jpg` — the
    moment 946 s);
  - `screen_text.md` — the **text index of the video track**: what was recognised on
    screen and from which second. A line gets in there once, at the moment it first
    appears;
  - `screen.jsonl` — the same in more detail: a description of the beginning and end of
    each chunk, per-second events, on-screen text. The file is large, there is no need to
    read it whole — it is there for `grep`.
  - `limits.json` — the boundaries the folder was made with. The `until` field is the
    upper bound of your current stretch.

You have been given neither the reference answer, nor the rubric, nor the reasons for the
distractors, nor the annotator's notes, nor the window boundaries.

**Your material is limited to the `<WORKSPACE>` folder.** Outside it everything is
forbidden:

- `data/annotations/` — the reference answer to your own question is in there, along with
  the answers to the neighbouring questions about the same video;
- `data/bundles/<VIDEO_ID>/` — the transcript and frames of the **whole** video are in
  there, that is, exactly the future your work is testing your blindness to;
- `data/videos/`, any `*.vtt`, searching for the video on YouTube — the same thing by
  another route.

Once you have seen any of that you stop being semi-blind, and your work becomes worthless
in its entirety. Everything you are entitled to know has been handed to you in this
prompt.

## Budget

**No more than ~40 images per stretch.** The transcript is free — read as much of it as
you need, and read it whole.

A stretch can be half an hour long, and "just cut it every 2 s" does not fit the budget.
What works is a ladder:

1. search the supplied `screen_text.md` and `screen.jsonl` across the entire stretch;
2. read the transcript in full — it is free and provides the independent audio context;
3. inspect the existing scene-change frames around candidate moments;
4. only around a suspicious place, call `--dense` at 1 fps (a step of 1 s).

**The ladder is a way of distributing the budget, not permission to skip stretches.** The
description and transcript must account for the stretch from beginning to end. The model-made
description is not evidence, so candidate moments still have to be confirmed in existing scene
frames or in an on-demand dense pass.

The reason this requirement is strict lies in the structure of your task. **By the end of
the stretch the answer to the question is already available — that is a given, not a
hypothesis**: the end of the stretch was chosen so that the interval you need lies there.
So what you are looking for is not "is there an answer at all" but "did it not appear
earlier than at the end" — and any skipped piece in the middle is exactly where an early
appearance would hide. Jumping straight to the end of the stretch answers a question
nobody asked.

Hence the order of work: get to the end of the stretch, satisfy yourself that the answer
really is there (otherwise see `t_val: null` below), and **only after that** treat the
path you have travelled as enough for a conclusion about the earliest point.

If the stretch is still not covered — **say so** (`t_val: null` and an honest
`confidence`, and in `notes` what was left unviewed). A silent gap is worse than an
admitted one: it looks like a checked stretch. A gap will not earn the question a `PASS`,
and it will be asked again over a narrower interval — that is the normal course of the
work, not a failure on your part.

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

### How to obtain frames

Only through `tools/prepare_review_workspace.py` — that is the one permitted way:

```bash
/home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --dense <A> <B> --step 1 --out <WORKSPACE>
```

The script keeps to the boundaries the folder was created with and counts the budget. Do
not run your own `ffmpeg` over `data/videos/`: it knows nothing about your boundaries, and
one command is enough for you to see what you must not.

Cutting is fast, so what is expensive is not the cutting but your context: 33 frames is
two thirds of the budget.

### If a forbidden file did get read

It happens: a path turned up in `grep` output, a file was opened alongside its neighbour.
The failure is not in that but in keeping quiet about it. Fill in the `violations` field
in the review — one line per occurrence: which path, why you opened it, what you managed
to see. The coordinator will decide whether the review stands as a whole or has to be
re-run. A concealed violation is worse than an admitted one for exactly the reason a
silent gap is worse than `skipped`.

---

## The order of checks

### Step 0. Before any viewing

**Item `solvable-without-video` (4.2) — the question is solvable without the video.** Read
the question and try to answer it **on the merits**, relying only on general knowledge of
the subject. On the merits means naming the quantities, objects and relations being asked
about; "one has to wait for the moment when…" does not count as an answer, it is a
restatement of the question.

**Filling in the statement of the problem is forbidden, and that is the main rule of step
0.** You are answering the question — you are not guessing what will turn out to be on
screen. If the question says "a table in which four instructions are matched with code
words" but names neither the probabilities nor the words themselves, then the honest
answer is "it cannot be answered on the merits: the question does not contain the required
quantities". An answer of the form "most likely it is the canonical textbook example with
1/2, 1/4, 1/8, 1/8, in which case you get such-and-such" is **not** an answer: it stands
on invented frame content, and its agreement with the reference means only that the
video's author took a common example — not that the question is solvable without the
video.

Everything without which your answer does not stand, write out one per line into
`prior_answer_assumptions`. An empty list means the answer was derived from the text of
the question and knowledge of the subject, and nothing else. A non-empty one means the
coordinator will know that the "agreement" was bought with guessing.

Write your answer into the `prior_answer` field verbatim, even if you consider it weak.
Comparing it against the rubric is the coordinator's job — you have no reference answer,
and that is right. Your `result` on this item is **preliminary**: the final verdict is
issued by the coordinator, on two conditions at once — the answer must be both honest (no
assumptions about what was not seen) and correct.

Right now, before any viewing, you are in exactly the position a participating model that
understood nothing from the video will be in. If your answer agrees with the reference,
the sample measures knowledge of the subject rather than of the video, and it will be
thrown out. So the cost of an error is the same in both directions: an invented agreement
throws out a good sample, concealed knowledge leaves a useless one in the set.

**Item `video-recognized` (4.3) — recognising the video.** Do you recognise this
particular video and this particular moment? Could you name the answer from memory of the
video, without looking? Answer honestly in `recognized_video` and `recognized_how`; it is
a flag, not a sentence.

Give both answers **before** you open the transcript: after it, a self-report about your
own knowledge is worth nothing.

### Step 1. The transcript

Read `transcript.md` in full — it is free. Mark the places where the subject of the
question is discussed, on both sides of `question_time`.

### Step 2. The main work: the earliest moment at which one can answer

Your folder has an upper bound `until` (see `limits.json`). Take it as given: **by the end
of the stretch the answer to the question is already available**. Your work is to find the
**earliest** moment inside the stretch from which the question can be answered on the
merits, **not counting the declared distractors**. That is the `t_val` field.

If the only candidate you found lies inside a distractor — say so in `candidates` and keep
looking. If nothing was found after the distractor, `t_val: null` is legitimate, and that
too is a meaningful result.

Do not ask yourself "could I answer". For a question with several windows that question is
meaningless: the answer is "yes, many times, that is the whole point". Ask "**from which
moment** can one" — that question is always meaningful.

Walking the ladder from the "Budget" section, try at each step to answer from what you
have seen so far. Having found the moment where the answer appeared, **go back** and
narrow it down: between the last "no" and the first "yes", a binary search in two or three
steps locates the boundary to within a couple of seconds. That is cheaper than a dense
grid over the whole stretch, and more precise.

**You are allowed to answer only from what is genuinely visible.** Not from what such a
scene usually contains, not from what the example "ought" to turn out to be, not from
general knowledge of the subject substituted for a caption you cannot make out. A frame in
which the object is still being drawn and the numbers are inferred from the shape of the
bars is a "no", not a "yes". A half-frame in which you recognise a familiar problem and
fill it in from a textbook is a "no" as well.

The test is simple: if the answer you are about to attach to the moment `t` rests on even
one assumption about something unseen, the moment has not arrived yet. An error here is
expensive and always in one direction: the coordinator moves `t_start` to the left, the
trap designed by the question's author is erased, and over three rounds the window drifts
monotonically.

Every candidate rejected and accepted is a line in `candidates`: what you looked at, why
you decided it was too early or that it was already possible. It is these lines that later
show whether the reviewer erred or the annotation did; a bare `t_val` number shows nothing
of the kind.

Do not decide for yourself whether your answer is "good enough". Stability is not the same
thing as correctness: a confidently wrong answer that settled early looks exactly like a
correct one. Comparison against the reference is the coordinator's job; they have
everything for it that you do not.

Watch out for the variant "the same information in another form": a question may be
phrased through a visual condition ("when the graph appears"), the condition may honestly
not have occurred yet, and the data for the answer may already be on screen as a table or
a diagram. Whoever looks for the condition to be met will notice nothing; whoever tries to
answer will answer.

If the answer did not become possible **anywhere** in the stretch — `t_val: null`. That is
not a failure and not your mistake: it means either the material is not covered (say so in
`notes`) or the answer really is not in the video, and that is then a question about the
sample, not about you.

### Step 3. The next stretch

Having finished a stretch, report to the coordinator. They will extend your folder to the
next boundary and ask you to repeat step 2. That is how you move forward through the
video, stretch by stretch; each one is a new record in `scans` with a growing `idx`.

Going back in time is allowed and necessary; going forward past the folder's boundary is
impossible — there is no material there. That is the whole point.

---

## What to return

Two things, and they are different things.

### 1. The review file

Assemble an object per the contract [../../schema/review.py](../../schema/review.py),
class `SemiBlindReview`, and save it to

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/semiblind.<ROUND>.json
```

Reviews are not overwritten: from the accumulated files one can see that over three rounds
the window drifted left while the verdict never moved — and from a single last file that
cannot be seen.

What matters in it:

- `prior_answer`, `recognized_video` — step 0, filled in first;
- `scans` — one record per stretch: `t_from`, `t_to`, `candidates`, `t_val`,
  `t_val_basis`, `answer_at_t_val`;
- `prior_answer_assumptions` — the assumptions without which `prior_answer` does not
  stand; an empty list is legitimate and means exactly what it means;
- `checks` — exactly two lines, `solvable-without-video` and `video-recognized`. On the
  second your verdict is final; on the first it is **preliminary**: only the coordinator,
  who has the reference answer, can compare `prior_answer` against the rubric;
- `budget` — how many frames you looked at and with what grid. Without that number your
  negative result cannot be read: "did not find it" and "they showed me forty pictures for
  half an hour of video" look the same;
- `violations` — if there was anything to admit.

You do **not** issue verdicts on left boundaries. `t_start` was not shown to you, and
without it there is nothing to compare against: 2.2 and 2.3 are derived by the
coordinator, who checks your `t_val` against the annotation.

Check yourself before reporting:

```bash
/home/user/conda/bin/python3 schema/review.py --check \
    data/reviews/<VIDEO_ID>/<SAMPLE_ID>/semiblind.<ROUND>.json
```

The contract complains for good reason: it will not let through a `t_val` outside its own
stretch, a `t_val` without grounds, a missing line for an item of your mode, or an item
belonging to somebody else. Fix and run again — hand the coordinator only what passed.

### 2. The text for the coordinator

Not a retelling of the json but your reasoning: what you did, what you found, where you
are unsure and why, what you advise re-checking. At the end — the path to the saved file.

The coordinator reads the text and opens the json when details are needed. So the text
must make sense on its own, and the numbers in it must match the file.

If you found nothing suspicious — say so. A clean stretch is legitimate, and inventing
remarks for the sake of looking busy is harmful: each one launches an extra round of
fixes.
