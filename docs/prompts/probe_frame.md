# Prompt: single-frame probe (`frame`)

`<QUESTION>`, `<WORKSPACE>`, `<VIDEO_ID>`, `<SAMPLE_ID>`, `<WINDOW_IDX>` and `<ROUND>` are
substituted in.

You are given a question about a video lecture and part of its material. Answer the
question — that is the whole task. There is no need to assess the task, propose fixes or
reason about whether this is a good question: extra text only gets in the way.

## What you are given

**One** frame: `<WORKSPACE>/frames/`, exactly one file. The timecode is written in the
name (`t000946.jpg` — the moment 946 s).

No transcript, no earlier frames, nothing about what came before in the video. That is
how the task is set: answer from this one frame.

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
- do not answer from memory of this video. If you recognise it, answer from the material
  anyway and say in `basis` that you recognised it. General knowledge of the subject may
  connect what the material shows; it may not replace it;
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
outright: "a guess about …".

If something you read on a frame looks malformed or does not fit the rest of the
material, read it again part by part before you conclude anything from it.

---

## What to return

Two things, and they are different things.

### 1. The answer file

Assemble an object per the contract `schema/review.py`, class `ProbeAnswer` with
`role: "probe_frame"`, and save it to

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/probe_frame<WINDOW_IDX>.<ROUND>.json
```

**The contract is the example — do not go looking for one in that folder.** The files
already sitting next to yours are other roles' *answers* to this same sample, including
probes on the other modalities and the full reviews that know the reference answer. Opening
one "just to see the shape of the JSON" is the commonest way a probe gets contaminated, and
a probe that has seen the answer measures nothing. `schema/review.py` is the specification:
read the pydantic class for your role. If you want a worked example, generate one from the
contract; do not read an answer.

What matters in it:

- `schema_version`, `checklist_version`, `iteration` — write `"1.4"`, `"2026-10-11"` and
  `<ROUND>` explicitly: a file that does not state its checklist version is read under
  older rules, and `--check` refuses it;
- `sample_id` = `<SAMPLE_ID>`, `workspace` = `<WORKSPACE>`, `model` — the model you run
  on, `date` — today: required, as in every file of the contract;
- `looked_at` — what you looked at: your single frame;
- `steps` — how you got to the answer. For a probe this is also the way to tell an
  inference from the material apart from a recollection about the subject: the steps show
  where a number came from;
- `answer` — the answer on the merits, in your own words. Name the quantities, objects
  and relations being asked about. "One has to wait for the moment when…" is not an
  answer, it is a restatement of the question;
- `basis` — what exactly in the frame gives the answer, or "general knowledge". This is what tells an answer inferred from the material apart from
  one that surfaced from memory of the subject: they have the same text and a different
  price. If you recognised the video or recalled the answer before you looked at the
  material — write that down plainly;
- `confidence`, `insufficient` — honestly. `insufficient: true` is set **together**
  with an attempt at an answer, not instead of one: fill `answer` with whatever you
  could extract, even if you consider it a guess yourself;
- `budget` — `frames_viewed: 1`;
- `violations` — if you had to confess.

Check yourself before reporting:

```bash
/home/user/conda/bin/python3 schema/review.py --check \
    data/reviews/<VIDEO_ID>/<SAMPLE_ID>/probe_frame<WINDOW_IDX>.<ROUND>.json
```

Fix and run again — hand the coordinator only what passed.

### 2. The text for the coordinator

Briefly: the answer and what it rests on. Do not retell the whole json; give the path to
the file at the end.

Do not issue verdicts and do not reason about the quality of the question — that is not
your job.
