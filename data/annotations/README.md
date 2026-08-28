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
│   └── frames/tNNNNNN.N.jpg       # frames from scene-change detection
└── annotations/<youtube_id>.jsonl # ← the annotation itself, one sample per line
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

## 3. A complete example

The sample `q02` in full, as it lies in the file (indented here for readability — in the
file it is a single line):

```json
{
  "id": "3b1b__l6DKRf-fAAM__q02",
  "video": {
    "youtube_id": "l6DKRf-fAAM",
    "title": "Reinventing Entropy | Compression is Intelligence Part 1",
    "release_date": "2026-06-07",
    "duration": 1939.19,
    "source_code": "_2026/cross_entropy"
  },
  "question_time": 2.0,
  "question": "Wait for the moment when the author names Shannon's estimate for the compression limit of the English language, and say two things at once: the number itself and with how much preceding context that estimate was obtained. Until Shannon's estimate specifically is spoken — stay silent.",
  "act": "alert",
  "temporal_rel": "pre",
  "reasoning_level": "L1",
  "template": "premature_answer_trap",
  "triggers": [
    {
      "idx": 0,
      "required": true,
      "t_start": 1822.0,
      "t_end": 1860.0,
      "t_ideal": 1823.0,
      "response": "About one bit per character; the estimate was obtained when his interviewees had at least 100 preceding letters of context.",
      "rubric": [
        "the value ≈1 bit per character is named",
        "the condition is named: at least 100 preceding letters of context",
        "it is stated that this is an estimate from experiments with people rather than a measurement by an algorithm",
        "an answer with the number alone, without the condition about 100 letters, is partial (1 of 2)",
        "do NOT count 1.1 bits per character — that is the result of neural methods, from second 30",
        "do NOT count 4.2 bits per character — that is Huffman, from second 21"
      ],
      "trigger_modality": [
        "speech",
        "visual"
      ],
      "evidence_span": [
        1822.0,
        1829.4
      ]
    }
  ],
  "distractor_windows": [
    {
      "t_start": 12.0,
      "t_end": 34.0,
      "why": "the screen runs through the series ASCII 8.0 -> Huffman ~4.2 -> Neural methods ~1.1 bits per character; these are achievements of compression methods, not Shannon's estimate"
    },
    {
      "t_start": 34.0,
      "t_end": 60.0,
      "why": "the screen shows a speedometer reading 1.0 bits/ch with the caption “Limit?” — the number coincides with the correct answer, but this is the statement of the question rather than the answer, and it comes without the conditions it was obtained under"
    }
  ],
  "audio_dependency": null,
  "audio_dependency_claim": "required",
  "provenance": {
    "annotator": "claude+rahmatullaev",
    "created": "2026-08-20",
    "evidence": [
      {
        "type": "speech",
        "t_start": 1822.0,
        "t_end": 1829.4,
        "explanation": "«at least 100 preceding letters of context ... about one bit per character»"
      },
      {
        "type": "frame",
        "t": 1832.0,
        "explanation": "the counter “Bits Per Character ≈ 1.0”"
      },
      {
        "type": "frame",
        "t": 15.0,
        "explanation": "ASCII 8.0 bits/ch"
      },
      {
        "type": "frame",
        "t": 21.0,
        "explanation": "Huffman ~4.2"
      },
      {
        "type": "frame",
        "t": 30.0,
        "explanation": "Neural ~1.1"
      },
      {
        "type": "frame",
        "t": 40.0,
        "explanation": "the speedometer 1.0 bits/ch with the caption Limit?"
      }
    ]
  },
  "validation": {
    "status": "rejected",
    "notes": "a key sample for timing: the correct number is visible on screen 1785 s before the answer; level L1: both facts are spoken in a single line 1822-1829, and the difficulty of the sample lies entirely in the timing rather than in the reasoning | blind: before viewing, the semi-blind reviewer named both quantities of the rubric (≈1 bit per character, ≥100 letters of context) with no assumptions about the screen — a commonly known fact about Shannon's experiment | rejection: review cycle is incomplete; only the semi-blind review finished",
    "blind_solved": true
  },
  "question_time_note": "the question about the compression limit of text is raised by the video itself at 4.6-11.5, but the instruction has to be issued BEFORE the first distractor at 12 s, otherwise the trap with the on-screen “1.0 bits/ch  Limit?” at 40 s stops being a trap."
}
```

The same thing on the time axis:

```
 0s  2     12      34       60                                 1822   1829       1860      1939s
 │   ▲     ├───────┼────────┤                                  ├────────●─────────┤          │
 │   │     │  D0   │   D1   │                                  │   t_ideal        │          ▲
 │   │     └── distractors ─┘                                  └──── trigger[0] ──┘          │
 │   question_time   an answer here = 0 points             the one window where          end of
start   question issued  and it spoils all later ones      an answer counts               video
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
| `template` | string | ✔ | a template from the catalogue in §2.1 of the plan; a free string, not an enum |
| `triggers` | array ≥1 | ✔ | the windows in which an answer is expected |
| `distractor_windows` | array | — | the windows in which one **must not** answer |
| `audio_dependency` | enum \| null | ✔ | **derived from the probes** `visiononly_solved` and `solvable`, never set by hand; `null` until the probes have answered |
| `audio_dependency_claim` | enum | — | what the annotator assumed; not a measurement |
| `followup` | object | — | a non-proactive continuation (`question` + `answer`), scored separately |
| `provenance` | object | ✔ | where the ground truth came from |
| `validation` | object | ✔ | the state of the checking |

The enumeration values:

- `act` — `alert`, `monitor`, `ground`, `narrate`, `predict`, `verify`, `counterfact`
- `temporal_rel` — `pre`, `at`, `post`; the meaning and the derivation rule are in §4.1
- `reasoning_level` — `L1` (read off the screen or off the speech), `L2` (≥2 moments far
  apart have to be connected), `L3` (a computation or a derivation not present in the
  video is needed)
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

Formally: let `[e1, e2)` be the `evidence_span` of the first and of the last required
trigger (by default equal to the answer window). Then

```
question_time <  e1(of the first)  ->  pre
question_time >= e2(of the last)   ->  post
otherwise                          ->  at
```

The `temporal_rel` field is **derived by the validator** and compared against the recorded
one: the two can no longer diverge. Defining the axis through the answer window is not
allowed — for a `post` question the answer window begins exactly at the moment the
question is issued, which makes it indistinguishable from `at`.

**The geometry of the twins is not identical, and that is a confound.** For an `at`/`post`
twin the answer window begins, by construction, at the moment the question is issued, so
its length differs from the original (q07 — 43 s, q07b — 37 s). The difference in metrics
between twins contains both the effect of timing and the effect of window length; that has
to be taken into account, or normalised for length, when interpreting it.

Only `pre` is genuinely proactive. `at` and `post` exist as **control twins**: the same
triggers and the same rubric, with only `question_time` shifted. The pair is linked by the
`twin_of` field — the link cannot be reconstructed from `id` names, and the `b` suffix is a
convention rather than a contract. If a model solves `q02b` (`post`) but does not solve
`q02` (`pre`), the problem is in proactivity rather than in understanding — the difference
in PAUC between the twins is exactly the price of timing.

**The rule for `question_time`:** the latest moment at which the question already makes
sense but the window has not yet arrived. Three constraints, from below and from above:

1. *The referents must exist.* q03 asks "which of the two examples gone through in this
   video" — at second zero that phrase has no referent, hence `question_time = 1480`,
   right after both examples have been gone through.
2. *The distractors must be alive.* In q02 the traps are at 12–34 and 34–60 s, so the
   question must be issued earlier: `question_time = 2.0`. A distractor lying entirely
   before the question is issued is a validation error — there is nothing to catch there.
3. *Zero is sometimes right too.* q04 and q06 make sense from the first frame and require
   no context at all — their `question_time = 0.0` honestly.

The reason for the choice is recorded in `question_time_note` for every sample.

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
| `required` | bool | ✔ | `true` — a miss is penalised and the window goes into the recall denominator; `false` — not beyond dispute, so neither answering nor staying silent is penalised |
| `t_start`, `t_end` | number | ✔ | the boundaries of the ground-truth window. A window, not a point: PAUC builds a piecewise-linear curve over the interval |
| `t_ideal` | number | ✔ | a service field, `t_start + 1`; latency is measured from `t_start` |
| `response` | string | ✔ | the reference answer in prose, not the key of an option |
| `rubric` | array ≥1 | ✔ | criteria for the judge. Items beginning with "do NOT count" are explicit anti-criteria |
| `trigger_modality` | array | ✔ | what the moment can be detected from in principle: `visual`, `speech`, `sound` |
| `depends_on` | array of int | — | the indices of earlier windows without which the answer is incomplete; only smaller `idx` values |
| `evidence_span` | `[t1, t2]` | ✔ | where the **latest** piece of the information lies without which the question cannot be answered. Required: the field used to be optional, in which case the answer window was substituted for it — which made a `post` question indistinguishable from an `at` one. It often coincides with the window, but not always: for `post` questions the evidence went by long before it. This is the **evidence, not the corroboration**: what establishes that the reference answer is correct at all lives in `provenance.evidence` and may lie after the window (`predict`) or outside the video (`counterfact`) |

### `distractor_windows[]`

| Field | Type | Req. | Meaning |
|---|---|:---:|---|
| `t_start`, `t_end` | number | ✔ | the window; landing in it = a false positive |
| `why` | string | ✔ | why an answer here is wrong — read by a human when disputed cases are analysed |

Distractors do not intersect any trigger: otherwise one and the same answer would be
correct and false at once.

### `provenance`

| Field | Type | Req. | Meaning |
|---|---|:---:|---|
| `annotator` | string | ✔ | who annotated it |
| `created` | string | ✔ | the date of annotation |
| `evidence` | array ≥1 | ✔ | **required references to the source** — protection against invented ground truth. Each record is structured, its kind set by the `type` field: `{"type": "frame", "t", "explanation"}`, `{"type": "speech", "t_start", "t_end", "explanation"}` (both boundaries exactly on transcript-line boundaries; align outwards) or `{"type": "other", "explanation"}` for references with no timecode (the scene source, the link to a twin). Prose is not accepted: a prose reference cannot be checked except by regular expression. This is where the **corroboration** lives — what establishes that the reference answer is correct; unlike `evidence_span` it may lie after the answer window (`predict`) or outside the video altogether (`counterfact`, `type: other`) |

### `validation`

| Field | Type | Req. | Meaning |
|---|---|:---:|---|
| `status` | enum | ✔ | review lifecycle: `draft` is active; `validated` is complete and correct; `rejected` is incorrect or deliberately abandoned. Primary eligibility is separate |
| `solvable` | bool \| null | — | is it solvable at all, from the transcript and the frames together |
| `blind_solved` | bool \| null | — | is it solvable from the question alone, with no video; `true` excludes it from the primary benchmark without forcing rejection |
| `textonly_solved` | bool \| null | — | is it solvable from the question + the transcript |
| `visiononly_solved` | bool \| null | — | is it solvable without the audio |
| `frozenframe_solved` | bool \| null | — | is it solvable from a single frame at `t_ideal`, with no history |
| `notes` | string | — | the annotator's notes |

## 5. A multi-trigger sample

A fragment of `q04` (`state_monitor`): six windows, the later ones with `depends_on`
pointing at the earlier ones. The answer in each window must list everything accumulated so
far, so the windows are linked in meaning but scored independently.

```json
"triggers": [
  {
   "idx": 0,
   "required": true,
   "t_start": 907.6,
   "t_end": 940.0,
   "t_ideal": 908.6,
   "response": "Defined: (1) the number of bits per message under perfect compressio …"
  },
  {
   "idx": 1,
   "required": true,
   "t_start": 991.3,
   "t_end": 1022.0,
   "t_ideal": 992.3,
   "response": "Defined: (1) the number of bits = -log2(p); (2) the information of an …",
   "depends_on": [
    0
   ]
  },
  {
   "idx": 2,
   "required": true,
   "t_start": 1585.0,
   "t_end": 1620.0,
   "t_ideal": 1586.0,
   "response": "Defined: (1) the number of bits = -log2(p); (2) the information of an …",
   "depends_on": [
    0,
    1
   ]
  },
  {
   "idx": 3,
   "required": false,
   "t_start": 1638.0,
   "t_end": 1700.0,
   "t_ideal": 1639.0,
   "response": "There is no new formula, but the quantity from the previous item is g …",
   "depends_on": [
    2
   ]
  },
  {
   "idx": 4,
   "required": false,
   "t_start": 1770.5,
   "t_end": 1800.0,
   "t_ideal": 1771.5,
   "response": "The entropy rate of a stochastic process is mentioned — the generalis …",
   "depends_on": [
    2
   ]
  },
  {
   "idx": 5,
   "required": false,
   "t_start": 1851.1,
   "t_end": 1862.0,
   "t_ideal": 1852.1,
   "response": "Cross-entropy is mentioned as a variation of entropy — the name is gi …",
   "depends_on": [
    2
   ]
  }
 ]
```

The last three windows are `required: false` on purpose: naming a quantity that has already
been introduced, and a mention with no formula, are exactly the borderline cases where a
reasonable annotator might have said nothing.

## 6. The invariants the validator checks

Besides the schema, `tools/validate_samples.py` checks the semantics:

- `idx` values run consecutively from zero; there is at least one `required` trigger;
- `t_start < t_end`, the window is inside `duration`, `t_start ≤ t_ideal < t_end`, the
  window is no shorter than five seconds;
- `t_start ≥ evidence_span[0]` and `evidence_span[1] ≤ t_end`; whether the `t_start`
  boundary itself is right is not checked by the machine — that is the reviewer's work
  (2.4, 3.3);
- trigger windows do not intersect each other and do not intersect the distractors;
- `depends_on` refers only to strictly smaller `idx` values;
- `temporal_rel` matches the value derived from `question_time` and `evidence_span` (§4.1);
- `question_time` is not greater than the duration; no answer window lies entirely before
  it;
- a multi-trigger sample has at least one `distractor_window` (otherwise a spam strategy
  goes unpunished);
- `id` is unique across all the files being checked;
- no distractor lies entirely before `question_time` — there is nothing to catch there;
- `audio_dependency` stays `null` while `status == "draft"` — the label is derived from the
  answers of the modality probes (checklist 4.5), while the annotator's intent lives
  separately in `audio_dependency_claim`;
- the `claim` does not contradict the modalities: `unnecessary` when every trigger is
  speech-only is an error, and so is `required` without a single `speech`/`sound`.

To run it:

```bash
python tools/validate_samples.py data/annotations/*.jsonl
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
| q01 | counterfactual_on_appearance | counterfact / pre / L3 | 250 | 65 s | 1 +1 distr. |
| q02 | premature_answer_trap | alert / pre / L1 | 2 | 1820 s | 1 +2 distr. |
| q02b | post_control_twin | alert / **post** / L1 | 1900 | 0 s | 1 |
| q03 | assumption_probe | alert / pre / L1 | 1480 | 142 s | 1 +1 distr. |
| q04 | state_monitor | monitor / pre / L1 | 0 | 908 s | 6 (3 opt.) +2 distr. |
| q05 | step_dependency | alert / pre / L1 | 370 | 1181 s | 1 +2 distr. |
| q06 | speech_only_marker | ground / pre / L1 | 0 | 34 s | 9 (5 opt.) +2 distr. |
| q07 | counterfactual_on_appearance | counterfact / pre / L3 | 930 | 16 s | 2 (1 opt.) +1 distr. |
| q07b | at_control_twin | counterfact / **at** / L3 | 963 | 0 s | 1 |
| q08 | prediction_ahead | predict / pre / L1 | 1110 | 149 s | 1 +1 distr. |

Four of the ten (q02, q02b, q03, q08) still carry `status: rejected` after the old
review round. They remain rejected because their cycles were incomplete or left full-review
defects unresolved, not because their answers were given blind. The separate
`blind_solved: true` flag records the contamination result. The records are retained for
audit; a completed and otherwise correct blind-solved sample would instead be a validated
blind baseline.

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
