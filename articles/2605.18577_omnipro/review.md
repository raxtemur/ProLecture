---
title: "OmniPro: A Comprehensive Benchmark for Omni-Proactive Streaming Video Understanding"
authors: [Ruixiang Zhao, Jie Yang, Zijie Xin, Tianyi Wang, Fengyun Rao, Jing LYU, Xirong Li]
venue: preprint (NeurIPS 2026 template, Datasets & Benchmarks Track)
arxiv: 2605.18577
slug: 2605.18577_omnipro
code: https://github.com/RuixiangZhao/OmniPro
data: https://huggingface.co/datasets/RuixiangZhao/OmniPro
project_page: https://ruixiangzhao.github.io/OmniPro/
sources: source/
date_reviewed: 2026-08-19
review_type: adversarial
---

> A note on the topic: the paper is **unrelated** to the generation of educational videos, Manim or 3Blue1Brown. It is a benchmark for the proactive understanding of streaming audio-video. The section on the video/audio collection pipeline below is given in maximum detail, as requested, but with respect to their sources (LongVALE + COIN, YouTube).

# TL;DR

- OmniPro is a benchmark of 2,700 samples / 9,051 triggers over 1,262 YouTube videos, 9 subtasks, two evaluation regimes: Probe (accuracy) and Online (F1) [§3.1, §3.2.1].
- I recomputed every headline figure of the paper from the published `benchmark.json` and they **match exactly**: 2700/1262/3.35 resp.-per-q/84.0% audio-dep/54.1 s to the first trigger [Tab. 1].
- The main conflict of interest: Gemini-3-Flash simultaneously generates the data, judges the open-ended answers in Online mode, and is the best-scoring model evaluated (40.4 vs 22.6) [§3.1.3, §3.2.1, Tab. 2].
- The claim "the benchmark distinguishes omni models from vision-only ones" is refuted by their own table: the vision-only Qwen3-VL (19.5) beats 3 of the 5 omni models [Tab. 2].
- The conclusion "non-speech sound is the weakest dimension" is built on 6.4% of the triggers and is entirely confounded with task difficulty [Fig. 5].
- Reproducibility is strong: the code (MIT), the annotations and **all 1262 source videos** really are published; but the data-generation prompts are, contrary to the text, absent from the repository [§B.2].

---

# The problem and the motivation

The authors formulate the task of "omni-proactive streaming video understanding": the model gets one instruction at the start of the video ("tell me when the doorbell rings"), then consumes a continuous audio-video stream and decides for itself **when** to speak and **what** to say. This differs both from offline VideoQA (the question is asked after viewing) and from "streaming" in the sense of polling (an external orchestrator pokes the model every second).

The claim of a gap in the literature rests on three criteria [§1]: (1) omni-modal perception — vision, speech and non-speech sound are all needed; (2) proactive responding — the model initiates an answer itself, without polling and without fixed timestamps; (3) diverse video understanding tasks — not only alert, but also monitoring, grounding, counting, narration, prediction. It is then shown that StreamingBench-Pro (polling once a second, 250 purely visual questions, 1/6 abilities), OVO-Bench-Pro (queries at preset moments, effectively offline, 2/6) and OmniMMI-Pro (the only one with a genuine proactive regime, but one answer per question, ~35% speech, zero non-speech sound, 1/6) do not cover all three criteria [§2.2, Tab. 1].

The problem is genuinely real, and I agree that the "Pro" subsets of existing benchmarks are weak. But the construction of the argument deserves scepticism. The coverage metric "x/6 basic capabilities" is defined by the authors themselves through their own taxonomy, in which they naturally get 6/6 while the competitors get 1/6 and 2/6. This is an unfalsifiable comparison: any taxonomy invented for one's own benchmark will give that result. The word "first" occurs six times in the paper (abstract, §1 twice, contributions, §5), and every time the novelty rests on a conjunction of three conditions, two of which are already met in OmniMMI-Pro.

A separately inconvenient fact lies in their own Tab. 1: the average video duration in OmniPro is **189 s**, whereas StreamingBench-Pro has 636 s and OVO-Bench-Pro 625 s. That is, OmniPro has the shortest videos of the four, while the paper's central experimental conclusion is about "long-horizon robustness" and degradation after 180 s. The orange statistics columns are presented so that the reader looks at "# Videos" and "# Ques.", where OmniPro wins by 3–10×, rather than at "Dur. (s)", where it loses threefold.

# The method: how the benchmark is built

![An overview of the OmniPro taxonomy](figures/benchmark_overview.pdf)

**The taxonomy.** Three cognitive levels, 9 subtasks, exactly 300 samples in each [§3.1.1]. Perception: Instant Event Alert, Real-time State Monitoring, Snapshot Counting, Explicit Target Grounding. Comprehension: Event Narration, Cumulative Counting, Semantic Condition Alert. Reasoning: Deduplicated Counting, Sequential Step Instruction.

**Probe mode** [§3.2.1] is compatible with any VLM without streaming. For every GT trigger the evaluator asks a question twice: a pre-probe in the window −5…−2 s (a negative answer is expected, the event has not happened yet) and a post-probe in the window 0…+3 s (a correct answer is expected). The model sees the cumulative frames $[0,t]$. A trigger is credited **only if both probes are correct**; the metric is the share of correct triggers. Event-Narr. and Step-Inst. are converted into multiple choice, everything else is exact match.

**Online mode** [§3.2.1] — for streaming models only. The instruction is given at the start, then the model consumes the stream frame by frame together with its own dialogue history and decides for itself when to answer. The answers are matched against the GT by a greedy temporal alignment with a tolerance of ±3 s, and a match is valid only for a content-correct answer; the metric is F1 (precision penalises over-triggering). For Event-Narr. and Step-Inst. the content-correctness is scored by **Gemini-3-Flash as an LLM judge** on a 1–5 scale, threshold ≥3.

**The design of Probe mode is the most fragile point of the methodology.** Three specific complaints:

1. *The pre-probe is poorly defined for repeated events.* In Cumulative Counting ("how many times did the host say 'thank you'") and Real-time State Monitoring, by the moment of the 5th trigger the event has already happened four times. What "a negative answer is expected" means 2 s before the 5th repetition does not follow from the text; in the code it is differentiated through `count`. For Semantic Condition Alert with abstract conditions ("when somebody uses inappropriate language") a pre-probe 2 s before is a test of temporal resolution, not of understanding.
2. *There is no ablation of the probe windows.* The authors ablate the matching tolerance in Online mode (±1…±5 s, [§A.1]), but do **not** ablate the pre/post-probe offsets. Meanwhile the accuracy of the GT timestamps is a derivative of Gemini's annotation corrected by humans; an error of 2 s flips the label. Given that the post-probe window is only 0…+3 s while the pre-probe ends at −2 s, the whole protocol lives in a two-second gap.
3. *Exact match with no report of parse failures.* §3.2.1 says outright "Correctness is determined by exact match for all tasks". Weak models (VideoLLaMA2.1-AV 12.3, Phi-4-multimodal 12.9) may get low scores simply for not following the format. Neither the share of unparseable answers nor examples of the parsing appear in the paper.

# How the data were collected (in detail)

**The sources.** Two public datasets, and only their **test splits** [§3.1.2]:
- **LongVALE** (CC-BY-NC-SA-4.0) — a dataset of audio-visual correlations, long videos: everyday life, sport, news. 1,171 videos taken.
- **COIN** (CC BY-NC 4.0) — instructional videos with a step-by-step structure. 600 videos sampled at random. Needed exclusively for Sequential Step Instruction, since LongVALE has few tutorials.
- 1,771 source videos into the pipeline in total. Both datasets are public videos from YouTube.

**A check against the published data.** From `benchmark.json`: the 300 videos of `sequential_step_instruction` **do not intersect** any other subtask (these are COIN), and the remaining 962 videos are LongVALE. 1262 = 962 + 300. The median duration is 163 s, the mean 190.4 s, the range 24.1–594.6 s.

**Step 1 — Dense captioning** [§3.1.3, §B.1]. Every source video is run through **Gemini 3 Flash** with a prompt asking it to split the video into segments of 5–30 s (no longer than 45 s) covering the timeline with no gaps or overlaps, and to return for each segment a JSON with four fields: `caption` (an integrated description), `visual` (the scene, the lighting, the colours, the objects, the camera work, the on-screen text verbatim), `audio` (music with its genre/tempo/instruments, sound effects, ambience, voice quality, the moments sounds start and stop), `speech` (a paraphrase of what was said, "None" when there is none). Segmentation is triggered by a change of scene/location, a new action, a change of topic in the speech, a person appearing/leaving, an audio event or a noticeable visual change. The full prompt is given in the appendix.

**Step 2 — QA synthesis** [§3.1.3, §B.2]. The original video **plus** the dense caption are fed to Gemini together with a task-specific prompt. The output is a JSON with the schema: `question` (one instruction, issued at 00:00), `trigger_time` (MM:SS), `response`, `trigger_type` (visual / sound / speech and combinations), `audio_dependency` (required / helpful / none), `trigger_type_reason`, `event_description`, plus task-specific fields (`count`, `position`, `states`, `state_from`/`state_to`, `chosen_category`). There is an explicit escape hatch `{"status":"skip"}`.

Three declared principles: **audio-first** (look for events in the `audio`/`speech` fields first, visual ones last; the prompts state this firmly: "Audio scan (MANDATORY) first", "LISTEN FIRST", "Try your best to find an audio-required event"); **streaming constraint** (the answer must not use the future relative to the trigger; the Event Narration prompt outright forbids the words "concludes/climax/final/wraps up/ends with"); **video as ground truth** (the caption is auxiliary, the timestamps are checked against the video itself).

The prompts contain rather fine quality constraints worth noting: for Target Grounding the target must fit into a single cell of a 3×3 grid (a whole person, a close-up of a face, a large car are forbidden); for Dedup Counting an appear–disappear–reappear pattern and ≥3 unique targets are mandatory, otherwise skip; for Cumulative Counting the event must repeat ≥3 times and be discrete ("10 people would agree on the number"); for Semantic Condition Alert the condition must fail the test "would a detector + classifier have coped?"; for Step Instruction only tutorials are admissible (cooking, DIY, repair, beauty, sport), while interviews/vlogs/news/reviews are skipped.

The volume after generation: **~1,000 samples per subtask, 9,000 raw QAs** [§3.1.3].

**Step 3 — Human quality control** [§3.1.4]. Two rounds. Round 1: 9 annotators, each handling one subtask in a dedicated tool; what is checked is the naturalness of the question, the accuracy of the trigger time (the moment the event has fully happened), the factual correctness of the answer (no hallucinations), the correctness of the modality labels. Bad samples are fixed or thrown out. Round 2: the annotators swap subtasks for cross-validation. **~30% kept**, giving 2,700 samples over 1,262 videos.

**Licences and ethics** [§C.3]. LongVALE CC-BY-NC-SA-4.0, COIN CC BY-NC 4.0, OmniPro itself CC BY-NC 4.0, the code MIT. It is asserted that "our licence is compatible with the licences of the sources".

**What is wrong here:**

- **A quota, not a filter.** The final set has exactly 300 samples, exactly 300 unique videos and exactly 1 sample per video in each of the 9 subtasks. That is not the result of an honest filtering of ~30% out of 1000 — it is a selection down to a round quota. Which means the retention rate differed by subtask, and the set was trimmed down to 300 by an undescribed method. If it was trimmed "top-down by quality", the final set is systematically biased towards what Gemini generates confidently — that is, towards the samples Gemini itself then solves best of all.
- **Not a single figure on annotator agreement.** No κ, no percentage of edits vs discards, no data on the annotators' qualifications/pay/language, no adjudication protocol for disagreements in round 2. For a D&B track this is a substantial gap; "human-verified" in the abstract remains unverifiable.
- **A contradiction about the generating model.** §3.1.3 says "Gemini 3 Flash" both for captioning and for QA synthesis; §B.2 says the prompts "are fed to **Gemini 2.5 Flash**". Which model actually produced the GT is unknown from the paper.
- **A false statement about the availability of the prompts.** §B.2: "Full prompts are available in the code repository". At the time of checking, the repository contains neither a data-generation directory nor those prompts: there is only `utils/prompts.py` with the **evaluation** prompts, `evaluators/`, `metrics/`, `models/`, `scripts/`. The full data-generation pipeline is not reproducible.
- **Question diversity.** 81 samples have a question text that coincides verbatim with another's; one template ("Count how many different people are interviewed and speak on camera in this video.") occurs **34 times** — 11% of the whole Dedup Counting subtask. That is a template collapse in the generator, not diversity.
- **A licensing stretch.** LongVALE is distributed under CC-BY-NC-**SA**-4.0. OmniPro — a derivative work — is relicensed under CC BY-NC 4.0 without ShareAlike, while compatibility is asserted. And separately: the 1,262 mp4s from YouTube are themselves published on HuggingFace; a CC licence on the source dataset's annotations grants no rights to redistribute the videos.
- **84% is a marketing aggregation.** "84% depend on audio" = `required` (1768, 65.5%) + `helpful` (500, 18.5%). "Helpful" by definition means audio is **not** obligatory. The honest formulation: 65.5% require audio. On top of that, the `audio_dependency` labels themselves were produced by Gemini (humans only checked them), so the abstract's key figure is at bottom an LLM's self-assessment. The distribution is extremely uneven across tasks: Target-Ground has 288/300 required, while Dedup-Count has only 17/300 required against 121 "none".
- **Small annotation defects** (I checked the whole `benchmark.json` programmatically; the scale is small, but it compromises "human-verified"): 5 samples have triggers **later than the end of the video** (the worst: `instant_event_alert::1PglWltNB1M::18` — a duration of 104 s, a trigger at 457 s); 1 sample with non-chronological triggers; 3 with duplicated timestamps; 4 dedup-counting samples whose counter is not 1..N; 4 "state transitions" with `state_from == state_to`. There are substantive desynchronisations too: in `cumulative_counting::0JTW1IMJ9d0::0` the question is about squats with a fitness ball, while every `event_description` is about a "pull of yarn to measure tail", and all 5 triggers (110–120 s) go beyond the duration of 92 s. One such sample is two independent failures of both review rounds on a single object.
- **Contamination risk.** The videos are taken from the test splits of **public** datasets widely used for training. COIN is a standard corpus for instructional-video models; LongVALE supplies omni-modal instruction-tuning data. Several of the models evaluated (Qwen2.5/3-Omni, MiniCPM-o, video-SALMONN 2+) have most likely seen these YouTube videos or their annotations during pre-training. Neither an overlap check nor a decontamination analysis appears in the paper. Secondarily: publishing all 1262 mp4s guarantees the contamination of future models.

# Experiments and results

**The setup** [§4.1]. 11 models. Probe (9): InternVL3.5-8B, Qwen3-VL-8B (vision-only), Qwen2.5-Omni-7B, Qwen3-Omni-30B, video-SALMONN 2+ 7B, VideoLLaMA2.1-AV-7B, Phi-4-multimodal-14B, Gemini-3-Flash, MiniCPM-o 4.5 9B. Online (3): MiniCPM-o 4.5, MMDuet2-3B, LiveStar-8B. Everywhere 1 fps, greedy decoding, max 512 tokens, A800 80GB.

**The main table** [Tab. 2]. Probe: Gemini-3-Flash 40.4 against the best open model MiniCPM-o 4.5 at 25.8 and Qwen3-Omni at 22.6. Online: MiniCPM-o 4.5 20.9, MMDuet2 11.3, LiveStar 3.6. The modality ablation [Tab. 3]: A+V is consistently better than V, with gains from +2.4 (Qwen3-Omni) to +11.1 (video-SALMONN 2+). Temporal degradation [Fig. 4]: on average 37% of the Short-term result survives into Long-term; MiniCPM-o in Online falls 29.1 → 0.3; even Gemini goes 38.5 → 17.9. The radar by trigger modality [Fig. 5]: every model is weakest on visual+sound (15.3–22.3).

**The honesty of the baselines and the correctness of the conclusions:**

- **Gemini-3-Flash is participant, task author and judge at once.** It produced the dense captions, produced the questions/answers/GT timestamps, produced the distractors for the MCQ versions of Event-Narr. and Step-Inst., and it also judges the open-ended generation in Online mode. And it wins by a wide margin precisely where its own annotation defines the right answer: Event-Narr. 86.4 (next best 55.8) and Step-Inst. 76.3 (next best 31.6). Those are two tasks out of nine, and they pull up its average. Without them its mean falls to about 28.8 against 24.6 for MiniCPM-o — "almost twice as good as the open models" turns into "4 points better". No control for self-preference (a second independent judge, human agreement with the judge, a cross-check on a subset) appears in the paper.
- **The key claim is refuted by their own table.** §3.1.5 asserts that almost half the triggers are cross-modal and that this "ensures the benchmark can differentiate omni models from vision-only counterparts". In Tab. 2 the vision-only Qwen3-VL-8B (19.5) beats the omni models Qwen2.5-Omni-7B (20.1 — almost level), Phi-4-multimodal-14B (12.9) and VideoLLaMA2.1-AV-7B (12.3), and the vision-only InternVL3.5 (12.1) is level with two omni models. There is no separation by model class; the advantage of audio is demonstrated only **within a single model** in the ablation [Tab. 3], which proves merely that an audio input is not useless, not that the benchmark discriminates omni architectures.
- **The Online comparison is unfair by construction.** MMDuet2 and LiveStar are vision-only, and they are run on a benchmark where 84% of the samples are labelled as depending on audio. The gap of MiniCPM-o 20.9 vs MMDuet2 11.3 is attributed to general proactive ability. But Tab. 3 has a MiniCPM-o **V-only: 13.8** row. That is, with equal access to modalities the gap collapses from +9.6 to **+2.5**. The authors make this obvious control comparison neither in the text nor in the caption.
- **Mixed metrics in one table.** In Tab. 3 the rows for Qwen2.5-Omni, video-SALMONN 2+, Qwen3-Omni and Gemini are Probe accuracy, while the MiniCPM-o 4.5 row coincides numerically with its Online F1 from Tab. 2 (44.2/13.9/24.3/…, mean 20.9). The caption does not mention this, and the Δ gains between rows are incomparable.
- **Zero statistics.** No confidence intervals, no tests, no repeats. With n=300 per subtask the standard error at p≈0.2 is about 2.3 pp; with n=2700 about 0.8 pp. The order InternVL3.5 (12.1) / VideoLLaMA2.1 (12.3) / Phi-4 (12.9) is statistically indistinguishable but is presented as a ranking; the bolded "second-best" over gaps of 0.1–0.5 pp in individual columns (n=300) is noise. Gemini-3-Flash is an API model for which even greedy decoding does not guarantee determinism, and no repeated runs were made.
- **Not a single trivial baseline.** No random, no majority-class, no blind-LLM (the question text only), no human ceiling. This is critical, because the answer distributions are heavily skewed: in Target-Ground the answer "center" covers **33.7%** of the positions (while the best model scores 18.1), and in Snapshot Counting the answer "2" covers **32.3%** of the GT counts. The reader cannot tell whether Gemini's 21.0 on Snap.-Count is above or below constant guessing under their paired protocol. Without a human ceiling the absolute 40.4% is not interpretable at all: it is unknown whether the ceiling is 95% or 55%.
- **The non-speech sound conclusion rests on 6.4% of the data and is confounded with the tasks.** I recomputed the distribution of trigger_type over the 9051 triggers: visual+speech 3833, visual 2157, speech 2055, **visual+sound 581 (6.4%)**, sound 271 (3.0%), visual+sound+speech 80, sound+speech 74. So the radar conclusion "non-speech audio remains a shared bottleneck" leans on the visual+sound bucket. Worse, that bucket is heavily confounded with the task mix: visual+sound is 58% State-Monitor (137), Event-Narr. (125), Cum.-Count (82), Snap.-Count (54) — that is, objectively hard tasks; while the "visual" bucket is 27% Step-Inst. (593) — the easiest task for Gemini (76.3). There is no separation of "modality vs task difficulty"; the stated conclusion does not follow from the slice presented.
- **Temporal degradation: the confound is partly removed, but the cause is substituted.** I checked the obvious hypothesis "it is the task mix": weighting the models' per-task accuracy by the number of triggers in each temporal bucket, I get 47.5 / 49.8 / 47.9 (S/M/L) for Gemini and 18.2 / 17.9 / 19.4 for MiniCPM-o — that is, the task mix alone predicts a **flat** profile. The observed fall is real and is not explained by that confound; here the paper takes the punch. However, the causal attribution "limited long-horizon robustness" is not the only one available: the mean trigger **index** inside a sample grows across the buckets 1.99 → 3.40 → 4.02, and the mean video duration goes 142 → 200 → 355 s. 76–79% of the triggers belong to tasks with a cumulative dependence (counters, chains of states, narration), where an error on the 3rd trigger mechanically breaks the 4th. On top of that, with cumulative frame feeding [0,t] the later triggers mean more frames and potential context truncation, that is, an artefact of the protocol. Neither a breakdown by trigger index, nor a control for video length, nor a separation of order-dependent and order-independent tasks appears in the paper.
- **A generalisation from n=1.** The claim "online streaming models nearly fail beyond 180 s" is obtained on a single model (MiniCPM-o), because the other two Online models are vision-only and their scores are near zero from the start. In the Online regime exactly **one** omni model is evaluated at all — even though Online is the declared main contribution of the protocol.

# Limitations and threats to validity

The authors' limitations section [§C.1] is **one paragraph** about the benchmark being English-only. For a dataset track that is unacceptably little: it acknowledges neither the LLM origin of the ground truth, nor the self-judging, nor the contamination risk from public test splits, nor the absence of a human ceiling, nor the fragility of exact match and of the probe windows.

Beyond what is listed above I would add: (a) 724 of the 1262 videos are used in more than one subtask (up to 8 tasks per video), which reduces the effective independence of the samples and correlates the errors between tasks when aggregating into the Mean; (b) the Mean metric is an unweighted average over 9 subtasks of 300 samples each, but with different numbers of triggers (from 300 for Snap.-Count to 1709 for Step-Inst.), so the per-task accuracies are computed on very different n and the Mean implicitly re-weights; (c) the LLM judge's threshold "≥3 = correct" on a scale where 3 is defined as "captures the right event but with notable inaccuracies" is generous and is in no way calibrated against humans; (d) the abstract gives the URL `https://OmniPro.github.io/OmniPro/`, which returns 404 (the working one is `ruixiangzhao.github.io/OmniPro`).

**Reproducibility is a strength and must be acknowledged honestly.** Really available and verified: the GitHub `RuixiangZhao/OmniPro` under MIT with the full evaluation code (`evaluators/probe_evaluator.py`, `evaluators/online_evaluator.py`, the probe/online metrics, an LLM judge with two providers, wrappers for all 11 models, per-model shell scripts including the `_noaudio`/`_audioonly` variants, `requirements.txt`); HuggingFace `RuixiangZhao/OmniPro` under CC BY-NC 4.0 with `benchmark.json`, `metadata.jsonl` and **all 1262 mp4s** (1266 files, 1547 downloads). This is substantially better than the median benchmark paper. Not available: the data-generation pipeline and the full generation prompts (contrary to §B.2), the annotation interface, the raw 9000 before filtering, the log of the annotators' decisions, the models' predictions and evaluation logs, a leaderboard.

# Positioning relative to adjacent work

OmniPro sits at the intersection of three lines. The first is proactive streaming models, which the authors divide into token-driven (VideoLLM-online, StreamO, MMDuet2, MiniCPM-o), classification-head (StreamBridge, Dispider, StreamMind) and signal-driven (LiveStar, TimeChat-Online) [§2.1]; it is exactly this taxonomy the benchmark is meant to tell apart, although in the Online regime only one representative of each of the first two groups and one of the third are actually tested. The second is proactive benchmarks: StreamingBench, OVO-Bench, OmniMMI, relative to which novelty is claimed and from which OmniPro differs by a genuine multi-trigger online protocol (3.35 answers per question against 1.0 for StreamingBench-Pro and OmniMMI-Pro) and by the presence of non-speech sound. The third is the data sources: LongVALE as a supplier of audio-visually correlated long videos and COIN as a supplier of procedural tutorials; in effect OmniPro is a re-annotation of their test splits by Gemini into a proactive format. The closest competitor in spirit is OmniMMI-Pro; the main substantive advance over it is multi-trigger with a penalty for over-triggering and the introduction of non-speech sound as a separate class of triggers, rather than being "the first benchmark" in any absolute sense.

# The overall assessment

A useful, carefully published resource with an honest engineering part and genuinely open artefacts, but with overstated conclusions. What I would accept without reservation: the formulation of the task, the Online protocol with multi-trigger and a penalty for over-triggering, the fact that every headline statistic matches the published data, the full release of the videos and the code. What requires rework before acceptance: (1) a judge independent of Gemini and a control for self-preference, or else the exclusion of Gemini from the leaderboard; (2) trivial baselines (random/majority/blind) and a human ceiling; (3) confidence intervals and no ranking within the noise; (4) a contamination check against COIN/LongVALE; (5) separating modality from task difficulty in the non-speech sound analysis; (6) separating "position in time" from "index in the chain of answers" in the degradation analysis; (7) annotator agreement statistics and a description of the selection down to the quota of 300; (8) publication of the data-generation prompts, which the appendix already promises.

# Anchors

- `abstract: source/sections/abstract.tex:L2 — the abstract; also the broken URL OmniPro.github.io`
- `three_criteria: source/sections/introduction.tex:L5 — the three criteria of a good omni-proactive model`
- `novelty_claim: source/sections/introduction.tex:L7 — the discussion of the shortcomings of StreamingBench-Pro/OVO-Bench-Pro/OmniMMI-Pro`
- `key_findings: source/sections/introduction.tex:L20 — the three main conclusions (+2.4..+11.1, 37%, non-speech)`
- `related_benchmarks: source/sections/related_work.tex:L15 — a line-by-line discussion of the competing benchmarks`
- `taxonomy: source/sections/benchmark.tex:L13 — 3 levels, 9 subtasks, 2700 samples`
- `data_sources: source/sections/benchmark.tex:L47 — LongVALE 1171 + COIN 600 = 1771 videos`
- `dense_captioning: source/sections/benchmark.tex:L53 — Gemini 3 Flash, 4 description fields`
- `qa_synthesis: source/sections/benchmark.tex:L56 — the field schema of a QA sample`
- `generation_principles: source/sections/benchmark.tex:L58 — audio-first, streaming constraint, video as GT`
- `raw_scale: source/sections/benchmark.tex:L60 — ~1000 samples per subtask, 9000 raw`
- `human_qc: source/sections/benchmark.tex:L65 — 9 annotators, 2 rounds, retention ~30%`
- `dataset_stats: source/sections/benchmark.tex:L115 — first trigger 54.1 s, last 126.2 s`
- `probe_protocol: source/sections/benchmark.tex:L126 — pre-probe window -5..-2 s, post-probe 0..+3 s, exact match`
- `probe_metric: source/sections/benchmark.tex:L128 — paired accuracy (both probes correct)`
- `online_protocol: source/sections/benchmark.tex:L130 — Gemini-3-Flash as the LLM judge, threshold >=3`
- `online_metric: source/sections/benchmark.tex:L132 — F1, greedy alignment, tolerance +-3 s`
- `eval_models: source/sections/experiments.tex:L10 — the line-up of 11 models by regime`
- `impl_details: source/sections/experiments.tex:L13 — 1 fps, greedy, 512 tokens, A800 80GB`
- `main_claims: source/sections/experiments.tex:L21 — four observations on Tab. 2`
- `modality_ablation_claims: source/sections/experiments.tex:L29 — the conclusions from Tab. 3`
- `temporal_claim: source/sections/experiments.tex:L35 — 37% retention, MiniCPM-o 29.1->0.3, Gemini 38.5->17.9`
- `modality_radar_claim: source/sections/experiments.tex:L57 — visual+sound 15.3-22.3 as the bottleneck`
- `benchmark_comparison_table: source/tables/benchmark_comparison.tex:L14 — Tab. 1, including Dur. 189 s for OmniPro against 636/625`
- `main_results_table: source/tables/main_results.tex:L17 — Tab. 2, Probe (L17-L25) and Online (L29-L31)`
- `audio_ablation_table: source/tables/audio_ablation.tex:L13 — Tab. 3; the MiniCPM-o row (L29-L31) is Online F1`
- `tolerance_ablation: source/appendix/more_results.tex:L14 — the ablation of the tolerance +-1..+-5 s`
- `dense_caption_prompt: source/appendix/data_details.tex:L10 — the full dense captioning prompt`
- `model_discrepancy: source/appendix/data_details.tex:L78 — "Gemini 2.5 Flash" against "Gemini 3 Flash" in §3.1.3`
- `prompt_iea: source/appendix/data_details.tex:L80 — the Instant Event Alert prompt (audio-first)`
- `prompt_etg: source/appendix/data_details.tex:L134 — the Target Grounding prompt (3x3 grid)`
- `prompt_rsm: source/appendix/data_details.tex:L189 — the State Monitor prompt (audio scan mandatory)`
- `prompt_sc: source/appendix/data_details.tex:L249 — the Snapshot Counting prompt`
- `prompt_sca: source/appendix/data_details.tex:L309 — the Semantic Condition Alert prompt`
- `prompt_cc: source/appendix/data_details.tex:L365 — the Cumulative Counting prompt (categories A-D)`
- `prompt_en: source/appendix/data_details.tex:L426 — the Event Narration prompt (streaming constraint)`
- `prompt_dc: source/appendix/data_details.tex:L483 — the Dedup Counting prompt (appear-disappear-reappear)`
- `prompt_ssi: source/appendix/data_details.tex:L543 — the Step Instruction prompt (tutorials only)`
- `limitations: source/appendix/ethics_limitations.tex:L8 — the single acknowledged limitation (English-only)`
- `licenses: source/appendix/ethics_limitations.tex:L26 — CC-BY-NC-SA-4.0 -> CC BY-NC 4.0`
- `project_page: source/main.tex:L84 — the working link ruixiangzhao.github.io/OmniPro`
- `architecture_diagram: figures/benchmark_overview.pdf — Fig. 1, an overview of the taxonomy (a copy of source/figures/benchmark_v3.pdf)`
- `temporal_figure: figures/temporal_position_ablation.pdf — Fig. 4, degradation by temporal bucket`

# Glossary

- `omni-proactive streaming video understanding` — the ability of a model, while consuming a continuous audio-video stream, to decide for itself **when** to speak and **what** to say, without external queries.
- `Probe mode` — an evaluation regime for any VLM without streaming: for each GT trigger two probes are asked (5–2 s before and 0…+3 s after), and the trigger is credited only if both are correct.
- `Online mode` — a regime for streaming models: the instruction at the start, frame-by-frame consumption, the model initiating the answers itself; the metric is F1 with a tolerance of ±3 s.
- `trigger time` — the timestamp at which a proactive model is obliged to produce an answer; the key quantity of the whole annotation.
- `trigger modality` — a label saying which modality is needed to detect the trigger: `visual` / `sound` / `speech` and their combinations.
- `audio dependency` — a label `required` / `helpful` / `none`; the claimed "84% audio" is the sum of the first two.
- `non-speech sound` — sound that is not speech (ambience, sound effects, music), singled out by the authors as a separate class of triggers and declared the models' weakest dimension.
- `paired accuracy` — the Probe mode metric: the share of triggers for which both the pre-probe and the post-probe are correct.
- `over-triggering` — a model's superfluous answers outside the GT triggers; penalised through precision in the Online F1.
- `-Pro suffix` — the designation of the proactive subset of an existing benchmark (StreamingBench-Pro, OVO-Bench-Pro, OmniMMI-Pro).
