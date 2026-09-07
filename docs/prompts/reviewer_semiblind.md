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
and applying the fixes is the coordinator's job. That is also why you are asked for
**answers, at every step, and not for a verdict**: you have nothing to check an answer
against, and a confidently wrong answer that settled early looks to you exactly like a
right one. The coordinator has the rubric and will check every answer you write.

## What you are given

- **the text of the question** and **`question_time`** — in the body of this prompt;
- the workspace `<WORKSPACE>`, prepared by the coordinator:
  - `transcript.md` — the lines of speech with timecodes;
  - `frames/` — the scene frames: one per change of the screen's content, cut by a scene
    detector, about a dozen per minute; the file name contains the timecode
    (`t000946.jpg` — the moment 946 s);
  - `screen.jsonl` — the **description of the video track**, chunk by chunk: what the
    screen looks like at the beginning and the end of each five-second chunk, the
    per-second events, the recognised on-screen text. This is your main material for the
    stretch after `question_time`: **read it in full**, in order, the way you read the
    transcript. On the pilot videos that is about 8 KB per twenty seconds of video;
  - `screen_text.md` — the recognised text as a timeline: a line gets in there once, at
    the moment it first appears. A quick way to see *when* a formula or a number came up;
  - `limits.json` — the boundaries the folder was made with. The `until` field is the
    upper bound of your current stretch.

You have been given neither the reference answer, nor the rubric, nor the annotator's
notes, nor the window boundaries — and nothing that would let you infer any of them.

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

**No more than ~40 images per stretch.** The transcript and the description are free —
read as much of them as you need, and read them whole.

A stretch can be half an hour long, and "just cut it every 2 s" does not fit the budget.
What works:

1. read the transcript of the stretch in full;
2. read the description (`screen.jsonl`) **in full** over `[question_time, until]`, and skim
   it before `question_time` — the material before the question is there so that the
   coordinator can check whether the answer was available before the question was even
   issued;
3. at every moment where the state of the screen or the speech **relevant to the task**
   changed, write down a full answer from what is available up to that moment (see step 2);
4. look at the scene frames in `frames/` around those moments;
5. only where you call a moment sufficient, or where the description is ambiguous (the
   middle of an animation, a number you cannot trust), call `--dense` at 1 fps and confirm.

**This is a way of distributing the budget, not permission to skip stretches.** The
description and the transcript must account for the stretch from beginning to end.

The reason this requirement is strict lies in the structure of your task. **By the end of
the stretch the answer to the question is already available — that is a given, not a
hypothesis**: the end of the stretch was chosen so that the interval you need lies there.
So what you are looking for is not "is there an answer at all" but "did it not appear
earlier than at the end" — and any skipped piece in the middle is exactly where an early
appearance would hide. Jumping straight to the end of the stretch answers a question
nobody asked.

Hence the order of work: get to the end of the stretch, answer there (that answer is
mandatory — without it the coordinator cannot tell "too early everywhere" from "stopped
looking"), and let the trajectory you wrote on the way be the evidence about the earliest
point.

If the stretch is still not covered — **say so** (`t_val: null`, an honest `confidence`, and
in `notes` what was left unviewed). A silent gap is worse than an admitted one: it looks like
a checked stretch. A gap will not earn the question a `PASS`, and it will be asked again
over a narrower interval — that is the normal course of the work, not a failure on your
part.

### The screen description: material to read, not evidence to cite

`screen.jsonl` and `screen_text.md` were made **by a model** from the frames, not by a
human. That changes what they are for, and the difference is hard:

- **allowed, and expected** — reading them as material. The description says what is on
  screen second by second; answering from it is how you cover a twenty-minute stretch
  without twenty minutes of frames;
- **not allowed** — citing them as proof. Before a moment you call sufficient goes into the
  review, it must be **seen in a real frame**. Recognition makes mistakes: it confuses
  similar digits, loses what is shown in passing and finishes off things that are not
  there. A number or a verbatim text taken from the description is confirmed on a frame
  before you rely on it.

What goes into `looked_at` of a sufficient point is a frame you opened, not a line of the
description. A review whose conclusion rests on a description alone is the same guesswork
as a caption filled in from a textbook, only with somebody else's hands.

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

**Write the content, not a statement about the content.** "I know only the general
Lagrangian derivation of the logarithm" is not an answer — the derivation itself is, chain
by chain, followed by whatever caveat you have. The coordinator scores `prior_answer`
against the rubric item by item; a sentence *about* your knowledge scores nothing, and a
sample that is in fact solvable blind then stays in the set.

A caveat about what you cannot know — the notation on the screen, a colour, the exact
wording — is not an assumption about content and does not go into
`prior_answer_assumptions`. That list is for assumptions **without which the answer would
be wrong**: "the screen shows the standard example 1/2, 1/4, 1/8, 1/8". "Which colour
they gave the term I cannot say" is a caveat; write it after the content.

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

### Step 2. The main work: a full answer at every change of state

Your folder has an upper bound `until` (see `limits.json`). Take it as given: **by the end
of the stretch the answer to the question is already available**. Your work is to walk the
stretch and, at **every** moment where the state of the screen or the speech relevant to
the task changed, write a **complete answer** to the task from what is visible and audible
up to that moment. Each such moment is a `Candidate` record in `scans[].candidates`: the
moment `t`, the answer, whether you yourself consider it sufficient, what changed there,
and the frame it rests on if you call it sufficient. The last record is at the end of the
stretch.

"Not yet answerable" is a legitimate answer — but then say **what exactly is missing**:
which quantity, which object, which relation. "The condition of the question has not
occurred yet" is not an answer to that: the question may be phrased through a visual
condition ("when the graph appears"), the condition may honestly not have occurred, and
the data for the answer may already be on screen as a table or a diagram. Whoever looks for
the condition to be met notices nothing; whoever tries to answer answers. So at every point
**try to answer**, and note the condition separately if you like.

Do not ask yourself "could I answer". For a question with several windows that question is
meaningless: the answer is "yes, many times, that is the whole point". Ask at every point
"**what** can I answer from here" — and write it down.

**You are allowed to answer only from what is genuinely visible or audible.** Not from what
such a scene usually contains, not from what the example "ought" to turn out to be, not
from general knowledge of the subject substituted for a caption you cannot make out. A
frame in which the object is still being drawn and the numbers are inferred from the shape
of the bars gives an answer with `sufficient: false` and a note of what is inferred. A
half-frame in which you recognise a familiar problem and fill it in from a textbook — the
same. The test is simple: if the answer you are attaching to the moment `t` rests on even
one assumption about something unseen, say so in the record.

**Do not decide for yourself whether an answer is "good enough", and do not stop at the
first one you find convincing.** Stability is not correctness: a confidently wrong answer
that settled early looks exactly like a correct one, and you have nothing to check it
against. Write the answer, mark your own view in `sufficient`, and move on to the next
change of state until the end of the stretch. The coordinator, who has the rubric, will
check every record and decide which is the first that passes; your `t_val`, `t_val_basis`
and `answer_at_t_val` are your own view and are recorded as such.

Where you call a point sufficient, confirm it on a real frame and put that frame into the
record's `looked_at`. Where the description is ambiguous — the middle of an animation, a
digit you cannot trust — take a dense pass at 1 fps over a few seconds and settle it.

If at no point of the stretch could you answer — `t_val: null`, with the trajectory of
"not yet" answers still written down. That is not a failure and not your mistake: it means
either the material is not covered (say so in `notes`) or the answer really is not in the
video, and that is then a question about the sample, not about you.

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
- `checklist_version` — write `"2026-09-07"` explicitly. A review that does not state its
  version is read under the previous checklist, and the contract will then accept a shape
  of `candidates` that is no longer wanted;
- `scans` — one record per stretch: `t_from`, `t_to`, the trajectory `candidates` (a
  `Candidate` per change of state, each with a full answer; the last at the end of the
  stretch), and your own view in `t_val`, `t_val_basis`, `answer_at_t_val`;
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

The contract complains for good reason: it will not let through a trajectory that does not
reach the end of the stretch, a point called sufficient with no frame behind it, a `t_val`
outside its own stretch, a `t_val` without grounds, a missing line for an item of your
mode, or an item belonging to somebody else. Fix and run again — hand the coordinator only what passed.

### 2. The text for the coordinator

Not a retelling of the json but your reasoning: what you did, what you found, where you
are unsure and why, what you advise re-checking. At the end — the path to the saved file.

The coordinator reads the text and opens the json when details are needed. So the text
must make sense on its own, and the numbers in it must match the file.

If you found nothing suspicious — say so. A clean stretch is legitimate, and inventing
remarks for the sake of looking busy is harmful: each one launches an extra round of
fixes.
