# A benchmark of proactive tasks for streaming VLMs on 3Blue1Brown videos

Working title: **ProLecture** (proactive lecture streaming benchmark).
Status: draft plan, version 0.1, 2026-08-19.

---

## 0. The goal and the positioning

**The goal.** A benchmark testing the ability of a streaming VLM to decide for itself *when* to
answer and *what* to answer, on the material of mathematical lectures, where the answer requires
reasoning rather than reading off.

**How we differ from what exists.** The three nearest works:

| Work | Domain | What it measures | What is missing |
|---|---|---|---|
| [OVO-Bench](https://arxiv.org/abs/2501.05510) | everyday / sports / games | backward / real-time / forward active | MCQ, no audio, perception |
| [ProactiveVideoQA](https://arxiv.org/abs/2507.09313) | mixed | open-ended + the **PAUC** metric | simple questions ("tell me when X") |
| [OmniPro](https://arxiv.org/abs/2605.18577) | real scenes | 6 abilities × 9 subtasks, audio | perceptual tasks, counting; 84% audio, yet vision-only models keep up |

Our niche is **proactivity that runs into reasoning**. A lecture has almost no perceptual
difficulty (clean rendering, large formulas, clear speech), but it does have a logical structure:
premise → derivation → consequence. Which means the only way to answer in time is to understand
the content rather than recognise an object. That is exactly the axis along which OmniPro fails to
tell models apart (see §1.2).

**Our unique asset.** For 140 3b1b videos we know both the YouTube link **and a path to the
source manim code that actually exists in the repository** (159 lessons declare a `source`, 155 of
them together with a YouTube ID, but for 15 of those the path is broken or renamed)
(`data/3b1b_mapping.json`, assembled by `tools/build_3b1b_mapping.py`). None of the existing
benchmarks has the sources of the visual track. This gives:

1. an exact ground truth of what is on the screen (the `Tex`/`MathTex` strings with LaTeX),
2. semantic boundaries (scene names, the order of the animations),
3. the possibility of **re-rendering with an injected error** — content guaranteed to be absent
   from pre-training (see Phase 6).

---

## 1. The risks we build into the design from day one

These points are direct conclusions from the adversarial reviews of OmniPro, M³AV and Code2Video
(`articles/*/review.md`). Each of them killed or badly weakened the work in question.

### 1.1. Contamination — risk no. 1 for 3b1b

3b1b videos are among the most watched mathematical videos in existence. Texts, transcripts and
retellings of "Essence of calculus" are almost certainly in the pre-training of any frontier model.
The question "what is a Taylor series" is solved blind.

Measures:
- **A blind baseline is mandatory for every sample.** The model gets only the question, without
  the video. If it solves it, set `blind_solved: true`: the sample is excluded from the
  primary benchmark, but may remain `validated` when its review is otherwise complete and
  correct.
- **The pilot is built on 2026 videos** (`_2026/*`), released after the cutoff of most models, and
  **in parallel we take a control video from 2017**, so as to *measure* the size of the gap rather
  than deny the problem.
- Question wordings are anchored to *this* exposition ("what method does the author use", not "what
  method is this solved by").

The maintained selection rule is:

```python
primary_tasks = status == "validated" and not blind_solved
blind_baselines = status == "validated" and blind_solved
invalid_samples = status == "rejected"
```

### 1.2. A benchmark is obliged to tell modalities apart

In OmniPro 84% of the questions are marked as audio-dependent, yet the vision-only Qwen3-VL beats
three of the five omni models — that is, the label was never checked empirically.

The measure: `audio_dependency` is **not a declaration by the annotator but the result of a
measurement.** The label is derived from the answers of the modality probes rather than from the
annotator's opinion: while `status == "draft"` the field stays `null`, and the opinion lives
separately in `audio_dependency_claim`.

**A caveat without which this would be the same substitution as OmniPro's.** The probes are textual
agents: `probe_text` reads the **transcript**, `probe_vision` looks at frames. So `required` for us
means "the **content of the speech** is needed" rather than "the sound is needed": a model with an
ASR front end will get that content from text and will not confirm the label. The only real check
will be the vision-only baseline in Phase 3 — until then the label remains a hypothesis derived by
a measurement on a surrogate. In the release the field is named `speech_dependency`; the samples
where the real vision-only baseline diverges from the label are reconsidered, not fitted.

Recorded separately: **3b1b has no non-speech sound** (only speech and occasionally background
music). The "sound" axis from OmniPro does not work for us — we write that honestly in the
limitations rather than fitting around it.

### 1.3. Generator ≠ judge ≠ participant

In Code2Video, Gemini-2.5 Pro was the Critic inside the method, the judge and the "student" all at
once; in OmniPro, Gemini-3-Flash is the data generator, the judge and the leader of the table.

Measures:
- The model assisting the annotation is **excluded from the table of results**, or reported on a
  separate line with an explicit note.
- The final GT goes through a human. While the pipeline is being calibrated — exhaustively, on
  every sample: that is the only way to find out what the automation lets through, and the side
  result (new checklist items) matters more than the direct one. Later — selectively, plus
  necessarily everything the cycle did not close itself: `CRITICAL_FAIL`, whatever went over the
  iteration limit, whatever oscillated, and whatever has unchecked items.

**How the roles are distributed in fact, without self-deception.** The proposer, the coordinator
and the annotator are one role, and it is played by Opus 5 **together with a human in dialogue**:
decisions about edits are taken in correspondence, not autonomously. The reviewers and the probes
are the same Opus 5, but **without the human**: they get a prompt and material and report against
the contract.

There is **no** requirement at this stage that the judge be of a different family than the
generator — there is nothing to satisfy it with, and pretending it is satisfied is worse than
admitting it. What really is separated: the reviewers and the probes have neither the reference
answer, nor the history of edits, nor access to the annotation, and this is ensured by the prompt,
the working folder and the self-report of violations. What is not separated: judging the probes'
answers and editing the samples are done by one and the same participant. The compensation is the
coordinator's record (`data/reviews/<...>/coordinator.<ROUND>.md`), where the grounds for every
flag are written out in words, and a human in the loop on every decision.

A limitation for the paper follows: when evaluating models of the Claude family the result cannot
be presented on a par with the others — the annotation was done by a relative of theirs.

### 1.4. No MCQs and no skewed answer keys

In Code2Video the answer key was B=50.6% — a constant answer beat the baseline. We have **open
answers plus a rubric**, judged by an LLM against explicit criteria. If an MCQ is nevertheless
needed somewhere, a check of the key's distribution and a "majority answer" baseline are mandatory.

### 1.5. Trivial strategies must fail

Mandatory dummy baselines: "answer immediately", "answer at the end", "answer every N seconds",
"stay silent". If any of them scores decently, the design is broken.

### 1.6. Statistics

From the very beginning: a breakdown by category, the sample size in each cell, confidence
intervals (bootstrap), several runs. Claims of the form "model A is better than model B" are not
written without CIs.

### 1.7. Legal

3b1b videos are ordinary copyright (CC BY-NC-SA covers the code, not the videos). **We distribute
annotations + YouTube IDs + timecodes, not mp4s.** The download script is on the user's side.
(MMMC put 43 GB of somebody else's video on HF; we will not repeat that.)

---

## 2. The taxonomy of tasks

Three orthogonal axes. Every sample is characterised by a triple (act, temporal relation, level of
reasoning) — that gives a cube whose cells we balance across.

### Axis A — the type of proactive act

An adaptation of OmniPro's; Cumulative/Deduplicated Counting have been dropped and three
verification-counterfactual types added.

| Code | Act | Essence | Example |
|---|---|---|---|
| `alert` | Alert | report that a condition has occurred | "say when an incorrect argument is presented" |
| `monitor` | State monitoring | track an evolving quantity, report on a change | "report every time the dimension of the space under consideration changes" |
| `ground` | Grounding | point at the moment/region of an event | "when the definition of entropy appears, say so" |
| `narrate` | Narration | explain what is happening at the moment it happens | "explain every transition in the derivation at the moment of the transition" |
| `predict` | Prediction | name the next step **before** it is shown | "when the author poses the problem, say what method he will solve it with" |
| `verify` | Verification | confirm/refute the correctness of what is shown | "say whether the transition presented is valid" |
| `counterfact` | Counterfactual | "what changes if…" at the moment an object appears | "when the graph appears, say how it changes under a → 2a" |

### Axis B — the temporal relation of question and trigger

It coincides with the user's idea and with the three-part division of OVO-Bench — good, there is
something to cite.

The axis is determined by the position of the **evidence** relative to the moment the question is
issued (`question_time`), not by the position of the answer window: with a `post` question the
answer window also begins at the moment of issue, and by the window it is indistinguishable
from `at`.

| Code | Where the evidence lies | What it checks | The analogue in OVO-Bench |
|---|---|---|---|
| `pre` | appears **after** `question_time` | **the ability to wait**, not to answer too early | Forward Active Responding |
| `at` | is present **at the moment of** `question_time` | perception "here and now", there is no "when" decision | Real-Time Visual Perception |
| `post` | has passed **before** `question_time` | an answer from memory, immediately | Backward Tracing |

The label is **derived by the validator** from `question_time` and `evidence_span` rather than set
by hand: otherwise it silently diverges from the content (which is what happened in the first
iteration of the annotation — all eight samples were labelled by the criterion "where the answer
comes from", which in fact encodes axis C).

`question_time` is chosen as the latest moment when the question already makes sense but the window
has not yet arrived: the referents in the wording must exist, and the evidence must remain later
than the issue of the question.

`pre` is the main regime and the main value. `post` is useful as a control: if a model solves
`post` but does not solve the same question in `pre`, the problem is precisely proactivity rather
than understanding. **One and the same question is worth annotating in two regimes — that gives a
controlled pair.**

### Axis C — the level of reasoning (what OmniPro does not have)

| Code | Level | How the answer is obtained | Target share |
|---|---|---|---|
| `L1` | Perception | read off the screen or off the speech | ≤ 20% (30% in the pilot — see below) |
| `L2` | Integration | one has to connect ≥2 moments separated in time | ~40% |
| `L3` | Derivation | one has to carry out a computation/derivation that is **not** in the video | ~40% |

In the pilot the shares came out as `L3` 4, `L1` 4, `L2` 2 out of ten, that is, `L1` is twice the
target. (The numbers are recomputed by the validator in the "coverage" block; if they diverge from
this line, it is the line that gets fixed — that is item 9.1.) The reason is honest: two samples
were re-annotated from `L2` to `L1` after checking (both facts of the answer were spoken in a
single utterance). Fitting to target shares on a sample of ten is meaningless; we return to this
when expanding.

**The quality criterion for L3:** the answer must not follow from general knowledge of the topic —
otherwise the blind baseline solves it. It is checked mechanically (§5.3), not by eye.

### 2.1. A catalogue of "hard" question templates

This is what the whole thing is for. Eight templates, sorted by value/cost ratio.

1. **Natural-error alert** (`alert`/`pre`/`L3`) — 3b1b regularly presents a naive or incomplete
   line of reasoning which is then refuted. We put the trigger where the argument is
   **presented**, not where the author took it apart. It checks the ability to notice a mistake
   before the author does. Cheap and very strong.

2. **Premature-answer trap** (`any`/`pre`/`L2`) — a question to which the video has an early
   *plausible but wrong* answer, with the correct one later. An early answer lowers the score by
   itself: it lies outside every window, earns no PAUC and raises the FAR. It directly breaks the
   greedy strategy "answer at the first match". A property of the wording, not a field: the
   former `distractor_windows` was removed on 2026-09-07 (it duplicated the FAR for scoring and
   leaked `t_start` to the semi-blind reviewer); the proposer's intent may be recorded in the
   optional `provenance.trap_note`.

3. **Prediction-ahead** (`predict`/`pre`/`L3`) — "once the problem is posed, name the method of
   solution". The GT is what actually happened next. In streaming the model physically cannot peek.
   Pure reasoning.

4. **Counterfactual on-appearance** (`counterfact`/`at`/`L3`) — the user's idea about the
   coefficients. The trigger is the moment an object appears, the answer is the result of an
   independent computation. The answer is checked numerically/symbolically (sympy), not only by an
   LLM judge.

5. **Step-dependency** (`monitor`/`pre`/`L2`) — "report when the result obtained earlier is used".
   It requires keeping two separated moments in memory.

6. **Symbol-binding / notation tracking** (`monitor`/`pre`/`L2`) — "report when the symbol σ is
   redefined or changes meaning". Specific to lectures, almost impossible without really holding
   the context.

7. **Cross-modal conflict** (`alert`/`at`/`L2`) — a moment where speech and picture diverge (a slip
   of the tongue, "left" instead of "right", a typo in a formula). In 3b1b such places are
   documented in the errata and in the video clarifications. **The only type that fundamentally
   requires both modalities** — valuable for checking `audio_dependency`.

8. **Injected-error alert** (`alert`/`pre`/`L3`) — we inject an error by re-rendering from manim.
   The most expensive, but completely free of contamination and with an exact GT timecode. Phase 6.

**What is implemented in the pilot.** On `l6DKRf-fAAM`, templates 2, 3, 4, 5 are done plus five not
foreseen by the plan: `state_monitor`, `assumption_probe`, `speech_only_marker` and two control
twins (`post_control_twin`, `at_control_twin`). Template 1, `natural_error_alert`, is **weak but
not impossible** on this video: there are no outright mistakes, but there are two candidates — the
straightforward student's flat two-bit code (281–292), declared worse at 364.9, and an intuition
presented and immediately refuted at 773–785. Both are weaker than an injected error: the author
refutes them himself, and quickly. Template 7, `cross_modal_conflict`, likewise: no divergences of
speech and picture were found. Both require either a different video (one that goes through failed
attempts) or Phase 6 with an injected error. Inventing them on this material is not allowed — the
result would be a non-existent GT.

A good continuation (not proactive, but meaningful as a second beat): after an `alert` question
about a mistake — "fix it and complete the solution yourself". We keep this as a separate
`followup` field, score it separately, and do not mix it into the main metric.

---

## 3. The storage format

We take OmniPro's as the basis and extend it. One JSON object per sample, the file is JSONL.

The canonical example has been moved to `data/annotations/README.md` §3 and is taken from there
**verbatim from a live file**: any edit to the schema or the annotation is immediately visible in
the documentation, and the example is guaranteed to pass the validator. Previously the example was
rewritten by hand and, as it turned out on checking, did not pass its own schema and lied about the
facts (the wrong duration, a non-existent path to the source). Below is only a list of the fields
and why they are needed.

**Differences from OmniPro and what they are for:**

| Field | What for |
|---|---|
| `t_start`/`t_end` instead of a point | a GT window rather than a moment — that is how PAUC works; nobody will guess the exact frame |
| `t_ideal` | a service field, `t_start + 1`; it means nothing, the latency is measured from `t_start` |
| `rubric` | the judge scores against explicit criteria rather than "by eye" |
| `act` / `temporal_rel` / `reasoning_level` / `template` | the taxonomy axes; the breakdowns are computed over them too |
| `audio_dependency: null` until validation | filled in by a **measurement**, not by the annotator (§1.2) |
| `evidence_span` | where the information for the answer lies; axis B is derived from it (with `post` it diverges from the answer window) |
| `question_time_note` | why the question was issued at exactly this moment |
| `provenance.evidence` | a mandatory reference to the transcript/frame — protection against an invented GT. This is **confirmation**, not evidence: unlike `evidence_span` it may lie later than the window (`predict`) or outside the video (`counterfact`) |
| `validation.*` | the answers of the modality probes (checklist, group 4); `status` records draft/validated/rejected lifecycle, while `blind_solved` separately controls primary eligibility |

### 3.1. Multi-trigger samples (decided: allowed)

A `monitor` without several firings degenerates into an `alert`, so `triggers` is an ordered list
of windows rather than a single one. That drags four decisions along with it.

**1. Required and optional windows.** Not all moments are equally indisputable: there are places
where a reasonable annotator might well have stayed silent. Such windows are marked
`"required": false` — they are not penalised either for an answer or for silence, and they do not
go into the recall denominator. Without this the annotation of `monitor` turns into an argument
about taste.

```json
"triggers": [
  {"idx": 0, "required": true,  "t_start": 412.0, "t_end": 431.5, ...},
  {"idx": 1, "required": false, "t_start": 502.0, "t_end": 515.0, ...},
  {"idx": 2, "required": true,  "t_start": 688.0, "t_end": 702.0,
   "depends_on": [0], ...}
]
```

**2. The relativity of the answer.** For `monitor` a substantive answer refers to the previous state
("the dimension grew from 2 to 3", not "the dimension is 3"). The `depends_on` field lists the
windows without knowledge of which the answer cannot be complete. We score the windows
**independently** (otherwise a single miss zeroes out the whole tail and the metric loses its
resolving power), but additionally compute a chain metric — see §4.

**3. The spam strategy is the main new threat.** With N windows a model can answer every 10 seconds
and hit all of them. PAUC by itself does not penalise that. Therefore:
- **the False-Alarm Rate goes into the main table alongside PAUC**, not into an appendix; a
  spammer lands in any interval, so no annotated interval is needed to catch one (the former
  requirement of a `distractor_window` on every multi-trigger sample was dropped on 2026-09-07);
- in the report we always publish the average number of the model's answers per sample next to
  `n_triggers` — if a model produces 30 answers for 3 windows, that must be visible.

**4. We set no hard limit on the number of answers.** An upper bound ("no more than K") would turn
the task into guessing K. We regulate through the FAR.

---
---

## 4. The metric

**The main one is PAUC** (from ProactiveVideoQA), since it is the only one that takes into account
that the model produces a sequence of answers over time:

- on each GT window a polyline "time → quality of the accumulated answers" is built,
- the quality `s_p ∈ {0,1,2}` is assigned by an LLM judge against the rubric,
- PAUC = the area under the polyline / the maximum,
- the starting point is `(t_start, 0.5)` — silence is better than a confident wrong answer. A
  consequence that must be reported explicitly: the strategy "always stay silent" constructively
  gets **0.25 of the PAUC maximum** on every window. That is the floor of the scale, not a result;
  all the numbers are read relative to it, otherwise §1.5 about the dummy baselines contradicts
  itself,
- the hyperparameter `ω ∈ [0,1]` regulates the importance of timeliness by shifting the abscissas
  of the polyline's points to the left (`τ_p → τ_p − ω·(τ_p − t_start)`): at `ω = 1` a late correct
  answer is valued on a par with an early one, at `ω = 0` time is taken fully into account. We
  report at `ω = 0` and `ω = 0.5`.

**Optional windows: we compute PAUC twice.** The main number is **without them**, over the required
windows only. An optional window exists not in order to demand an answer there but in order **not
to penalise** an answer in it: the rubric permits silence, and if such a window went into the
sample's average PAUC, lawful silence would give 0.25 there and drag the result down for behaviour
the annotation declared correct. The second number — with the optional ones — is published
alongside: the difference shows how much the model makes use of the non-mandatory opportunities to
answer. The first is the one taken as sufficient. In the pilot 10 windows out of 25 are optional,
so the difference will be noticeable, and silently mixing the two quantities is not allowed.

**Additionally and obligatorily:**

- **False-Alarm Rate** — the share of answers outside all GT windows. PAUC by itself does not
  penalise talkativeness outside the windows, and for us that is critical.
- **Where the false alarms cluster** — a diagnostic, not a metric, and computed after the fact:
  the false alarms of several models are clustered in time, and a cluster is an empirically
  confirmed trap (on the pilot, `GlYgs6v2YfU` q03 at 519 s: the first configuration, before the
  correct one). This replaced the former *trap rate* over annotated `distractor_windows`, which
  measured hits on decoys guessed a priori and never checked to catch anybody.
- **Latency** — `τ − t_start` for **the first answer inside the window**, as a distribution, not a
  mean. The count starts from `t_start` precisely: that is the moment when an instantaneously
  reasoning model could already have answered (`S-29` keeps `t_start ≥ evidence_span[0]`). The
  former wording counted from `t_ideal`, which is set mechanically as `t_start + 1` — that is, an
  answer exactly on the boundary of the window would give a latency of `−1 s`. Why `t_ideal` is
  unsuitable as a reference point is in the section "Why `t_ideal` means nothing" of the checklist.
  Taking the model's very first answer is not allowed: with an early false firing one gets a
  meaningless `−1700 s`, and that already measures the FAR rather than the latency.
- **Silence rate** — the share of GT windows with not a single answer.
- **Trigger Recall** — the share of **required** windows where there was at least one answer with
  `s ≥ 1`. It separates "the model stays silent" from "the model answers, but badly" — PAUC mixes
  them.
- **Responses-per-sample** — the average number of the model's answers next to `n_triggers`.
  Always published, otherwise the spam strategy stays invisible.
- **Chain accuracy** (all windows with a non-empty `depends_on`, regardless of `act`) — the share
  of windows with a non-empty `depends_on` where the answer correctly refers to the previous state.
  Counted against a separate item of the rubric.
- Breakdowns along all three taxonomy axes + by video.

**Aggregation is over samples, not over windows.** The pilot has 25 triggers, but 9 of them belong
to one q06 (`ground`/`L1`) and 6 to q04: averaging over windows would make the final number a
hostage of two samples, one of which is the simplest in the set. We compute the metric inside a
sample (the mean over its windows) and then average over samples.

---

## 5. The plan of work by phases

### 5.0. The results of testing the download (2026-08-19)

Tested empirically on `l6DKRf-fAAM`. **Cookies and a login are not needed.** But there are three
snags:

1. **The default client `android_vr` returns dead URLs** → 403 on any download. Cured by naming the
   client explicitly: `--extractor-args "youtube:player_client=android"`. Tested: `ios`, `tv`,
   `mweb`, `web_embedded`, `android` — they work on metadata; the real video formats without a PO
   token are served only by **`android`**. `web_safari` without a PO token returns nothing but
   storyboards, `tv_embedded` returns 403.

2. **`--download-sections` does not work**: it passes the CDN URL to an external `ffmpeg`, which
   goes without the necessary headers and gets a 403.
   → **we download the video whole through yt-dlp's HTTP stack and cut it locally with `ffmpeg`.**
   48 MB in 42 s is not a bottleneck.

3. **Without a PO token only format 18 is available** (640×360, progressive h264+aac, ~48 MB for
   32 min). The DASH formats (720p/1080p) require a PO token. Readability at 360p has been checked
   by eye: the headings of the formulas are crisp, the indices `p_0…p_n` are distinguishable, the
   small axis labels are borderline. **Sufficient for the pilot.** The upgrade path if 1080p is
   needed: the `bgutil-ytdlp-pot-provider` plugin (it raises a local Node service and **still
   requires no login or cookies**).

The working command:

```bash
python -m yt_dlp \
  --extractor-args "youtube:player_client=android" \
  -f 18 \
  --write-info-json --write-subs --sub-langs en --sub-format vtt --write-description \
  -o "data/videos/%(id)s/%(id)s.%(ext)s" \
  "https://www.youtube.com/watch?v=<ID>"
```

**A pleasant surprise: the subtitles are human.** `l6DKRf-fAAM` has 13 languages in `subtitles`
(including `en`) and **an empty `automatic_captions` for en** — that is, these are manually
uploaded captions, not ASR. Whisper as a fallback will most likely not be needed. The chapters are
in place too (7 of them).

### Phase 0 — infrastructure (partly done)

- [x] `vendor/Code2Video`, `vendor/videos`, `vendor/site`
- [x] `data/3b1b_mapping.json` — 175 lessons; 170 with a YouTube ID, 159 with a declared `source`
      (155 together with an id), **140 with an id and a source that actually exists**
- [x] `vendor/PINNED.txt` — the commits of the third-party repositories, without which these
      numbers are irreproducible
- [x] `yt-dlp` 2026.07.04 installed in the conda environment `rah_manim`; `ffmpeg` 8.1.2 is present
- [x] **the download has been tested on `l6DKRf-fAAM` — cookies are NOT needed** (see §5.0)
- [x] `tools/fetch_video.py <youtube_id>` → `data/videos/<id>/`: mp4, `info.json` (chapters!),
      `.en.vtt` subtitles, `.description`
- [x] `tools/make_bundle.py` — an **annotation bundle** per video:
      - the transcript with timecodes from the vtt (3b1b's subtitles are human, Whisper was not
        needed and is not in the code),
      - frames at the chapter boundaries and every N seconds,
      - the list of LaTeX strings from the manim source (`Tex`, `MathTex`, `OldTex`, `TexText`)
        with line numbers and scene names,
      - the transcript grouped by chapter (there is no separate "chapter → frames" table, the
        correspondence is recovered from the timecodes in `bundle.json`).

The bundle is what a human annotator actually works with. Without it, annotating 20 questions on a
25-minute video turns into torture.

### Phase 1 — fixing the taxonomy and the guideline

- [ ] `docs/taxonomy.md` — the final axes and definitions
- [ ] `docs/annotation_guide.md` — 2 examples and **2 anti-examples** for each of the 8 templates.
      The anti-examples matter more than the examples: they formulate what we reject (solvable
      blind, solvable from a single frame, the answer is in the question).
- [x] `schema/sample.schema.json` + `tools/validate_samples.py`

### Phase 2 — the pilot annotation

The goal of the phase is **not volume but finding out which types are annotatable at all** on this
material.

The candidates (all with a working source in `vendor/videos`):

| Video | YouTube | Date | Role |
|---|---|---|---|
| Reinventing Entropy (Compression & Intelligence Pt.1) | `l6DKRf-fAAM` | 2026-06-07 | the main one, beyond the cutoff |
| The Hairy Ball Theorem | `BHdbsHFs2P0` | 2026-01-31 | visually rich, topology |
| Taylor series (Essence of calculus ch.11) | `3d6DsjIBzJ4` | 2017-05-07 | **the contamination control** |

- [x] a pilot of 10 samples / 25 triggers on `l6DKRf-fAAM` (see `data/annotations/README.md`)
- [ ] bring it up to 15–25 questions per video, covering the cube (act × relation × level)
- [ ] at least 2 samples for each of the 8 templates
- [x] control twins: q02/q02b (`pre`/`post`), q07/q07b (`pre`/`at`)

### Phase 3 — validating the annotation (before any experiments with models)

- [ ] `tools/run_shortcut_baselines.py`: blind / text-only / vision-only / frozen-frame /
      always-now / always-end / silent / **spam-every-N-seconds** (the last is mandatory: §3.1
      point 3 names spam as the main threat of multi-trigger samples)
- [ ] filling in `validation.*`; `rejected` is reserved for incorrect or deliberately
      abandoned samples, while `blind_solved` controls primary-set eligibility
- [ ] **measuring contamination**: compare the share of blind-solved on the 2026 video vs the 2017
      one. This is a result in its own right, worth publishing independently of the benchmark.
- [ ] computing `audio_dependency` from the measurements
- [ ] a second annotator on 30% of the samples + IAA (Cohen's κ on `act`, agreement on windows)

### Phase 4 — the harness

- [ ] `tools/stream_eval.py` — a streaming simulator: it feeds the video in portions, the model
      returns `(t, text)` or silence; support for the Gemini Live API and local streaming models
      (MMDuet2, LiveStar, MiniCPM-o)
- [ ] an implementation of PAUC + FAR + latency + silence rate, bootstrap CIs
- [ ] a judge on a model of a different family than the annotation assistant

### Phase 5 — scaling up

- [ ] semi-automatic generation of candidates: an LLM proposes questions from the bundle, a human
      accepts/edits/rejects. We log the acceptance rate by template — that is a quality metric for
      the automation itself.
- [ ] expansion to 15–20 videos with a balance over the 13 categories
- [ ] **no quotas** of the form "exactly 300 per task" (OmniPro's mistake) — however many passed
      validation is however many there are, and the imbalance is reported honestly

### Phase 6 — error injection (optional, high cost)

- [ ] install `manimgl`, check that `_2026/*` renders
- [ ] inject an error into a scene, render it, splice it with the original via `ffmpeg`
- [ ] we get samples with an **exact** GT timecode and a guarantee of absence from pre-training

Risk assessment: the old code (`_2017`) will almost certainly not build, the fresh code should.
Start only after Phases 2–4 have given a working cycle.

---

## 6. The structure of the repository

```
manim_play/
├── docs/
│   ├── plans/general.md          # this file
│   ├── taxonomy.md               # Phase 1
│   ├── annotation_guide.md       # Phase 1
│   ├── annotation_checklist.md   # classes of error and who catches them
│   ├── annotation_pipeline.md    # the working order: proposer -> reviewers -> edits
│   └── prompts/                  # drafts of the pipeline role prompts
├── articles/                     # adversarial reviews of papers
├── data/
│   ├── annotations/README.md     # the canonical example and the field reference
│   ├── 3b1b_mapping.json/.csv    # done
│   ├── videos/<youtube_id>/      # mp4, info.json, vtt (in .gitignore)
│   ├── bundles/<youtube_id>/     # material for the annotator
│   └── annotations/*.jsonl       # the samples themselves
├── schema/sample.schema.json
├── tools/
│   ├── build_3b1b_mapping.py     # done
│   ├── fetch_video.py
│   ├── make_bundle.py
│   ├── run_shortcut_baselines.py
│   └── stream_eval.py
└── vendor/{Code2Video,videos,site}
```

---

## 7. What we are doing right now

Three steps, after which annotation can begin:

1. Install `yt-dlp`, write `tools/fetch_video.py`, download the three pilot videos with their
   `info.json` and subtitles. Check that they have chapters and human (not automatic) English
   subtitles.
2. Write `tools/make_bundle.py` and assemble the bundle for `l6DKRf-fAAM`.
3. Annotate 5–8 questions by hand on a single video, covering 3–4 different templates — and see
   where the schema from §3 creaks. The schema is fixed by that result, before 60 samples have been
   invested in it.

**The decision has been taken: multi-trigger samples are allowed** (see §3.1). `monitor` must be a
full-fledged act rather than an `alert` in disguise.
