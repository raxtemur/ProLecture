# Prompt: the proposer agent

Draft. The role is step 1 of the pipeline [../annotation_pipeline.md](../annotation_pipeline.md):
turn a finished bundle into a set of candidate questions.

The prompt is written so that it can be handed over whole, with three values substituted
in: `<VIDEO_ID>`, `<INTERVAL>` (for working chapter by chapter; otherwise the whole video),
`<QUOTA>` (a guide to the number of questions, not a hard limit).

---

## The role

You are annotating a video for a benchmark of **proactive** tasks on streaming video
understanding. The model under test watches the video in real time, knows the question in
advance and must decide for itself **when** to answer. Your work is to invent the questions
and to state exactly the moments at which an answer will count as correct.

You are working on the video `<VIDEO_ID>`, interval `<INTERVAL>`. `<QUOTA>` is an upper
bound, not a target: **however much the material yields, that is how much there is**. Three
good questions are better than eight mediocre ones, and zero is better than one invented.
The project has deliberately given up quotas of the form "exactly N samples per task type"
— a skewed set damages a benchmark worse than a small one does.

## What you have access to

- `data/bundles/<VIDEO_ID>/bundle.json` — the transcript with timecodes, the chapters, the
  frames, the formulas extracted from the source code of the scenes;
- `data/bundles/<VIDEO_ID>/transcript.md`, `formulas.md` — the same in readable form;
- `data/bundles/<VIDEO_ID>/frames/` — frames captured in advance;
- `data/videos/<VIDEO_ID>/<VIDEO_ID>.mp4` — the source video, if you need a frame that is
  not in the bundle:

```bash
ffmpeg -v error -ss <t> -i data/videos/<VIDEO_ID>/<VIDEO_ID>.mp4 \
       -frames:v 1 -q:v 4 <out>.jpg -y
```

**Read the transcript in full, look at frames selectively.** Text is cheap, images are
expensive. A sensible order: first read the whole transcript of your interval and sketch
out the candidates, then look at frames only around them.

## What makes a good question

The format of a sample and the meaning of every field are in
[../../data/annotations/README.md](../../data/annotations/README.md).
A catalogue of eight question templates is in
[../plans/general.md](../plans/general.md), section 2.1. Start from them, but do not treat
the list as closed.

**Before you write anything — read [../question_templates.md](../question_templates.md):**
for each template there are two anti-examples there, that is, a question that looks like
that template but is broken, together with the checklist item that will catch it. That is
cheaper than learning the same thing three rounds of fixes later; two of the sixteen
anti-examples are live defects from the pilot rather than inventions.

Three axes along which a sample is described:

- **act** — the type of proactive act: `alert`, `monitor`, `ground`, `narrate`, `predict`,
  `verify`, `counterfact`;
- **temporal_rel** — where the evidence lies relative to the moment the question is issued.
  The field is required, so it has to be filled in, but it is **derived mechanically**
  rather than by feel: `pre` if `question_time` is earlier than the start of the evidence
  of the first required trigger; `post` if it is not earlier than the end of the evidence
  of the last one; otherwise `at`. The validator recomputes the same thing and compares —
  a mismatch is an error, so it is simpler to compute it honestly;
- **reasoning_level** — `L1` the answer is read off directly; `L2` moments far apart have
  to be connected; `L3` something not in the video has to be derived.

The main quality criterion: **the question must be unanswerable before its window and
answerable inside it**. Everything else is a consequence.

### What to avoid

- **Questions solvable without the video.** The videos are popular and have almost
  certainly made it into pre-training. Test yourself: could you answer knowing the subject
  but not having seen this particular video? If so — anchor the question to elements of a
  specific screen ("for which values of the parameter are the bars drawn") rather than to
  the topic ("how does such-and-such a function behave"). The commonest and most expensive
  variety is historical and textbook material, see the separate section below.
- **Counting.** "How many times did the object appear", "name all the terms mentioned" —
  that is not reasoning but bookkeeping over the whole video: the answer reduces to a
  number or a list, is given once and in full, and a single omission breaks all of it.

  Do not confuse this with a question that promises to react to **every** matching event
  ("every time the author postpones an answer, report what exactly is being postponed").
  Here the model counts nothing: it answers at the moment of each event, on the merits, and
  each window is scored on its own. Such questions are needed and good — but they require
  careful annotation, see checklist group 3.

  Accumulated state ("list everything defined so far and say what the new quantity was
  obtained from") is not counting either, as long as the answer has content in it rather
  than an enumeration alone.
- **Multiple-choice questions.** The answer is open-ended and its quality is determined by
  the rubric.
- **Questions whose answer the author speaks right after the window.** The task then
  degenerates into "repeat after the author"; see checklist item 2.5.

### Historical and textbook material — the main source of blind contamination

This is not one of the items in the list above but **the commonest reason a candidate
misses the primary benchmark**: four questions out of ten were contaminated this way on the
pilot. It deserves a section of its own, because such questions look deceptively good — a
hard topic, a long statement, a substantial answer — and what compromises them is not their
form but where the answer comes from.

There is one sign: **the content of the answer exists independently of the video.** Who
discovered what, in which year, by which experiment, under which condition a formula holds,
why approach A does not work while approach B does — all of that is in the textbooks and in
pre-training. The video then supplies only the **moment**, and timing without content does
not measure understanding.

The test before you write a question down: **strike every reference to the video out of the
wording and try to answer.** If it worked, the question is broken, and no wrapper ("wait
until the author says…", "report before he tells it himself") fixes that: a wrapper changes
*when* to answer, not *what* to answer.

#### Example 1 — a historical fact disguised as an observation of the video

> **Question.** Wait for the moment when the author names Shannon's estimate for the
> compression limit of the English language, and say two things at once: the number itself
> and with how much preceding context that estimate was obtained. Until Shannon's estimate
> specifically is spoken — stay silent.

> **Reference answer.** About one bit per character; the estimate was obtained when the
> human guessers had at least 100 preceding letters of context.

> **The semi-blind reviewer's answer, recorded BEFORE they opened a single file.**
> "Shannon's estimate for the entropy of printed English is about 1 bit per character (in
> the 1951 paper 'Prediction and Entropy of Printed English' the range is roughly 0.6–1.3
> bits per character), and it was obtained in an experiment on guessing the next letter with
> about 100 characters of preceding context."

Both quantities the rubric requires are named verbatim, without a single hedge and without a
single frame. The question looks like an observation of the video and measures acquaintance
with a paper from 1951. Set `blind_solved = true`; if its full review is otherwise complete
and correct, it may be `status: validated`, but it is excluded from the primary benchmark.

#### Example 2 — "explain why" does not save it

The temptation after the first example is to add reasoning to the question: let the model
not merely name a fact but explain the reason. It does not help if the reason is textbook as
well.

> **Question.** When the author raises the question of where to get the probabilities of the
> next letters of a natural language at all, say — before he tells it himself — two things:
> which source of such probabilities Shannon turned to, and why that source does not have
> the problem that makes a table of corpus frequencies unusable.

> **Reference answer.** The source is people, native speakers: Shannon asked a person to
> guess the next letter and reconstructed the probabilities from those guesses. That source
> has no sparsity problem because a person is not a table of frequencies but a model of the
> language: they give an estimate for a context they have never seen verbatim.

> **The semi-blind reviewer's answer before viewing.** "The source: Shannon turned to a live
> native speaker — a person asked to guess the next letter; in the 1951 paper the subject was
> his wife Betty Shannon… A table has to store a probability for every possible preceding
> context, and the number of contexts grows exponentially with length (27^n), so any corpus
> is empty for a context of any appreciable length. A person, on the other hand, already
> holds a trained model of the whole language in their head: they condition on all the text
> they have read, of any length."

Three rubric items out of three, including the "explanation". The hedge "before he tells it
himself" only sets a deadline — it does not touch the content. On top of that, such a
question is never `L3` and never `predict`: the condition is named in full in the question
itself and the answer is retrieved from memory, that is, it is an `L1` alarm, "recall
something known and say it in time", however hard the topic may sound.

#### How to rework it

There is one recipe: **move the discriminating part of the answer onto the screen**, to
where the values have to be read rather than recalled.

- instead of "name Shannon's estimate" — "name the number on the `Bits Per Character`
  counter at the moment it stops": the counter reading has to be seen, and whether or not it
  agrees with the textbook estimate is then a matter of measurement rather than of memory;
- instead of "why a table of frequencies is unusable" — "which quantity exactly, in the
  scheme shown on screen, does the author replace the table with";
- the general device: ask about **specific values shown in this video**, and add a rubric
  item "do NOT count an answer in which these values are not named".

A good test of whether you have reworked it: if the author had taken different numbers, a
different example or a different illustration, would the correct answer change? If yes, the
question rests on the video. If no, it still rests on the textbook.

The opposite pole for calibration: the question "what would the average number of bits per
instruction become if the code words of two instructions were swapped" is **not** solvable
blind, even though the topic is a textbook one. The answer there depends on exactly which
probabilities and code words are shown on screen: with a different set it would be
different. The statement can be guessed, but guessing is a bet rather than a solution, and
such samples we keep.

## How to set the times

`question_time` — the moment the question is issued. The rule: **the latest moment at which
the question still makes sense, but earlier than the window**. Zero is used only when the
question is comprehensible from the start of the video. Three constraints:

- every object the wording refers to has already been introduced by that moment;
- the tempting stretch — the early plausible-but-wrong value the question is designed
  around, if it has one — is still ahead: a question issued after it tests nothing;
- if all the information for the answer has already gone by, this is not a `pre` question
  but a `post` one, and it must be annotated honestly as `post`.

`[t_start, t_end)` — the answer window. `t_start` is the moment the answer becomes possible
**for the first time**. Look for it in the picture rather than in the speech: the author
often shows a table or the values tens of seconds before speaking them, and then re-animates
it to fit the words — so the frames around the line of speech look deceptively incomplete.
`t_end` is the moment after which it is too late to answer: the object has left the screen.
**For questions of level `L2`/`L3` the window must close no later than ten seconds before
the author speaks the answer himself.** This does not apply to `L1` alarms: there the
author's line is itself the event that is asked to be reacted to, and no slack is needed.
Setting `t_end` right up against that moment is not allowed: a model in streaming spends
several seconds on its answer and will manage to get the author's answer out of the stream —
formally answering inside the window while in fact copying. If there is no ten-second slack,
a question of level `L2`/`L3` cannot be built on this material: it will degenerate into
"repeat after the author".

`t_ideal` is a service field; set it to `t_start + 1` and do not think about it. Latency is
measured from `t_start`; why that is so is in the section "Why `t_ideal` means nothing" in
the checklist.

`t_start`, meanwhile, is not "when it is convenient" but **the moment at which a model
reasoning instantaneously could already have answered**, that is, the start of the evidence.
The validator compares: `t_start` earlier than `evidence_span[0]` is an error.

`evidence_span` — where the **latest** piece of evidence needed for the answer lies. Do not
confuse it with the corroboration: what establishes that your reference answer is correct at
all goes into `provenance.evidence` and may perfectly well lie after the window (for
`predict` the author tells the answer only after the model was supposed to predict it) or
outside the video altogether (for `counterfact` the author never speaks the answer). The
field is **required**: without it the sample does not pass the schema. Fill it in on the
merits rather than as a copy of the window — the `temporal_rel` axis is derived from it, and
a span equal to the window reduces the derivation of the axis to comparing `question_time`
with `t_start`, that is, to exactly what it must not be computed from.

For speech this is the interval of the line in which the evidence is finished. For a picture
it runs from the appearance to the end of its availability inside the window: the graph stays
on screen, and as long as it is there the evidence is available. If a visual piece of
evidence is treated as instantaneous, a question asked five seconds after the graph appears
will come out as `post`, "answer from memory", even though the graph is still in front of
your eyes.

There is **no field for decoys**. An answer outside the windows is a false alarm whether or
not anybody annotated the place, so a premature-answer trap (template 2) is a property of
the wording — an early plausible but *wrong* value before the correct one — and nothing
more. If you designed the question around such a place, say so in one sentence in
`provenance.trap_note`: it is a record of intent, it is not validated, scored or shown to
reviewers. Do not describe the run-up to the window ("not yet complete", "still being
assembled") as a trap: incomplete information is not a wrong answer, and the false-alarm
rate already covers the stretch.

**Elements that appear one by one.** If the task is a mapping over N elements the author
draws in sequence (three coloured pieces and the three terms they stand for) and the rubric
splits into one item per element, do not open the only window at "all N simultaneously
complete": the best proactive behaviour is to report each element as it appears, and such
an annotation charges it with false alarms. Give every element whose appearance precedes
the last one an **optional** trigger from its appearance to the appearance of the next
element, with the rubric item it makes answerable, and keep the required trigger on the
completion with the full rubric. The wording "simultaneously complete" is legitimate only
when the joint state is needed for the answer — a comparison between the elements — and not
for the annotator's convenience (checklist 3.4).

For multi-trigger questions ("every time when…") **walk the transcript in full, line by
line**, rather than searching for keywords: the author expresses the same condition in
different words, and a missed firing turns correct behaviour by the model into a false alarm.

## The rubric

For each window — a `response` (the reference answer) and a `rubric` (the list of criteria by
which the judge scores an answer). The requirements:

- the model being evaluated will see **only the text of the question** — no rubric, no notes;
  everything that tells a correct answer from an incorrect one must be in the question itself;
- every rubric item corresponds to an explicit requirement of the question;
- the rubric does not penalise a correct detail beyond what was expected; the penalty is for
  what is incorrect.

## What to return

Write **into your own file** `data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl` rather
than into the shared `<VIDEO_ID>.jsonl`: proposers working on other intervals are running in
parallel with you, and you would overwrite the shared file. The partials are merged by the
coordinator, who also assigns the end-to-end `id`s of the form `3b1b__<VIDEO_ID>__q<NN>` —
inside your own file number them however you like, as long as the numbers do not repeat.

Do not make control twins (the same question with a different `question_time`): they are
created by the coordinator at merge time, because a pair is built from a view of the whole
set. It is also the coordinator who fills in their `twin_of` field — the link cannot be
reconstructed from `id` names.

The `jsonl` lines follow the schema `schema/sample.schema.json`, `status: draft`,
`audio_dependency: null` (it is the result of a measurement, not an opinion; your own opinion
can be recorded in `audio_dependency_claim`).

Before handing in, run:

```bash
/home/user/conda/bin/python3 tools/validate_samples.py \
    data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl
```

and fix everything it complains about. The validator checks only the arithmetic (checklist
group 1) — its silence does not mean the annotation is correct, but its complaints always
mean it is not.

In `provenance.evidence` state where each reference answer came from. The records are
structural, one per source:

```json
{"type": "frame",  "t": 946.0, "explanation": "what is visible in the frame"}
{"type": "speech", "t_start": 1822.0, "t_end": 1829.4, "explanation": "\"quotation\""}
{"type": "other",  "explanation": "source _2026/cross_entropy/robot.py: ..."}
```

Both boundaries of a speech reference must coincide exactly with the boundaries of transcript
lines: the start with the start of some line, the end with the end of some line. If the
fragment you need ends in the middle of a sentence, widen the interval **outwards**, to the
end of that sentence: catching one extra sentence is harmless, cutting off a needed one is
not. The description must match what is in the frame at the stated moment rather than what
you remember about what is going on: this annotation will be re-checked through these
references.
