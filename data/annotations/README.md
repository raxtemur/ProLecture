# ProLecture annotation — storage format

## 1. File layout

```
data/
├── videos/<youtube_id>/           # sources (not under version control — heavy)
│   ├── <id>.mp4                   # 640x360 h264+aac, ~48 MB for 32 min
│   ├── <id>.info.json             # yt-dlp dump: chapters, duration, upload_date, …
│   ├── <id>.en.vtt                # human subtitles (not ASR)
│   └── <id>.description
├── bundles/<youtube_id>/          # material for the annotator, generated
│   ├── bundle.json                # everything machine-readable in one file
│   ├── transcript.md              # transcript with timecodes, split by chapters
│   ├── formulas.md                # LaTeX strings from the manim source
│   ├── description.jsonl, .md     # a model's description of the screen (tools/describe_video.py)
│   ├── screen_text.md             # on-screen text, each line once, at its first appearance
│   └── frames/tNNNNNN.N.jpg       # frames from scene-change detection
└── annotations/<youtube_id>.jsonl # ← the annotation itself, one sample per line
    └── partial/<id>.<interval>.jsonl  # a proposer's file; the coordinator edits it in place
                                       # and merges the files when the video is closed
```

`schema/sample.schema.json` — JSON Schema draft 2020-12, `additionalProperties: false` at
every level: an unknown field is an error rather than something silently ignored.

## 2. Conventions

| | |
|---|---|
| File format | JSONL, UTF-8 without BOM, one JSON object per line, no trailing comma |
| Time | seconds from the start of the video, `float`, half-open intervals `[t_start, t_end)` |
| `id` | `3b1b__<youtube_id>__q<NN>`, regexp `^[A-Za-z0-9_.-]+$` |
| Language | questions, answers and rubrics in English; the terms follow the video's own wording |
| Order | samples in a file are ordered by `id`, triggers inside a sample by time |

## 3. Complete examples

Two complete samples lie in [docs/sample_examples.jsonl](../../docs/sample_examples.jsonl),
as a proposer hands them in (`status: draft`). They are **invented**: the lecture, on
charging a capacitor, is not in the benchmark, and its id `INVENTED_RC` has no bundle, so
the validator skips the rules that read one. They pass `tools/validate_samples.py`, which
keeps them in line with the schema.

- `q01` — `extend`, `pre`, `L2`, one window. The two values the answer needs are on the
  screen and stay there, so the `evidence_span` runs from the appearance of the last of them
  to the end of the window. The window closes ten seconds before the author starts working
  on the second circuit himself.
- `q02` — `monitor`, `pre`, `L2`, four required windows, one per new row of a table. Each
  window closes where the next one opens, and each `evidence_span` runs from the row's
  appearance to the end of its window. The last window is six seconds long: it closes at
  least ten seconds before the author says the answer it asks for.

Both show the lines a draft carries in `validation.notes` and the `provenance.evidence`
record of what the author gives away.

`q01` on the time axis:

```
0s    58–65        606         611     616    617                    659     669      900s
│     τ₁ = 0.1 s   ▲           R₂      ▲      ├──── trigger[0] ──────┤       │         │
│     said and     second      on the  │      C₂ appears; both values        the      │
start shown        circuit     screen  question   stay on the screen         author   end
                   announced           issued                                starts on
                                                                             the circuit
```

## 4. Field reference

### Top level

| Field | Type | Req. | Meaning |
|---|---|:---:|---|
| `id` | string | ✔ | unique identifier of the sample |
| `twin_of` | string | | the `id` of the control twin: the same question issued at a different moment. The link is undirected — setting it on one of the pair is enough; the validator gathers the group and requires its members to agree on the rubrics of the required triggers, on `act` and on `reasoning_level`, while `question_time` must differ |
| `video` | object | ✔ | which video it belongs to, see below |
| `question` | string ≥20 chars | ✔ | the standing instruction, issued to the model once |
| `question_time` | number ≥0 | ✔ | the moment the instruction is issued, see §4.1 |
| `question_time_note` | string | — | why exactly that moment was chosen |
| `act` | enum | ✔ | the type of proactive act (taxonomy axis A) |
| `temporal_rel` | enum | ✔ | axis B, **derived automatically**, see §4.1 |
| `reasoning_level` | enum | ✔ | depth of reasoning (axis C) |
| `template` | string | ✔ | the name of the template in `docs/question_templates.md` the question started from, in snake_case, or a short name of the annotator's own; a free string, not an enum |
| `triggers` | array ≥1 | ✔ | the windows in which an answer is expected |
| `audio_dependency` | enum \| null | ✔ | **derived from the probes** `visiononly_solved` and `solvable`, never set by hand; `null` until the probes have answered |
| `audio_dependency_claim` | enum | — | what the annotator assumed; not a measurement |
| `followup` | object | — | a non-proactive continuation (`question` + `answer`), scored separately |
| `provenance` | object | ✔ | where the ground truth came from |
| `validation` | object | ✔ | the state of the checking |

The enumeration values:

- `act` — `alert`, `monitor`, `ground`, `narrate`, `predict`, `verify`, `counterfact`,
  `extend`; the definitions are in [docs/prompts/definitions.md](../../docs/prompts/definitions.md)
- `temporal_rel` — `pre`, `at`, `post`; the meaning and the derivation rule are in §4.1
- `reasoning_level` — `L1` reading, `L2` integration or a short calculation, `L3` derivation
  or substantial computation; the definitions are in
  [docs/prompts/definitions.md](../../docs/prompts/definitions.md). The label is that of the
  **cheapest** legal route to the full rubric, not of the route the question was written
  around
- `audio_dependency` — `required`, `unnecessary` (the intermediate `helpful` was removed:
  two boolean flags cannot tell it apart)
- `audio_dependency_claim` — `required`, `helpful`, `unnecessary`; this is the annotator's
  opinion, and a middle grade is meaningful in it

### 4.1. Axis B and the choice of `question_time`

**Axis B is about where the evidence lies relative to the moment the question is issued.**
Not about where the answer window lies, and not about how the answer is computed (the
latter is axis C, `reasoning_level`).

| Value | Condition | What it tests |
|---|---|---|
| `pre` | the evidence appears **after** `question_time` | the model has to **wait** and decide for itself when to answer |
| `at` | the evidence is present **at** `question_time` | perception and computation here and now; there is no "when" to decide |
| `post` | the evidence went by **before** `question_time` | an answer from memory, immediately |

Formally: let `e1` be the earliest start and `e2` the latest end of the `evidence_span`s of
all required triggers. Then

```
question_time <  e1  ->  pre
question_time >= e2  ->  post
otherwise            ->  at
```

The `temporal_rel` field is **derived by the validator** and compared against the recorded
one: the two can no longer diverge. Defining the axis through the answer window is not
allowed — for a `post` question the answer window begins exactly at the moment the
question is issued, which makes it indistinguishable from `at`.

**The geometry of the twins is not identical, and that is a confound.** For an `at`/`post`
twin the answer window begins, by construction, at the moment the question is issued, so
its length differs from the original. The difference in metrics
between twins contains both the effect of timing and the effect of window length; that has
to be taken into account, or normalised for length, when interpreting it.

Only `pre` is genuinely proactive, and `pre` is what the benchmark wants more of. `at` and
`post` arise in three ways. Directly: a question that is good scientifically but has
nothing ahead that brings what it needs is written as `at` or `post`. As **control twins**: the same triggers and the same rubric, with
only `question_time` shifted. And as the honest outcome of review: when the semi-blind
check (checklist 2.2/2.3) shows that the evidence was there before the question and the
when-clause of the wording contributed nothing to the answer, the sample is re-labelled
rather than kept `pre` by the letter of its wording — a `pre` a model may ignore with
impunity measures nothing. The twin pair is linked by the `twin_of` field — the link cannot
be reconstructed from `id` names, and the `b` suffix is a convention rather than a contract. If a model solves the `post` twin but not the `pre`
original, the problem is in proactivity rather than in understanding — the difference in
PAUC between the twins is exactly the price of timing.

**The rule for `question_time`:** the latest moment at which the question already makes
sense, and no later than the window opens; an `at` or `post` question opens its window at
`question_time`. Three constraints, from below and from above:

1. *The referents must exist.* `q01` of the examples asks about "the second circuit", which
   has no referent until the author announces it at 600–606; the question is issued at
   616, the last moment before its window opens.
2. *The tempting stretch must be ahead.* If the question is designed around an early
   plausible-but-wrong value, it is issued before that value, so that an answer on it
   counts as an answer outside the windows. (Such stretches used to be annotated as
   `distractor_windows`; the field was removed on 2026-09-07.)
3. *Zero is sometimes right too.* A question that makes sense from the first frame and
   needs no context has `question_time = 0.0` honestly.

The reason for the choice goes into `question_time_note`.

### `video`

| Field | Type | Req. | Meaning |
|---|---|:---:|---|
| `youtube_id` | string | ✔ | 11 characters, also the key in `data/videos/` |
| `title` | string | ✔ | as in `info.json` |
| `release_date` | string `YYYY-MM-DD` | ✔ | needed for estimating contamination |
| `duration` | number >0 | ✔ | seconds; the validator checks that the windows fit inside it |
| `source_code` | string | — | a path inside `vendor/videos`, a file or a directory |

### `triggers[]`

| Field | Type | Req. | Meaning |
|---|---|:---:|---|
| `idx` | int ≥0 | ✔ | ordinal number, consecutive from zero |
| `required` | bool | ✔ | `true` — a miss is penalised and the window goes into the recall denominator; `false` — an optional window: neither answering nor staying silent there is penalised. When one is set is in `docs/prompts/definitions.md`, "Optional window" |
| `t_start`, `t_end` | number | ✔ | the boundaries of the ground-truth window. A window, not a point: PAUC builds a piecewise-linear curve over the interval |
| `t_ideal` | number | ✔ | a service field, `t_start + 1`; latency is measured from `t_start` |
| `response` | string | ✔ | the reference answer in prose, not the key of an option |
| `rubric` | array ≥1 | ✔ | criteria for the judge. Items beginning with "do NOT count" are explicit anti-criteria |
| `trigger_modality` | array | ✔ | what the moment can be detected from in principle: `visual`, `speech`, `sound` |
| `depends_on` | array of int | — | the indices of earlier windows without which the answer is incomplete; only smaller `idx` values |
| `evidence_span` | `[t1, t2]` | ✔ | where the **latest** piece of the information lies without which the question cannot be answered. Required: the field used to be optional, in which case the answer window was substituted for it — which made a `post` question indistinguishable from an `at` one. It often coincides with the window, but not always: for `post` questions the evidence went by long before it. This is the **evidence, not the corroboration**: what establishes that the reference answer is correct at all lives in `provenance.evidence` and may lie after the window (`predict`) or outside the video (`counterfact`) |

### `provenance`

| Field | Type | Req. | Meaning |
|---|---|:---:|---|
| `annotator` | string | ✔ | who annotated it |
| `created` | string | ✔ | the date of annotation |
| `trap_note` | string | — | optional: the proposer's note that the question was designed around an early plausible-but-wrong value (template 2). A record of intent only — no interval, not validated, not scored, shown to no reviewer. Replaced `distractor_windows` on 2026-09-07 |
| `evidence` | array ≥1 | ✔ | **required references to the source** — protection against invented ground truth. Each record is structured, its kind set by the `type` field: `{"type": "frame", "t", "explanation"}`, `{"type": "speech", "t_start", "t_end", "explanation"}` (both boundaries exactly on transcript-line boundaries; align outwards) or `{"type": "other", "explanation"}` for references with no timecode (the scene source, the link to a twin). Prose is not accepted: a prose reference cannot be checked except by regular expression. This is where the **corroboration** lives — what establishes that the reference answer is correct; unlike `evidence_span` it may lie after the answer window (`predict`) or outside the video altogether (`counterfact`, `type: other`) |

### `validation`

| Field | Type | Req. | Meaning |
|---|---|:---:|---|
| `status` | enum | ✔ | review lifecycle: `draft` is active; `validated` is complete and correct; `rejected` is incorrect or deliberately abandoned. Primary eligibility is separate |
| `solvable` | bool \| null | — | is it solvable at all, from the transcript and the frames together |
| `blind_solved` | bool \| null | — | the semi-blind reviewer's answer before viewing was both correct and honest — not resting on guesses about unseen screen content (`docs/prompts/definitions.md`); correctness scored by the evaluation judge, the flag set by the coordinator. `true` excludes the sample from the primary benchmark without forcing rejection |
| `textonly_solved` | bool \| null | — | is it solvable from the question + the transcript |
| `visiononly_solved` | bool \| null | — | is it solvable without the audio |
| `frozenframe_solved` | bool \| null | — | is it solvable from a single frame from the middle of each window, `(t_start + t_end) / 2`, with no history |
| `notes` | string | — | the annotator's notes |

## 5. A multi-trigger sample

`q02` in [docs/sample_examples.jsonl](../../docs/sample_examples.jsonl) has four required
windows, one per firing of "each time a new row is added"; windows do not overlap, so each
closes, at the latest, where the next opens — earlier if its own end comes first. The windows are scored independently; `depends_on` links a window to earlier ones only when its answer is
incomplete without theirs, and never points from a required window to an optional one. An
optional window (`required: false`) is scored without penalty either way: neither answering
nor staying silent there is penalised. When one is set — a firing a reasonable annotator
might skip, an earlier stretch where the answer is possible only by a harder route, an
element of a sequence answered before the whole — is in `docs/prompts/definitions.md`,
"Optional window".

## 6. The invariants the validator checks

Besides the schema, `tools/validate_samples.py` checks the semantics; among its rules:

- `idx` values run consecutively from zero; there is at least one `required` trigger;
- `t_start < t_end`, the window is inside `duration`, `t_start ≤ t_ideal < t_end`, the
  window is no shorter than five seconds;
- `t_start ≥ evidence_span[0]` and `evidence_span[1] ≤ t_end`; whether the `t_start`
  boundary itself is right is not checked by the machine — that is the reviewer's work
  (2.4, 3.3);
- trigger windows do not intersect each other;
- `depends_on` refers only to strictly smaller `idx` values;
- `temporal_rel` matches the value derived from `question_time` and `evidence_span` (§4.1);
- `question_time` is not greater than the duration; no answer window begins before it;
- `id` is unique across all the files being checked;
- `audio_dependency` stays `null` until both probes it is derived from
  (`visiononly_solved`, `solvable`) have answered, whatever the status — the label is set by
  measurement, while the annotator's intent lives separately in `audio_dependency_claim`;
- the `claim` does not contradict the modalities: `unnecessary` when every trigger is
  speech-only is an error, and so is `required` without a single `speech`/`sound`;
- a `draft` carries in `validation.notes` a line `item <N> needs: …` for its rubric items,
  and a `pre` draft a line `the when-event gives: item <N> — …`; N is the number of an item
  of a required window's rubric, counted from 1 in list order;
- `predict`, `counterfact` and `extend` are never `L1`;
- a `predict` has no optional window opening after its last required window closes.

`python tools/validate_samples.py --rules` lists every rule with what breaks without it.

To run it:

```bash
/home/user/conda/bin/python3 tools/validate_samples.py data/annotations/*.jsonl
```

With zero errors it prints the coverage breakdown along all three axes, the templates and
the number of triggers per sample.

## 7. How to read it programmatically

```python
import json
from pathlib import Path

rows = [json.loads(l) for l in
        Path("data/annotations/l6DKRf-fAAM.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

# every required window, sorted by time
for s in rows:
    for t in s["triggers"]:
        if t["required"]:
            print(f"{s['id']}  [{t['t_start']:7.1f}, {t['t_end']:7.1f})  {t['response'][:60]}…")

# correctness/review status and benchmark eligibility are independent
primary_tasks = [s for s in rows
                 if s["validation"]["status"] == "validated"
                 and not s["validation"]["blind_solved"]]
blind_baselines = [s for s in rows
                   if s["validation"]["status"] == "validated"
                   and s["validation"]["blind_solved"]]
invalid_samples = [s for s in rows if s["validation"]["status"] == "rejected"]
```

## 8. What has been annotated so far

`l6DKRf-fAAM.jsonl` — "Reinventing Entropy | Compression is Intelligence Part 1",
published 2026-06-07, **10 samples / 24 triggers**. The pilot video was chosen so that its
release date falls after the cutoff of most models.

| id | template | act / rel / level | q_time | wait | triggers |
|---|---|---|---|---|---|
| q01 | counterfactual_on_appearance | counterfact / pre / L3 | 250 | 65 s | 1 |
| q02 | premature_answer_trap | alert / pre / L1 | 2 | 1820 s | 1 |
| q02b | post_control_twin | alert / **post** / L1 | 1900 | 0 s | 1 |
| q03 | assumption_probe | alert / pre / L1 | 1480 | 142 s | 1 |
| q04 | state_monitor | monitor / pre / L1 | 0 | 908 s | 6 (3 opt.) |
| q05 | step_dependency | alert / pre / L1 | 370 | 1181 s | 1 |
| q06 | speech_only_marker | ground / pre / L1 | 0 | 34 s | 9 (5 opt.) |
| q07 | counterfactual_on_appearance | counterfact / pre / L3 | 930 | 16 s | 2 (1 opt.) |
| q07b | at_control_twin | counterfact / **at** / L3 | 963 | 0 s | 1 |
| q08 | prediction_ahead | predict / pre / L1 | 1110 | 149 s | 1 |

All ten are `status: validated` after the second review round. Five of them (q02, q02b, q03,
q05, q08) carry `blind_solved: true`: the semi-blind reviewer answered them before viewing, so
they are excluded from the primary set and kept as blind baselines. The flag records the
contamination result separately from the status; the records are retained for audit.

**The windows are anchored to information appearing on screen, not to the speech.** This is
a pitfall of its own: the author often shows a table or the values tens of seconds before
speaking them aloud. In q01 the table of code words is complete as early as 315, whereas the
author names those same words at 337–347 and computes the average at 347–360 — the window
opens at 315, because the codes and the probabilities are enough to answer. In q07 the same
four pairs `(p, −log₂ p)` are shown as square diagrams at 946, 11 seconds before the graph;
that moment is recorded as an optional window so that an early correct answer does not count
as a false positive. This has to be checked against frames, not against the transcript.

The full list of the error classes to check for while annotating is in
[docs/annotation_checklist.md](../../docs/annotation_checklist.md).

## 9. Statuses and what Phase 3 has to show

Promotion to `validated` happens only after the modality probes have answered (`text`,
`vision`, `frame`, and `full` if needed; see
[docs/annotation_pipeline.md](../../docs/annotation_pipeline.md)). The expectations the
probes have to confirm or refute:

- **q06 must fail vision-only** — all seven of its triggers are purely spoken. If it does
  not fail, what is broken is the measurement method, not the sample. A caveat: the window
  `[34, 46)` coincides with the frame t=40, where the screen shows a speedometer captioned
  "Limit?" — a visual marker for "the question is postponed" is partly readable there, so
  the control is weaker than one would like.
- **q01, q07 and q07b must survive without the audio** — their answers are computed from
  the picture.
- **The candidates for blind-solved are wider than they look**: besides q02, q02b and q08
  this includes q01 (the canonical Huffman example `1/2, 1/4, 1/8, 1/8 → 0, 10, 110, 111`),
  q03 (which reduces to "entropy assumes i.i.d.") and q07/q07b (bars at
  `1/2, 1/4, 1/8, 1/16` of heights `1, 2, 3, 4` — the canonical illustration of `−log₂ p`).
  All seven have to be checked; the claims in `validation.notes` about resistance to blind
  solving are hypotheses, not measurements.
- **q02, q02b and q08**: Shannon's estimate of ≈1 bit per character and the letter-guessing
  experiment are in the textbooks. Their `blind_solved` flags exclude them from primary
  "timing only" tests. The current records remain rejected for incomplete or unresolved review;
  a future otherwise correct and complete equivalent belongs in the validated blind-baseline
  slice (checklist 4.2).
- **q03 must not be solvable frozen-frame**: from a single frame with the formula one cannot
  name which two examples were gone through earlier in the same video.
- **q07/q07b must not be solvable frozen-frame from a frame without the graph**, and must
  not be solvable blind: the positions of the bars `p = 1/16, 1/8, 1/4, 1/2` can only be
  read off the screen. An early revision of the question (with no anchoring to the bars) was
  a pure textbook exercise and was solvable without the video — that has been fixed.

## 10. Environments

The project has two pythons, and they divide the duties:

| Environment | Path | What is in it | What for |
|---|---|---|---|
| `rah_manim` | `/home/jovyan/.mlspace/envs/rah_manim/bin/python` | `manim` 0.20.1, `yt-dlp` | downloading videos, future re-rendering of scenes |
| base conda | `/home/user/conda/bin/python3` | `matplotlib`, `pandas`, `jsonschema`, `cv2`, jupyter | the notebook, the validator, building bundles |

`python3` in an interactive shell may resolve to either of them, so
`tools/fetch_video.py` finds an interpreter with `yt_dlp` on its own (the list is in
`CANDIDATE_PYTHONS`) and prints which one it chose. Run the other tools with the base
python:

```bash
/home/user/conda/bin/python3 tools/make_bundle.py <id>
/home/user/conda/bin/python3 tools/validate_samples.py data/annotations/*.jsonl
```

The kernel of the `data_overview.ipynb` notebook is base conda; `rah_manim` has neither
`matplotlib`, nor `pandas`, nor `ipykernel`.

## 11. How to reproduce from scratch

```bash
python tools/build_3b1b_mapping.py            # lesson -> youtube_id -> manim source
python tools/fetch_video.py l6DKRf-fAAM       # mp4 + info.json + en.vtt + description
python tools/make_bundle.py l6DKRf-fAAM       # transcript.md, formulas.md, frames/
python tools/validate_samples.py data/annotations/l6DKRf-fAAM.jsonl
```

## 12. Frames: scene detection only

There is no uniform grid in the pipeline any more. It needed nothing but ffmpeg, but on
manim videos it erred in both directions at once: it duplicated static shots and **lost
whole scenes**. On the pilot video, in the window 887–1011 s, the grid missed 8 meaningful
states out of 18, including the entire derivation chain
`p = 2⁻ⁿ → log₂(p) = −n → −log₂(p) = n` and the moment where the definition
`Information := −log₂(p)` is introduced.

Frames are cut by [`tools/detect_scenes.py`](../../tools/detect_scenes.py): accumulated
drift relative to the last frame taken, with the noise floor subtracted block by block. Over
the same window it catches 18 states out of 18. The price is 3.2 times as many frames (437
against the previous 136 for a 32-minute video) and a dependency on OpenCV:

```bash
/home/user/conda/bin/python3 -m pip install opencv-python-headless   # into base conda
```

How the threshold was chosen, which videos it was checked on, how many frames per minute it
produces and what the detector does not catch are in
[docs/scene_detection.md](../../docs/scene_detection.md). Capture times depend on the
detector's parameters, so `make_bundle.py` wipes all the old frames before writing:
otherwise a run with a different threshold would leave its files next to the new ones, the
annotator would see a mixture of two cuts, and `bundle.json` would list only half of them.

The detector also works as a standalone tool:

```bash
python tools/detect_scenes.py l6DKRf-fAAM                    # times only
python tools/detect_scenes.py l6DKRf-fAAM --write-frames     # frames as well
python tools/detect_scenes.py video.mp4 --threshold 0.02 --json cuts.json
```
