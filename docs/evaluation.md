# Measuring a model on ProLecture

How a model is run on the benchmark, what its answers must look like on disk, and how they
become scores. The design behind the metrics is in [plans/general.md](plans/general.md), §4;
the format of a record is in [../data/annotations/README.md](../data/annotations/README.md).

## What you need

- **The data**: `annotations/<video>.jsonl` (the records), `videos/<video>/<video>.mp4` with
  its `.en.vtt`, and `bundles/<video>/bundle.json` (its `transcript`, the subtitles as timed
  cues, is what the offline run reads). Apart from the three pilot videos' records they are
  not in the repository. On the SR004 cluster they are in

      /workspace-SR004.nfs2/rahmatullaev/rand_exps/PoC_for_rand_ideas/manim_play/data

  Point `PROLECTURE_DATA` at that folder and the scripts read the records and the videos from
  there, while a run's own folder (`--out`) stays in your checkout. Without the variable the
  checkout's own `data/` is read. Read the shared folder, do not write into it.
- **Python**: the judge and the scores run on the standard library plus `openai` and `httpx`.
  A model's runner runs in the model's own environment; what it shares with the rest,
  [tools/eval_common.py](../tools/eval_common.py), is standard library only.
- **A judge**: an OpenAI-compatible server. The runs so far used Qwen3.8-27B on vLLM.

## Three steps, one folder per run

```
data/eval/<model>/<date>/
├── config.json               # what was run: the model's settings, `runs`, the list of `samples`
├── responses/<task>.json     # step 1: what the model said, untouched
├── judged/<task>.json        # step 2: which lines state which rubric item
└── scores/                   # step 3: tasks.jsonl, summary.json, summary.md
```

A task is one session of one record: `<sample_id>.r<run>`. Every step is a file per task and
skips the files that exist, so an interrupted step is simply started again.

```bash
BASE=/home/user/conda/bin/python3
export PROLECTURE_DATA=/workspace-SR004.nfs2/rahmatullaev/rand_exps/PoC_for_rand_ideas/manim_play/data
OUT=data/eval/<model>/<date>

# 1. the model's answers: one runner per model
<model env>/python tools/eval_run_minicpm.py --out $OUT --runs 3           # a stream
$BASE tools/eval_run_offline.py --out $OUT --runs 3 --workers 2            # or one answer after the material

# 2. the judge
$BASE tools/eval_judge.py --out $OUT --base-url http://127.0.0.1:8000/v1 --api-key dummy --model local

# 3. the scores
$BASE tools/eval_score.py --out $OUT        # -> $OUT/scores/summary.md
```

## Which records

`eval_common.select_samples()` returns every record with `validation.status == "validated"`
of every `data/annotations/*.jsonl`. All of them are run. The scores split them afterwards:

- **the primary set** — `validation.blind_solved == false`; the headline numbers are over it;
- **`blind_solved`** — records a model answered without the video; reported apart.

`rejected` records stay in the files and are never run.

## What the model is shown

**A stream** (`eval_run_minicpm.py`). One session per task. The lecture runs from 0 s
(`eval_common.stream_bounds`), not from a clip around the question: a question may lean on
anything shown before it. The question text is injected at `question_time`. The stream ends
20 s after the last window's `t_end`, so that a late answer is seen as late. The model decides
itself when to speak; nothing tells it where the windows are. Three runs per record, each with
a seed that follows from the task's name.

**Offline** (`eval_run_offline.py`). For a model that takes a video and answers once. It gets
the lecture from 0 s to 1 s past the last window's `t_end` — one-minute segments at 1 fps,
each followed by the subtitles spoken in it — and then the question with the moment it was
asked. There is no timing to score: this is what the model answers with all the material its
windows allow. The material is everything before the last window, not the stretch from the
question to it, so a question asked late in a long lecture may not fit the model's context:
such a task fails and is counted as missing (with a 262k-token context the limit is about
33 minutes of lecture, and a few records lie past it).

A model must not be shown `triggers` (windows, reference answers, rubrics), `provenance` or
`validation`: of a record it gets `question`, `question_time` and the video.

## The contract: `responses/<task>.json`

This file is all the judge and the scores read of a model. A runner for a new model writes it
and nothing else needs to change.

```json
{
  "task": "3b1b__<video>__q03.r0",
  "sample_id": "3b1b__<video>__q03",
  "video": "<video>",
  "run": 0,
  "responses": [
    {"t": 412.0, "content": "The heavier ball lands first,", "utterance_id": 0},
    {"t": 413.0, "content": "because the air slows the light one more.", "utterance_id": 0},
    {"t": 455.0, "content": "Now both are on the ground.", "utterance_id": 1}
  ]
}
```

| field | meaning |
|---|---|
| `task`, `sample_id`, `video`, `run` | which session this is; `task` is `eval_common.task_name(sample_id, run)` |
| `responses[].t` | the second of the lecture at which this piece of text was emitted |
| `responses[].content` | the text; an empty piece is ignored |
| `responses[].utterance_id` | pieces with the same id, next to each other, are one utterance: it is timed by its first piece and credited as a whole. `null` makes every piece its own utterance |

A session in which the model said nothing is a file with `"responses": []`, not a missing
file. Anything else may be added (`seed`, `seconds`, `host`, the stream bounds): it is kept
and ignored. `seconds`, when present, is reported as the cost of the task. An offline runner
writes its one answer split into sentences, every line at the time of the cut.

`config.json` needs `"runs"` and `"samples"` (the ids that were run); an offline run adds
`"mode": "offline"`, which makes the scores drop everything about timing.

## Adding a model

Write `tools/eval_run_<model>.py` after one of the two runners. The parts to keep:

```python
import eval_common as ec

samples = ec.select_samples()                         # the validated records
for sample in samples:
    start, end = ec.stream_bounds(sample)             # 0 s .. last t_end + 20 s
    video = ec.video_path(sample)                     # <data>/videos/<id>/<id>.mp4
    for run in range(runs):
        task = ec.task_name(sample["id"], run)
        # feed [start, end] of `video`; give sample["question"] at sample["question_time"];
        # collect (second, text, utterance id) of everything the model says
```

`eval_run_minicpm.py` also shows how several workers and jobs share one run: a task is taken
through a `<task>.claim` file with a heartbeat, so a job that is preempted leaves its tasks to
the others.

## The judge

One call per task. The judge sees the question, every window's reference answer and rubric
items, and the model's output as numbered lines with their seconds. For every item it lists
the lines that state it correctly and the lines that state it wrongly or offer an alternative.
It does not score time: one judgement serves every metric.

- `judged/<task>.json` records `prompt_version` and `judge_model`. Scores over tasks judged by
  different prompts compare nothing: `eval_score.py` warns, and `eval_judge.py --force` judges
  the run again.
- The judge of the runs so far is the model that also proposed and reviewed the records, so
  its own high score is partly built in. A judge of another family is a change of
  `--base-url`/`--model`; say which judge a number was obtained with.

## The scores

`scores/summary.md` gives, for the primary set, the `blind_solved` records and all, and for
the primary set by `act`, `reasoning_level`, `temporal_rel`, `audio_dependency` and video:

| column | what it is |
|---|---|
| `acc` | share of the required windows' rubric items the model stated inside a window of the record |
| PAUC ω=0, ω=0.5 | the main timing score over the required windows: quality (0–2) of what was said so far, over the window; **0.25 is silence**, the floor of the scale |
| Trigger Recall | required windows where at least one item was credited |
| Silence rate | required windows in which no utterance starts |
| FAR | utterances that start outside every window |
| Rubric acc. (1)–(3) | items credited inside a window / anywhere / before the window's end on `predict` |

A record's value is the mean over its runs; a table's value is the mean over records, with the
standard deviation across the runs and a 95% bootstrap interval over records.
`scores/tasks.jsonl` has every task with its windows, for looking at single records. The exact
definitions are in the docstring of [tools/eval_score.py](../tools/eval_score.py).

An offline run reports `acc` alone: the share of the required windows' items credited over the
whole answer.
