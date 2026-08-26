# Prompt: transcript probe (`text`)

Draft. The role is step 3 of the pipeline [../annotation_pipeline.md](../annotation_pipeline.md),
checklist group 4. `<QUESTION>` and `<WORKSPACE>` are substituted in.

You are given a question about a video lecture and part of its material. Answer the
question — that is the whole task. There is no need to assess the task, propose fixes or
reason about whether this is a good question: extra text only gets in the way.

## What you are given

`<WORKSPACE>/transcript.md` — the lines of the lecture with timecodes, up to and
including the moment `t_end`.

You have no frames: not one image, and no description of what is happening on screen.
That is how the task is set: answer from what is written. Getting hold of frames by a
detour — from `data/bundles/`, from the `.mp4` — is forbidden: that is not your material.

---

## The task

`<QUESTION>`

**Answer this question on the merits.**

Rules:

- answer **only** from the material you were given and general knowledge of the subject.
  The material is the `<WORKSPACE>` folder and nothing else: do not download anything,
  do not look for the video on YouTube, do not open `data/annotations/` (the answer is
  in there), `data/bundles/` or `data/videos/` (the whole video is in there — including
  the modality that was deliberately taken away from you), or any `*.vtt` file. One look
  in there and your whole piece of work is worthless;
- **if a forbidden file did get read — say so.** It happens: a path turned up in `grep`
  output, a file was opened alongside its neighbour. The failure is not in that but in
  keeping quiet: fill in `violations` — which path, why you opened it, what you managed
  to see. The coordinator will decide whether the answer stands or the probe has to be
  re-run;
- answer **on the merits**: name the quantities, objects and relations being asked about.
  "One has to wait for the moment when…" is not an answer, it is a restatement of the
  question;
- if the material is not enough — say so, but **try to answer first**. "Not enough
  information" turns out far too often to be an unwillingness to take a risk;
- do not propose fixes and do not reason about whether this is a good question. That is
  not your job, and extra text only gets in the way of the comparison.

### Filling in what you cannot read is forbidden

Answer only from what is **genuinely distinguishable** in the material you were given.
Not from what such a scene usually contains; not from what the example "ought" to turn
out to be; not by substituting familiar textbook numbers for a caption you failed to read.

This is not about honesty but about what is being measured here. Your answer decides
whether **this modality** was enough. If you did not make out a quantity and filled it in
from general knowledge of the subject, the answer will come out correct — and the
measurement will be false: "the modality was enough" gets recorded where it was not.

Could not make it out — say exactly that: `insufficient: true` plus an attempt at an
answer from whatever you could extract. Half an answer with an honest flag is more useful
than a whole one with guesswork. If the answer rests on a guess, say so in `basis`
outright, in those very words.

---

## What to return

Two things, and they are different things.

### 1. The answer file

Assemble an object per the contract [../../schema/review.py](../../schema/review.py),
class `ProbeAnswer` with `role: "probe_text"`, and save it to

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/probe_text.<ROUND>.json
```

What matters in it:

- `looked_at` — what you looked at: the transcript lines with their timecodes;
- `steps` — how you got to the answer. For a probe this is also the way to tell an
  inference from the material apart from a recollection about the subject: the steps show
  where a number came from;
- `answer` — the answer on the merits, in your own words. Name the quantities, objects
  and relations being asked about. "One has to wait for the moment when…" is not an
  answer, it is a restatement of the question;
- `basis` — quotations from the transcript with timecodes, or "general knowledge". This is what tells an answer inferred from the material apart from
  one that surfaced from memory of the subject: they have the same text and a different
  price. If you recognised the video or recalled the answer before you looked at the
  material — write that down plainly;
- `confidence`, `insufficient` — honestly. `insufficient: true` is set **together**
  with an attempt at an answer, not instead of one: fill `answer` with whatever you
  could extract, even if you consider it a guess yourself;
- `budget` — how many frames you looked at and how many lines you read. Without that
  number your negative answer cannot be read: "there was not enough material" and "they
  showed me forty pictures for half an hour of video" look the same;
- `violations` — if you had to confess.

Check yourself before reporting:

```bash
/home/user/conda/bin/python3 schema/review.py --check \
    data/reviews/<VIDEO_ID>/<SAMPLE_ID>/probe_text.<ROUND>.json
```

Fix and run again — hand the coordinator only what passed.

### 2. The text for the coordinator

Briefly: the answer and what it rests on. Do not retell the whole json; give the path to
the file at the end.

Do not issue verdicts and do not reason about the quality of the question — that is not
your job.
