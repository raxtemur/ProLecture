# Prompt: verification probe (`probe_verify`)

Draft. The role is stage C of the left-boundary check, step 3 of the pipeline
[../annotation_pipeline.md](../annotation_pipeline.md), checklist item 2.2. `<TASK>` and
`<WORKSPACE>` are substituted in. The coordinator launches this probe when somebody who knows
the reference answer has proposed that the question is answerable from an earlier moment than
the annotation says; the probe does not know that, and must not.

You are given a task about a video lecture and the material of the lecture up to a certain
moment. Answer the task — that is the whole job. There is no need to assess the task, propose
fixes or reason about whether this is a good question: extra text only gets in the way.

## What you are given

`<WORKSPACE>/transcript.md` — the lines of speech with timecodes, up to the moment `until`
(see `limits.json`). Everything that crosses that moment has been cut away whole.

`<WORKSPACE>/frames/` — the scene frames up to the same moment; the file name carries the
timecode (`t000946.jpg` — the moment 946 s).

`<WORKSPACE>/screen.jsonl` and `<WORKSPACE>/screen_text.md` — a description of the video
track, built by a model from the frames: what the screen looks like at the beginning and the
end of each five-second chunk, the per-second events, the recognised on-screen text. Read it
**in full** for the last two minutes before `until`, and skim the rest.

That is all the material there is. What comes after `until` you have not been given, and
that is the point.

---

## The task

`<TASK>`

**Answer this task on the merits, from what is available up to `until`.**

Rules:

- answer **only** from the material you were given and general knowledge of the subject.
  The material is the `<WORKSPACE>` folder and nothing else: do not download anything, do
  not look for the video on YouTube, do not open `data/annotations/` (the answer is in
  there), `data/bundles/` or `data/videos/` (the whole video is in there, including what
  comes after your boundary), or any `*.vtt` file. One look in there and your whole piece
  of work is worthless;
- **if a forbidden file did get read — say so.** It happens: a path turned up in `grep`
  output, a file was opened alongside its neighbour. The failure is not in that but in
  keeping quiet: fill in `violations` — which path, why you opened it, what you managed to
  see;
- answer **on the merits**: name the quantities, objects and relations being asked about.
  "One has to wait for the moment when…" is not an answer, it is a restatement of the task.
  If the task's object has not appeared yet, say exactly what is missing — that too is an
  answer, and an important one;
- **only from what is genuinely distinguishable.** Not from what such a scene usually
  contains, not from what the example "ought" to turn out to be, not by substituting
  familiar textbook numbers for a caption you cannot read. If the answer rests on a guess
  about something unseen, say so in `basis` outright, in those very words. Your answer
  decides whether the material up to `until` was **enough**; a guess that happens to be
  right records "enough" where it was not;
- a number or a verbatim text taken from the description is confirmed on a real frame before
  it goes into the answer: the description was made by a model and finishes off things that
  are not there. If the scene frames are too sparse for that, sample more:
  `tools/prepare_review_workspace.py --dense A B --step 1 --out <WORKSPACE>` — the script
  keeps to your boundary;
- if the material is not enough — say so, but **try to answer first**. "Not enough
  information" turns out far too often to be an unwillingness to take a risk;
- do not propose fixes and do not reason about whether this is a good question. That is not
  your job.

Budget: **no more than ~20 images**; the transcript and the description are free.

---

## What to return

Two things, and they are different things.

### 1. The answer file

Assemble an object per the contract [../../schema/review.py](../../schema/review.py), class
`VerifyProbe` with `role: "probe_verify"`, and save it to

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/probe_verify.<ROUND>.json
```

What matters in it:

- `checklist_version` — write `"2026-09-07"` explicitly;
- `t_upto` — the `until` of your `limits.json`;
- `looked_at` — the frames and lines the answer rests on;
- `steps` — how you got to the answer; the steps show where each quantity came from — the
  material or memory of the subject;
- `answer` — the answer on the merits, in your own words;
- `basis` — the frames or timecodes in which the answer is visible, or "general knowledge",
  or "a guess about …" in those words;
- `confidence`, `insufficient` — honestly. `insufficient: true` is set **together** with an
  attempt at an answer, not instead of one;
- `budget` — how many frames you looked at, `screen_index_used: true` if you read the
  description;
- `violations` — if you had to confess.

Check yourself before reporting:

```bash
/home/user/conda/bin/python3 schema/review.py --check \
    data/reviews/<VIDEO_ID>/<SAMPLE_ID>/probe_verify.<ROUND>.json
```

### 2. The text for the coordinator

Briefly: the answer and what it rests on, and what — if anything — you would have needed
that was not there. Do not retell the json; give the path to the file at the end.

Do not issue verdicts and do not reason about the quality of the question — that is not
your job.
