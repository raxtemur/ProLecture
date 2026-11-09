# Prompt: frames-only probe (`vision`)

`<QUESTION>`, `<WORKSPACE>`, `<VIDEO_ID>`, `<SAMPLE_ID>` and `<ROUND>` are substituted in.

You are given a question about a video lecture and part of its material. Answer the
question — that is the whole task. There is no need to assess the task, propose fixes or
reason about whether this is a good question: extra text only gets in the way.

## What you are given

`<WORKSPACE>/frames/` — the frames of the lecture up to the moment `until` (see
`limits.json`). A frame's timecode is written in its file name: `t000946.jpg` — the moment
946 s.

`<WORKSPACE>/screen_text.md` and `<WORKSPACE>/screen.jsonl` — a text index of that same
video track up to the same moment, built by a model from the picture alone, without the
sound, on a denser grid than your frames. How to use it is below, in a section of its
own.

You have no transcript and no audio track — not one line of what the author says. That
is how the task is set: answer from what is visible. Getting hold of the text of the
speech by a detour — from `data/bundles/`, from the subtitles, by extracting the track
from the `.mp4` — is forbidden: that is not your material.

There may be a lot of frames. Look at as many as you need, but no more than forty.

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

### The screen index: something to search with, not to answer with

Besides the frames you have a text index of the same video track — it is built from the
picture alone, by a model, and it can misread:

- `screen_text.md` — what was recognised on screen and from which second; a line gets in
  there once, at the moment it first appears;
- `screen.jsonl` — in more detail: descriptions and per-second events. The file is large,
  there is no need to read it whole, it is there for `grep`.

Use it freely: it is the way to avoid paging through half an hour of video for the sake
of one caption. Once the index has found you the right stretch — **look at the real
frames there**, and answer from them.

Two rules, and both matter for what is being measured here:

1. **What you name must rest on a frame, not on a line of the index.** Recognition makes
   mistakes: it confuses similar digits, it finishes off things that are not there. If
   you name a quantity, you saw it — in a frame that is named in `looked_at`. Too few
   frames over the stretch you need — sample more for yourself, `<A>` and `<B>` being the
   first and the last second of the stretch:

   ```bash
   /home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
       --dense <A> <B> --step 1 --out <WORKSPACE>
   ```

   The script keeps to your boundary. A step of 1 s is the finest there is; keep the
   stretch short.
   For a quick look of up to 16 frames add `--sheet`: the script also tiles them into one
   image, `frames/sheet_<first>-<last>.jpg`, with the second stamped on each cell. Open
   that one image instead of the frames — a slow change (a fade, a morph) is
   visible only side by side — and open a single frame only to read small text.
2. **If you opened `screen_text.md` or `screen.jsonl`, set `screen_index_used: true` in
   `budget`.** A measurement with the index and one
   without it are not comparable, and they must be told apart by a mark rather than from
   memory.

A frame shows only its own moment. For the screen at another moment rely on the
index, and open that moment's frame only if the index looks inaccurate, incomplete or
silent on what you need; do not extrapolate from a neighbouring frame. A quantity or a
text you name still rests on a frame (rule 1). The frame at the last moment of your
material is always in the folder.

The index does not replace looking — it tells you where to look.

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

Outside `<WORKSPACE>` you write only the answer file below. Code, schemas, prompts,
documentation and every other file of the repository are not yours to edit, and scratch files
stay inside `<WORKSPACE>`. If a tool fails, or rejects your file and you believe the tool is
wrong, say so in the text for the coordinator with the command and its message, and do not
repair or work around the tool: the same tools check every other review.

Two things, and they are different things.

### 1. The answer file

Assemble an object per the contract `schema/review.py`, class `ProbeAnswer` with
`role: "probe_vision"`, and save it to

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/probe_vision.<ROUND>.json
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
- `looked_at` — what you looked at: the frames with their timecodes;
- `steps` — how you got to the answer. For a probe this is also the way to tell an
  inference from the material apart from a recollection about the subject: the steps show
  where a number came from;
- `answer` — the answer on the merits, in your own words. Name the quantities, objects
  and relations being asked about. "One has to wait for the moment when…" is not an
  answer, it is a restatement of the question;
- `basis` — the names or timecodes of the frames in which the answer is visible, or "general knowledge". This is what tells an answer inferred from the material apart from
  one that surfaced from memory of the subject: they have the same text and a different
  price. If you recognised the video or recalled the answer before you looked at the
  material — write that down plainly;
- `confidence`, `insufficient` — honestly. `insufficient: true` is set **together**
  with an attempt at an answer, not instead of one: fill `answer` with whatever you
  could extract, even if you consider it a guess yourself;
- `budget` — `frames_viewed` (a sheet counts as one), `dense_intervals` for every
  `--dense` call, and `screen_index_used`. Without these your negative answer cannot be
  read: "there was not enough material" and "they showed me forty pictures for half an
  hour of video" look the same;
- `violations` — if you had to confess.

Check yourself before reporting:

```bash
/home/user/conda/bin/python3 schema/review.py --check \
    data/reviews/<VIDEO_ID>/<SAMPLE_ID>/probe_vision.<ROUND>.json
```

Fix and run again — hand the coordinator only what passed.

### 2. The text for the coordinator

Briefly: the answer and what it rests on. Do not retell the whole json; give the path to
the file at the end.

Do not issue verdicts and do not reason about the quality of the question — that is not
your job.
