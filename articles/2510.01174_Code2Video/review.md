---
title: "Code2Video: A Code-centric Paradigm for Educational Video Generation"
authors: [Yanzhe Chen, Kevin Qinghong Lin, Mike Zheng Shou]
venue: "arXiv v1 is typeset with the ICLR 2026 template (iclr2026_paper.sty); the repository is marked \"[ICML 2026]\". What is reviewed is arXiv v1 — not a camera-ready."
arxiv: 2510.01174
slug: 2510.01174_Code2Video
code: https://github.com/showlab/Code2Video
data: https://huggingface.co/datasets/YanzheChen/MMMC
sources: source/
date_reviewed: 2026-08-19
review_type: adversarial
---

# TL;DR

- A planner–coder–critic generates Manim code; the main engineering contribution is discretising the canvas into a 6×6 grid (the visual anchor) and the local auto-fix ScopeRefine [§4.2, §4.3].
- The claimed "+40%" is +45 points on a 0–100 scale against the same backbone without the agent; the cost, meanwhile, is 15–20× higher in tokens [Tab. 1].
- The "unlearning" in TeachQuiz is a prompt instruction to refuse to answer. The baseline after "forgetting" is 5.0% against 25% for random guessing and 50.6% for the constant answer "B" [§A.1.1, Tab. 5].
- The answer key of the published quiz set is degenerate: B=50.6%, C=39.3%, A=8.5%, D=1.5% (585 questions); the repository has 5 questions per topic while the paper claims 10.
- The VLM judge's prompt explicitly demands that "presentation (left side)" and "animation (right side)" be scored — that is, it is hard-wired to Code2Video's own layout [source/eva_aes.tex:L17-L19].
- The data are a yt-dlp scrape of the 3Blue1Brown channel (117 videos), cut by YouTube chapters (339 clips, all of them from 49 videos); the Manim sources in 3b1b/videos were not used.

---

# Problem & Motivation

The paper attacks a real hole. Diffusion and autoregressive text-to-video models can make pretty 5–10-second clips but cannot: (a) draw readable text and formulas, (b) hold a spatial composition for tens of minutes, (c) build the logical sequence "concept → example → recap". For an educational video all three are critical, while perceptual fidelity is secondary [§1]. The authors propose changing the substrate of the generation: not pixels but executable code (Manim), which by construction gives determinism, interpretability and exact control over time and position [§1, §3.1].

The motivation is valid, but the wording "a new paradigm" is an overstatement. Generating Manim code with an LLM agent was not a new idea at the time of publication: TheoremExplainAgent (TEA, `ku2025theoremexplainagent`) did exactly that half a year earlier, and the authors acknowledge it by relegating the comparison with TEA to the appendix [§A.1.4]. The real delta contribution is not a "paradigm" but three engineering devices: an explicit grid of anchors, a per-block auto-fix and parallel rendering by section. This is solid but incremental work sold as a change of paradigm.

The second half of the motivation — "how to evaluate an educational video" — is claimed as the main conceptual contribution (the TeachQuiz metric). It is here that the work is most vulnerable, and I go through it in detail below.

---

# Method

## The general scheme

Input: a topic string $\mathcal{Q}$ (for example "Linear transformations and matrices"). Output: an mp4 assembled by concatenating the rendered sections.

![The Code2Video architecture](figures/approach.png)

**(i) Planner.** Two-stage. First an outline $\mathcal{O} \leftarrow \mathcal{P}_{\rm outline}(\mathcal{Q})$, where $\mathcal{O}=\{o_1,\dots,o_n\}$ and each $o_i$ contains an id, a title, a summary of the content, examples and — this is emphasised separately — the target audience (schoolchild/student) [§4.1(i)]. Then a storyboard $s_i \leftarrow \mathcal{P}_{\rm storyboard}(o_i)$: a set of lecture lines plus descriptions of the animations [§4.1(ii)]. In parallel an External Database $\mathcal{D}$ works: asset needs $a_i \leftarrow \mathcal{P}_{\rm asset}(s_i)$ are extracted from the storyboard, reference images are pulled from Google Images and filtered by a CLIP-similarity threshold, icons come from the Iconfinder API; everything is cached in $\mathcal{D}_{\rm asset}$ and reused between sections [§4.1, §A.1.7, §5.1].

**(ii) Coder.** Every section is coded independently: $c_i = \mathcal{P}_{\rm coder}(s_i, \mathcal{A})$, where $\mathcal{A}$ is the shared asset cache. The parallelism here is exactly at the level of sections, including the debugging and the refinement; the shared asset cache is the sole mechanism of consistency between the parallel branches [§4.2(i)].

The debugging is **ScopeRefine (SR)**, a three-level "go-to" repair:
- *(a) line scope*: $\mathcal{S}_1 = \text{line} \pm 1$, up to $K_1$ local edits;
- *(b) block scope*: $\mathcal{S}_2 = \mathcal{B}_{i,j}$ — the block of code corresponding to one lecture line, up to $K_2$ attempts;
- *(c) global scope*: a full regeneration of the section $c_i$ from $s_i$ [§4.2(ii)].

In the repository's code these budgets are `max_fix_bug_tries=10`, `max_regenerate_tries=10`, `max_feedback_gen_code_tries=3`, `max_mllm_fix_bugs_tries=3`, `feedback_rounds=2` (`src/run_agent.sh`). That is, up to 10 repair attempts per section.

**(iii) Critic.** The key device is the **visual anchor prompt** $\mathcal{P}_{\rm vis}$: the canvas is discretised into a 6×6 grid (A1…F6), with fixed Manim coordinates assigned to each cell, inherited from the base class `TeachingScene`. Small objects are placed in a single cell (*point-level*), large ones in a bbox defined by two corner anchors (*region-level*) [§4.3(i)].

![The visual anchor prompt](figures/anchor.png)

Critical for what follows: the grid occupies **only the right half of the frame**, the left being hard-reserved for the lecture lines. This is stated outright in the coder's prompt: `Grid layout (right side only): lecture | A1 A2 ... F6` and `NEVER use .to_edge(), .move_to(), or manual positioning!` [source/d-coder.tex:L24-L37]. That is, Code2Video produces videos with a fixed two-panel composition.

The Critic (Gemini-2.5 Pro) then looks at the rendered section $\mathcal{V}_i$ together with the code $c_i$ and an *occupancy table* — a table of "element → anchor(s), scale, lines of code". This gives indexability (tracing a visual defect down to a line) and knowledge of the free cells. Three classes of defect are looked for: an overlap inside a cell, the animation overlapping the lecture lines, and large empty areas. The result: $\tilde{c}_i = \mathcal{P}_{\rm refine}(c_i, \mathcal{V}_i)$, $\widetilde{\mathcal{V}} = \mathrm{Render}(\{\tilde c_i\})$ [§4.3(ii)].

The idea of discretisation is sensible and, judging by the ablation, works: 6×6 gives AES avg 79.0 against 69.2 without anchors and 70.3 with self-directed placement; 8×8 degrades to 76.0 [Tab. 7].

## The metrics

**AES**: VLM-as-a-Judge (Gemini-2.5 Pro), five axes of 20 points each — Element Layout, Attractiveness, Logic Flow, Visual Consistency, Accuracy & Depth [§3.3].

**TeachQuiz**: a two-stage protocol. Stage 1 is "unlearning": the model is given a prompt forbidding it to use any knowledge of the concept $\mathcal{K}$ and requiring it to answer `INSUFFICIENT EVIDENCE / NULL` if the answer requires the blocked knowledge. This gives $S_1(\mathcal{K})$. Stage 2 is "learning-from-video": the same block plus the video attached, with only the video allowed as support. This gives $S_2(\mathcal{K},\mathcal{V})$. The metric:

$$\mathrm{TQ}(\mathcal{K}, \mathcal{V}) = S_2(\mathcal{K}, \mathcal{V}) - S_1(\mathcal{K})$$

[§3.3, Eq. 1–2; §A.1.1].

![TeachQuiz: the gap between Unlearning and Learning-from-Video](figures/quiz.png)

**Efficiency**: the mean code generation time and the tokens per topic [§3.3].

---

# Experiments & Results

## The main table

Four classes of method: human-made 3B1B (the upper bound), pixel diffusion (OpenSora-v2, Wan2.2-T2V-A14B, Veo3), direct generation of Manim code by a single LLM, and Code2Video [§5.1]. The judge is Gemini-2.5 Pro; the Critic inside the pipeline is also Gemini-2.5 Pro.

| Method | Time (min) | Token (K) | AES avg | Quiz |
|---|---|---|---|---|
| Human-made 3B1B | — | — | **99.7** | **97.1** |
| OpenSora-v2 | 27.6 | — | 3.7 | 0.0 |
| Wan2.2-T2V-A14B | 17.4 | — | 6.0 | 0.0 |
| Veo3 | 2.3 | — | 9.0 | 2.5 |
| GPT-5 (direct code) | 1.8 | 1.1 | 32.7 | 36.5 |
| GPT-4.1 (direct code) | 2.1 | 1.2 | 34.2 | 37.0 |
| Claude Opus 4.1 (direct code) | 2.8 | 2.3 | 37.8 | 40.0 |
| Code2Video (GPT-5) | 8.8 | 19.3 | 72.2 | 80.0 |
| Code2Video (GPT-4.1) | 15.4 | 30.8 | 79.0 | 82.0 |
| Code2Video (Claude Opus 4.1) | 13.8 | 43.1 | **87.9** | **86.0** |

[Tab. 1]

The deltas within a single backbone really are large (+50.1 AES / +46.0 Quiz for Claude). This is the work's most convincing result: the agentic scaffolding greatly improves direct generation at a fixed model.

## Ablations

The components (on GPT-4.1, base 79.0 / 82.0) [Tab. 2]:
- w/o Planner: 38.1 / 40.5 (−40.9 / −41.5)
- w/o External Database: 68.1 / 52.0 (−10.9 / −30.0)
- w/o Visual Anchor: 69.2 / 55.2 (−9.8 / −26.8)
- w/o Critic: 72.5 / 60.7 (−6.5 / −21.3)

Efficiency [Tab. 3]: without parallelism 15.4 → 86.6 min (5.6×); SR → Retry: 42.9 min / 49.8K; SR → Full-code Debug: 39.2 min / 42.1K; without both: 149.8 min / 52.6K (9.7×). This is an honest and useful ablation — the only one in the paper where the quantity measured does not depend on an LLM judge.

Anchor granularity [Tab. 7]: w/o 69.2 → 4×4 76.9 → **6×6 79.0** → 8×8 76.0; Center Point 69.7, Self-directed 70.3.

The ablation of evidence sources for TeachQuiz [Tab. 5]:

| | Unlearn | Relearn | Δ=TQ | Text-only | Animation | Random |
|---|---|---|---|---|---|---|
| Code2Video (GPT-5) | 5.0 | 85.0 | 80.0 | 27.2 | 72.1 | 2.0 |
| Code2Video (GPT-4.1) | 5.0 | 87.0 | 82.0 | 22.1 | 75.0 | 5.0 |
| Code2Video (Claude Opus 4.1) | 5.0 | 91.0 | 86.0 | 24.0 | 76.6 | 4.0 |

The human study [Tab. 4]: five groups of 8 people (6 schoolchildren + 2 university students per group), each watching one type of video, 20 topics × 5 questions. 3B1B: AES 96.5, Quiz 78.8, CW 36.2, AR 1.2. Code2Video (Claude): AES 81.8, Quiz **80.3**, CW **64.0**, AR 1.8.

TheoremExplainBench [Tab. 6]: Code2Video (GPT-4o) overall 0.88 against TEA (GPT-4o) 0.78 and "human-made Manim videos" 0.77.

---

# The critical discussion: claims not closed by experiments

## 1. "Videos comparable to human-crafted tutorials" / "even outperform"

The abstract says "comparable to human-crafted tutorials", the introduction says something stronger: "agentically generated videos even outperform professional human-made tutorials" [§1, L38]. Inside the paper this is contradictory:
- By the automatic metric the human wins comfortably: 99.7/97.1 against 87.9/86.0 [Tab. 1]. A gap of 11–13 points is not "comparable".
- The only ground for "outperform" is the human study: Quiz 80.3 against 78.8 [Tab. 4]. A difference of 1.5 points, n = 8 participants per group, a between-subjects design, no confidence intervals, no significance test. Such a result is indistinguishable from noise.
- Worse: the "Quiz" columns in Tab. 1 and Tab. 4 measure **different quantities**. In Tab. 1 it is $\mathrm{TQ} = S_2 - S_1$ with $S_1 \approx 5$. For the humans no "unlearning" was carried out at all — the appendix says outright that the schoolchildren are "closer to a true unlearned state" [§A.1.2], that is, no subtraction was done. So the human "Quiz" is raw accuracy while the machine one is a difference. They cannot be compared.

## 2. An arithmetic inconsistency in TeachQuiz for 3B1B

$S_1$ by definition does not depend on the video — it is the model's accuracy under the unlearn prompt on the given question set. In Tab. 5 it equals 5.0 for all three rows, consistent with that property. Then $\mathrm{TQ} \le 100 - S_1 = 95$. But Tab. 1 claims **97.1** for human-made 3B1B. Either a different $S_1$ was used for the human row (unreported), or a different set of topics, or the number is inconsistent. $S_1$ is never given in the main table — and without it every value in the Quiz column is uncheckable.

## 3. The perfect 100.0 for the human

Human-made 3B1B gets exactly 100.0 from the VLM judge on four of the five axes: AT, LF, VC, AD [Tab. 1]. The judge's prompt allows an "exact decimal" [source/eva_aes.tex:L62]. For the average over a set of videos to come out at exactly 100.0 on four independent axes, the judge must have awarded the maximum on **every** call. For a stochastic Gemini that is practically impossible. The most likely explanation is that either one or two videos were scored, or the row was entered by hand as a "reference". Either way the human row in Tab. 1 is not a measurement comparable with the rest.

## 4. The External Database ablation is internally inconsistent

Removing the External Database costs −30.0 points of Quiz [Tab. 2]. But in the published data a reference image exists for only **43 of the 117** topics (`metadata.jsonl`), and in `json_files/long_video_ref_mapping.json` in the repository there are 30 non-empty values out of 117 in all. The appendix itself admits that for abstract topics (Topology) there are no references [§A.1.7]. A component absent from 63–74% of the topics cannot cost −30 points across the whole benchmark, unless the ablation also removed the Iconfinder icons — but that is not separated out. The mechanism of the effect is not established.

## 5. Efficiency is presented one-sidedly

The "Efficiency Components" section compares Code2Video only with its own ablations [§5.3]. But Tab. 1 shows that, relative to direct code generation, Code2Video is **15–20× more expensive in tokens** (30.8K vs 1.2K) and **5–7× more expensive in time** (15.4 vs 2.1 min). Not a line of text about this. Meanwhile "Efficiency (↓)" stands in the header of the main table as a dimension on which the direct LLM wins outright.

## 6. There are no Limitations, Ethics or Reproducibility sections

`A-main.tex` contains exactly: abstract, intro, related work, benchmark, approach, experiment, conclusion, appendix. There is no limitations or reproducibility section, mandatory for an ICLR submission. The limitations are scattered across one or two sentences in §5.2(iv) and §A.1.7.

---

# The weak points of MMMC and TeachQuiz

## MMMC as a benchmark

**A single source.** All 456 units come from one YouTube channel, one author, one visual style, one language. The name "**M**assive **M**ulti-discipline **M**ultimodal **C**oding" does not survive scrutiny: 117 videos is not "massive" (HF itself applies the tag `size_categories:n<1K`), and the "13 disciplines" are distributed extremely unevenly: Analysis 18, Linear Algebra 16, Calculus 15, Puzzles 12, Physics 10, Probability 10, Neural Networks 9, Geometry 7, Topology 7, Computer Science 5, Differential Equations 4, Epidemic 3, **Group Theory 1**. A category of one video is not a discipline. On top of that, every category lies inside "mathematics and its neighbours": there is no chemistry, biology, history, languages or economics.

**"Executable grounding" is nominal.** The selection criterion is formulated as "each concept aligns with a high-quality Manim reference" [§3.2, §A.1.6]. But **the 3B1B Manim sources were neither collected nor published**. The dataset holds only rendered mp4s. The public repository `3b1b/videos` with the real code of every video is not mentioned in the paper once. That is, a "code-centric benchmark" contains not a line of reference code — there is neither ground-truth code nor any way to measure code-level metrics. For a work declaring code to be the substrate of a paradigm, this is a heavy gap.

**A popularity leak.** 3B1B's topics are exactly the slice of mathematics most heavily represented in LLM training corpora (millions of views, thousands of retellings, summaries, Reddit threads). For a metric that tries to "erase" a VLM's knowledge, the worst possible domain has been chosen.

**Legal status.** 117 full 3B1B videos (about 17 minutes each) have been re-uploaded to HuggingFace in their entirety. `info.json` shows `license: null` — that is, the standard YouTube licence, not CC. Neither a dataset licence nor the author's permission appears on the HF card; there is only an "Acknowledgements". The paper has no Ethics section.

## TeachQuiz: why the "unlearning" is incorrect

**This is not unlearning but an instruction to refuse.** There is no intervention in the parameters at all — this is acknowledged [§A.1.1]. The prompt demands: "Evidence scope = ONLY the literal text of the question and options", "If the question implicitly/explicitly requires blocked knowledge, declare INSUFFICIENT EVIDENCE" [source/eva_unlearn.tex:L25-L30]. The model answers `NULL`.

The numerical proof: $S_1 = 5.0$ against **25% for random guessing** on 4 options [Tab. 5]. An accuracy *five times below chance* is impossible as the result of "removing knowledge" — it is possible only as the result of mass refusal to answer. That is, $S_1$ measures not residual knowledge but **the degree of obedience to the prompt**. Correspondingly $\mathrm{TQ} = S_2 - S_1 \approx S_2 - 0$ degenerates into "raw accuracy with the video", and no control for a leak of prior knowledge is exercised at all.

**The leak at the relearn stage is wide open.** At the second stage the block is formally preserved, but there is nothing with which to check that the model answered "from the video" rather than "from memory, with the video as an excuse": all that is required is to quote a scene. A model that remembers Euler's formula will happily write `VIDEO_EVIDENCE: the video shows e^(ix) traced on the unit circle` and answer correctly — regardless of whether that was in the video. The Random-video control (TQ 2.0–5.0) partly addresses this, but it hits too weak an alternative: a mismatched video activates the refusal mode. The main control is missing — **a video on the right topic with wrong content**: if the model still answers correctly, it is reading from memory and the video merely serves as a pass.

**The name of the concept is passed into the prompt.** `Forbidden concept: [{concept}]` — and the concept is, for example, `"Euler's Formula and e^(πi) = -1"`. The identity that is to be "forgotten" is literally printed in the forgetting prompt. Likewise `"Bayes theorem and independence in probability"`, `"Fractal dimension"`.

**The baseline without unlearning is not reported.** `src/eval_TQ.py` has three stages: `assess_baseline` (no unlearn, no video), `assess_with_unlearning`, `assess_with_unlearning_and_video`. The field `pre_unlearning_score` is computed and put into the report. **It is never given in the paper.** And it is the most important number: if Gemini answers 90% correctly with no video at all, then the whole TeachQuiz effect is an artefact of the prompt. Passing over precisely this quantity while it exists in the code is a serious complaint.

**The criterion of "successful unlearning" is a heuristic, and selective filtering is possible.** In the code: `unlearning_success = post_unlearn_score <= pre_score  # a simple heuristic`, and the aggregated statistics are printed over the subset `successful_results = [r for r in results if r.unlearning_success]` (`src/eval_TQ.py`). That is, a route to discarding inconvenient concepts is built into the tooling. The share of successful unlearns is not reported in the paper, and whether filtering was applied is unknown.

## TeachQuiz: the quiz set itself

The file `json_files/questions_by_topic_10.json` (117 topics):

- **5 questions per topic, not 10.** The appendix asserts: "For each learning topic, we construct 10 multiple-choice questions" [§A.1.1, L41]. In the published file there are exactly 5 for all 117 topics. That is 585 in total, not 1170. A discrepancy between paper and artefact.
- **A degenerate answer key**: B — 296 (50.6%), C — 230 (39.3%), A — 50 (8.5%), D — 9 (1.5%). The constant strategy "always B" gives 50.6%. Note: the direct-code-generation baseline gives $S_2 = 45.0$ for Claude (TQ 40.0 + $S_1$ 5.0) — **below constant guessing**. This means the Quiz column primarily measures how strongly a given input pulls the model out of refusal mode, not how well the video teaches.
- **Not "visually grounded".** The appendix promises questions on visually grounded reasoning [§A.1.1]. By a rough lexical count only **103 of 585 (17.6%)** questions contain any visual vocabulary at all. The rest are definitions and formulas answerable from memory.
- **The distractors are trivial.** An example from the Euler topic: "Which equation correctly expresses Euler's formula? A) e^(ix)=cos(x)+i·sin(x) B) e^(ix)=x+i C) e^(ix)=sin(x)+i·cos(x) D) e^(ix)=x²+i²". Options B and D are ruled out by type mismatch without any knowledge of the topic.
- **The answer parsing is fragile**: `re.search(r"\b[A-D]\b", resp)` takes the very first standalone letter A–D anywhere in the answer, including the text of the justification. The answer "INSUFFICIENT… I cannot distinguish between B and C" will be counted as "B".

## Statistics and sample size

- The size of the evaluation sample for Tab. 1 is **given nowhere**. Neither the paper nor the repository contains a fixed eval subset; `eva_video_list()` simply walks the whole list of topics. From the granularity of the numbers (36.5, 44.0, 48.5, 82.0 with 5 questions per topic) the sample looks like ~20 topics — that is, ~4% of the 456 units the benchmark claims.
- Not one confidence bound, not one p-value, not one seed, not one repeated run in the whole paper — even though both the generator and the judge are stochastic, and the auto-fix budget (up to 10 attempts) makes the variance knowingly large.
- The only statistic is "Aesthetics and Quiz are strongly correlated ($r=0.971$, $p=0.0059$)" [§5.3, L189]. That is a correlation over **five aggregated points** (the number of rows in Tab. 4), df=3. From it a causal conclusion is drawn: "visually appealing videos keep students engaged, leading to higher learning outcomes". Neither the sample size nor the causality survives scrutiny.
- The human study: 40 participants, a between-groups design, 8 per group. The breakdown by education level in [Tab. 8] is built on **2 university students** and 6 schoolchildren per group. Numbers like "88.1 against 55.0" are obtained on n=6 and n=2 respectively. No inter-rater agreement, no randomisation of order, no blinding — nothing is described.
- The load on a participant is implausible: 20 topics × 16.9 min = 5.6 hours of continuous viewing for the 3B1B group. With CW 36.2 most did not finish watching — that is, the "human" group was tested in a regime of unfinished videos. That is not a control of teaching quality, it is a control of duration.

---

# The honesty of the baselines and of the comparison with 3B1B

**Pixel diffusion is a straw man.** Veo3 and Wan2.2 generate clips of **up to 8 seconds** [§A.1.8], Code2Video 1.6–2.0 minutes [Tab. 4]. They are compared on "Logic Flow" and "Accuracy & Depth" on a 100-point scale and given zeros. An eight-second clip physically cannot expound a topic; the comparison is uninformative and serves only for contrast. It would have been fairer either to exclude them or to compare on a task for which 8 seconds suffice.

**Direct code generation is not compute-matched.** Code2Video gets up to 10 repair attempts, 2 rounds of critic, an external asset database and 15–20× the tokens. The "CodeLLM" baseline is obviously a single pass. All the obvious fair baselines are missing: (a) direct generation with the same retry-until-compilation budget; (b) best-of-N with the same token budget; (c) direct generation with the same `TeachingScene` base class and anchor grid but without the Planner/Critic. Neither the compilation rate nor the share of wholly failed generations is reported for any method. A substantial part of the 37.8 → 87.9 gap may simply be explained by the baseline often emitting code that does not run.

**The "GPT-5" backbone has been substituted.** `src/api_config.json` says `"model": "gpt-5-chat-2025-08-07"` — the **non-reasoning** chat variant. In the paper it is denoted simply "GPT-5" with a reference to the general OpenAI citation. This explains the anomaly of "GPT-5" losing to GPT-4.1 (72.2 vs 79.0) and makes the conclusion about "trade-offs between coding style and quality" an artefact of the checkpoint chosen. Likewise Gemini is given as `gemini-2.5-pro-preview-05-06` — a preview snapshot — while the paper says simply "Gemini-2.5 Pro".

**A conflict of interest in the judge.** Gemini-2.5 Pro is simultaneously: (a) the Critic inside the pipeline, which iteratively fixes the layout, (b) the VLM judge for AES, (c) the "student" in TeachQuiz. The pipeline is literally optimised for the preferences of the very model that then awards the scores. This is a form of train-on-test in LLM-judging terms. Not one second, independent judge was run.

**The judge's prompt is hard-wired to Code2Video's layout.** This is the most serious point. The Element Layout criteria, verbatim:
```
- Clarity and readability of text/diagrams in the presentation (left side)
- Optimal positioning and sizing of animated content (right side)
- Balance between presentation and animation areas
```
[source/eva_aes.tex:L17-L19]. Exactly the composition Code2Video imposes on its coders (`Grid layout (right side only)`, [source/d-coder.tex:L24-L32]). Neither 3B1B, nor Veo3, nor the direct CodeLLM uses a "text on the left / animation on the right" split. The metric by construction rewards a single method. Direct code generation is thereby penalised on EL (16.1 from the humans in Tab. 4, 47.5 from the judge in Tab. 1) not for quality but for failing to match the form.

**The comparison with 3B1B is not modality-equivalent.** The 3B1B videos are narrated lectures with a voice-over; Code2Video produces silent clips with text on screen. Nowhere does the paper say whether the Gemini judge received the audio track, or how "Attractiveness" and "Logic Flow" were scored for a narrated video against a silent one. The human study participants likewise compared a narrated 17-minute video with a silent 2-minute slideshow. This is a comparison of different products, not of different quality.

**The reverse signal in TheoremExplainBench is ignored.** In [Tab. 6] "Human made Manim videos" score an overall **0.77** — below Code2Video (0.88) and below even TEA (0.78). When an automatic protocol scores professional human videos below generated ones, the correct conclusion is "the protocol does not measure quality". The paper presents it as confirmation of the method's strength.

---

# Reproducibility: what really is in the repository

Checked against `github.com/showlab/Code2Video` (main, ~1.99k stars, MIT, last push 2026-08-18) and `huggingface.co/datasets/YanzheChen/MMMC`.

**Present on GitHub:**
- `src/agent.py` (~40 KB) — the full Planner/Coder/Critic pipeline;
- `src/scope_refine.py` (~33 KB) — the implementation of SR;
- `src/external_assets.py` — Google Images + a CLIP filter + Iconfinder;
- `src/gpt_request.py` — wrappers over six APIs;
- `prompts/stage1..stage5_*.py` — all the prompts, including the unlearning one; the texts match the paper's appendix verbatim;
- `prompts/base_class.py` — `TeachingScene` with the 6×6 grid mapping;
- `src/eval_AES.py`, `src/eval_TQ.py` — both automatic metrics;
- `json_files/`: the 117 topic names (three variants), the reference-image mapping, `questions_by_topic_10.json`.

**Present on HuggingFace (MMMC, 2084 objects):**
- `data/` — 117 full 3B1B mp4s + 43 reference frames `0.png`;
- `gallery/GT/` — 117 directories with the original yt-dlp dump: `*.info.json`, `*.description`, `*.webp`, the full mp4 and the cut `0.mp4 … N.mp4` (339 clips), `*_clips.json` (clip → chapter title), `video_topics.json` (LLM topics);
- `assets/icon/` — 613 PNG icons (of which only 9 are published on GitHub: `car, card, carrot, cat, cats, cell, cellphone, chameleon, character` — an alphabetical stump);
- `metadata.jsonl` — 117 lines: `id, category, video, main_topics, num_slices, reference_image`.

**Present nowhere:**
1. **Not a single reference Manim source.** A "code-centric" benchmark contains no code.
2. **An implementation of the "CodeLLM direct generation" baseline** — the point of comparison is irreproducible.
3. **A fixed eval subset**, or indeed any statement of how many topics Tab. 1–3 were obtained on.
4. **The generated videos / code / logs** for any method — only 4 demo GIFs in the README. No result can be re-scored by somebody else's judge.
5. **The human study data**: no questionnaires, no raw answers, no IRB/consent, no demographics beyond "6 schoolchildren + 2 students".
6. **The scraping and cutting script** (the yt-dlp command, the ffmpeg cut) — recoverable only from the artefacts.
7. **The prompt $\mathcal{P}_{\rm topic}$** for extracting topics — it is not in the appendix's list of prompts (which has aes, unlearn, learn, outline, storyboard, assets, vis, coder, refine), nor in `prompts/`.
8. **Machine-readable segment timestamps** separate from `.info.json`: `metadata.jsonl` gives only `num_slices`, with no `start_time`, no `end_time`, no segment topic. The segment level of the benchmark is de facto unindexed.
9. **The code for Tab. 6 (TheoremExplainBench)** and for the Tab. 5 ablations (Text-only / Animation / Random).
10. **The TQ score at the `assess_baseline` stage** — the code computes it, the paper is silent.

**Discrepancies found between the paper and the artefacts:**
| The paper's claim | The artefact |
|---|---|
| "10 multiple-choice questions" per topic [§A.1.1] | 5 questions for all 117 topics |
| "13 categories … Epidemics" [§A.1.6] | the directory `data/Epidemic` |
| "reference images … for each learning topic" [§5.1] | 43/117 in `metadata.jsonl`, 30/117 in `long_video_ref_mapping.json` |
| "GPT-5" [§5.1] | `gpt-5-chat-2025-08-07` (non-reasoning) |
| "Gemini-2.5 Pro" [§5.1] | `gemini-2.5-pro-preview-05-06` |

Miscellaneous: a `.DS_Store` in the root of the HF dataset and in `gallery/` — the dataset was assembled by hand on macOS. The files `Eulers_Formula_and_eπi_=_-1.jpg`, `Eulers_formula_and_e{pi_i}_=_-1.jpg`, `Eulers_formula_e{iπ}.jpg` are three copies identical in size (2512 B) under different name normalisations, which means the normalisation of topics is unstable and one topic can multiply.

The reproducibility verdict: **the pipeline is reproducible; the results are not.** The generation can be run (given six API keys and an Iconfinder key). Reproducing even one figure from the tables is impossible.

---

# How the data were collected (in detail)

A reconstruction from the artefacts of the HF dataset, since the paper describes the process in two paragraphs [§3.2, §A.1.6].

**1. The source is YouTube, not the code repository.** Explicitly: "From YouTube (footnote: youtube.com/@3blue1brown/videos), we scraped the complete collection of 3B1B videos" [§A.1.6, L205]. The repository `3b1b/videos` with the real Manim sources of the videos **was not used and is not mentioned**. There was no regeneration from code — the finished renders were taken.

**2. The tool is yt-dlp.** The evidence from `gallery/GT/**/*.info.json`:
- `"_version": {"version": "2025.07.21", "repository": "yt-dlp/yt-dlp", "release_git_head": "9951fdd..."}` — the exact version;
- `"extractor": "youtube"`, `"webpage_url": "https://www.youtube.com/watch?v=LqbZpur38nw"`;
- the playlist fields `playlist`, `playlist_id`, `playlist_index`, `playlist_count`, `n_entries` are present — so the channel playlist was dumped as a whole rather than individual videos;
- the file names contain `｜` (U+FF5C) and `？` (U+FF1F) instead of `|` and `?` — the standard name sanitisation in yt-dlp;
- next to every mp4 there is a `*.description` (117 of them), a `*.webp` (117 thumbnails) and an `*.info.json` — that is, the run used flags of the form `--write-info-json --write-description --write-thumbnail`.

**3. Audio and transcripts.** The audio track is present inside the mp4 (`acodec`, `asr`, `audio_channels` in info.json). But:
- **the subtitles were not downloaded**: `info.json` lists manual subtitles in ~10 languages (`ar, zh, en, fr, iw, hi, hu, id, it, ja`) with an empty `automatic_captions`, yet **not a single `.vtt`/`.srt` file is in the dataset** (the extensions in the tree are: `.mp4 .png .json .description .webp .jpg .md .jsonl`);
- no ASR was run, and there are no transcripts;
- consequently the extraction of topics went **from the title + description + metadata alone**, exactly as §A.1.6 says, and the content of the author's speech never entered the benchmark. This also means the 3B1B "reference" in the human study and for the judge is narrated, while the generated videos are silent.

**4. Filtering.** Non-educational material (Q&A sessions and the like) was removed from the full channel by hand, leaving **117 long videos** [§3.2, §A.1.6]. The filtering criterion was never formalised; the list of removed videos is not published.

**5. Categorisation.** "Following the topical structure adopted by 3B1B" — the 13 categories are taken from the lessons page of 3blue1brown.com itself [§A.1.6, L205]. In the paper: *Analysis, Calculus, Computer Science, Differential Equations, **Epidemics**, Geometry, Group Theory, Linear Algebra, Neural Networks, Physics, Probability, Puzzles, Topology*. In the dataset the directory is called `Epidemic`. The actual distribution (from `metadata.jsonl`):

| Category | Videos |
|---|---|
| Analysis | 18 |
| Linear Algebra | 16 |
| Calculus | 15 |
| Puzzles | 12 |
| Physics | 10 |
| Probability | 10 |
| Neural Networks | 9 |
| Geometry | 7 |
| Topology | 7 |
| Computer Science | 5 |
| Differential Equations | 4 |
| Epidemic | 3 |
| Group Theory | 1 |
| **Total** | **117** |

**6. Cutting into segments.** The author's **YouTube chapters** were used, sitting in `info.json` in the `chapters` field as a list of `{start_time, title, end_time}` in seconds. An example (`Beyond the Mandelbrot set`, id `LqbZpur38nw`, duration 1656 s):
```
[{"start_time": 0.0,    "title": "Intro",                     "end_time": 182.0},
 {"start_time": 182.0,  "title": "Rational functions",        "end_time": 255.0},
 {"start_time": 255.0,  "title": "The Mandelbrot set",        "end_time": 492.0},
 {"start_time": 492.0,  "title": "Fixed points and stability","end_time": 771.0},
 {"start_time": 771.0,  "title": "Cycles",                    "end_time": 985.0},
 {"start_time": 985.0,  "title": "Hidden Mandelbrot",         "end_time": 1277.0},
 {"start_time": 1277.0, "title": "Fatou sets and Julia sets", "end_time": 1584.0},
 {"start_time": 1584.0, "title": "Final thoughts",            "end_time": 1656}]
```
Each chapter was cut into a separate `N.mp4` (numbered from 0), and the correspondence was recorded in `<title>_clips.json`:
```json
{"...holomorphic dynamics_0.mp4": "Intro",
 "...holomorphic dynamics_1.mp4": "Rational functions", ...}
```
The cutting script (the ffmpeg call) is not published. There is no semantic segmentation — only the author's chapters; the phrase "semantically coherent sub-clips" rests entirely on 3B1B's own discipline in marking them up.

**7. The final volumes match to the unit.** Verified against the HF tree:
- **117** full mp4s (`data/`, duplicated in `gallery/GT/`);
- **339** numbered segment mp4s in `gallery/GT/`;
- **456** = 117 + 339 mp4s in `gallery/` in total — matching the claimed "456 units";
- the sum of `num_slices` over `metadata.jsonl` = **339**;
- the mean length of `main_topics` = **6.282** words (6.28 in the paper) — matching.

**A substantial detail hidden by the aggregate: 68 of the 117 videos have `num_slices = 0`.** That is, all 339 segments come from just **49 videos** (42%), the ones with chapters set on YouTube. The distribution of segments per video: 3→1, 4→5, 5→12, 6→4, 7→10, 8→6, 9→5, 10→1, 11→2, 12→2, 13→1. The segment part of the benchmark is heavily skewed towards the later, longer, well-annotated videos; the paper does not say so.

**8. Topic extraction.** An LLM (the prompt $\mathcal{P}_{\rm topic}$, published nowhere) produces `video_topics.json` from the title + description + metadata:
```json
{"main_topics": "Holomorphic dynamics and iterated complex functions",
 "segments": [{"file": "0.mp4", "topic": "Introduction to holomorphic dynamics"}, ...]}
```
A mismatch shows up right here: `chapters` and `_clips.json` give 8 segments (0–7), while `video_topics.json` gives only 7 (0–6); the last chapter, "Final thoughts", got no topic. No human verification or validation of the topics is described.

**9. Reference images.** The `reference_image` in `metadata.jsonl` points at a `0.png` inside the video's directory and is filled in for **43 of 117** (36.8%). This is a separate layer from the runtime External Database, which pulls images from Google Images with a CLIP filter on the fly [§5.1, §A.1.7]; the reproducibility of the latter is zero — Google Images results are non-deterministic and change over time.

**10. What the collection lacks entirely:** no audio transcripts, no subtitles, no Manim sources, no binding of segments to code, no machine-readable timecodes outside `info.json`, no licence, no list of the filtered-out videos.

---

# Related Work positioning

The nearest predecessor is **TheoremExplainAgent / TheoremExplainBench** (`ku2025theoremexplainagent`): an agent generating Manim animations to explain theorems. Code2Video differs by having lecture lines (a two-panel layout), an explicit anchor grid and a per-block auto-fix; the comparison is relegated to the appendix [§A.1.4], although it is in substance the only direct competitor and belongs in the main body. **Manimator** (`jain2025manimator`) is closer still in framing and is mentioned by a single citation in the list [§2.2] with no comparison. From the "program as visual output" line: **Plot2Code** (`wu2024plot2code`), **ChartCoder** (`zhao2025chartcoder`), **Paper2Poster** (`pang2025paper2poster`) — all limited to static output, and Code2Video honestly positions itself as an extension into the dynamic. From the pixel line, **CogVideoX** (`yang2024cogvideox`), Veo3 and Wan2.2 serve as contrasting background but, as discussed above, are not meaningful baselines given a difference of 8 s against 2 min. Multi-agent video pipelines (**Mora** `yuan2024mora`, **DreamFactory** `xie2024dreamfactory`, **StoryAgent** `hu2024storyagent`) are cited as context but not compared. The positioning as "the first code-centric educational video generation benchmark" [§1] is contestable: TheoremExplainBench came out earlier and solves an overlapping task — MMMC's novelty comes down to using 3B1B as a pseudo-upper-bound and to the TeachQuiz metric.

---

# The overall assessment

**What is genuinely worth taking away.** (1) The device of a discrete 6×6 anchor grid plus an occupancy table — a simple, measurably effective way around LLMs' weak spatial literacy; the granularity ablation [Tab. 7] looks honest. (2) ScopeRefine and per-section parallelisation — a reproducible engineering gain of 9.7× in time [Tab. 3], measured without an LLM judge. (3) Open, working pipeline code. (4) A carefully assembled (if legally dubious) 3B1B corpus with chapters.

**What must not be bought.** Not a single figure from the AES and Quiz columns. AES is measured by a judge that (a) is part of the pipeline and (b) receives a prompt hard-wired to Code2Video's layout. Quiz is built on an "unlearning" that reduces to an instruction to keep quiet and yields a baseline five times below chance, on a quiz set with a 50.6% skew in the key, of 5 questions instead of the claimed 10, over an unstated number of topics, without a single confidence interval. The claim of "outperforming human videos" rests on a difference of 1.5 points at n=8 and on comparing two different quantities.

**What would fix the work.** Report $S_1$ and the pre-unlearn baseline; balance the answer key and publish all 10 questions per topic; introduce a "video on the right topic with false content" control; take an independent judge that is not part of the pipeline; rewrite the judge's prompt in a layout-agnostic form; add a compute-matched baseline (the same backbone, the same base class and retry budget, but without the Planner/Critic); state the sample size, the number of runs and the CIs; publish the generated videos and the logs; collect the reference Manim sources from `3b1b/videos` so that the benchmark becomes genuinely code-centric; add Limitations and Ethics sections and sort out the rights to re-upload the 117 videos.

---

# Anchors

- `data_curation_main: source/3-benchmark.tex:L17 — §3.2: 3B1B, 117 videos, 339 segments, 456 units, 13 categories`
- `data_curation_commented: source/3-benchmark.tex:L24-L27 — the commented-out version of §3.2, which says outright "We scrape the full YouTube corpus" and lists all 13 categories`
- `aes_metric_def: source/3-benchmark.tex:L44-L51 — VLM-as-Judges, five axes on a 100-point scale`
- `teachquiz_def: source/3-benchmark.tex:L63-L76 — the definition of TeachQuiz, Eq. (1) and Eq. (2) $\widetilde S = S(\mathcal V) - S(\mathcal V|\text{unlearn})$`
- `planner: source/4-approach.tex:L32-L40 — outline, storyboard, External Database`
- `scope_refine: source/4-approach.tex:L59-L64 — ScopeRefine: line/block/global scope`
- `visual_anchor: source/4-approach.tex:L94-L95 — the 6×6 grid, point-level and region-level`
- `critic_occupancy: source/4-approach.tex:L100-L104 — the occupancy table and the three classes of defect`
- `baselines: source/5-experiment.tex:L5-L13 — the line-up of baselines, Gemini-2.5 Pro as Critic and as judge`
- `main_results_table: source/5-experiment.tex:L19-L54 — Tab. 1, the main table (Efficiency / AES / Quiz)`
- `ablation_components: source/5-experiment.tex:L104-L127 — Tab. 2, the contribution of Planner / ExtDB / Anchor / Critic`
- `ablation_efficiency: source/5-experiment.tex:L128-L147 — Tab. 3, parallelism and ScopeRefine`
- `human_study_table: source/5-experiment.tex:L162-L183 — Tab. 4, the human study (Quiz 80.3 vs 78.8)`
- `human_study_setup: source/5-experiment.tex:L187 — 5 groups × (6 schoolchildren + 2 students), 20 topics × 5 questions`
- `correlation_claim: source/5-experiment.tex:L189 — r=0.971, p=0.0059 over five aggregated points`
- `unlearn_protocol: source/7-appendix.tex:L21-L30 — §A.1.1, contextual masking / uncertainty injection / progressive validation`
- `quiz_setup_10q: source/7-appendix.tex:L41 — the claim of "10 multiple-choice questions" per topic`
- `teachquiz_metric: source/7-appendix.tex:L44-L50 — $\mathrm{TQ} = S_2 - S_1$`
- `unlearn_ablation_table: source/7-appendix.tex:L56-L73 — Tab. 5: Unlearn 5.0, Relearn 85–91, Text-only / Animation / Random`
- `human_study_by_level: source/7-appendix.tex:L88-L107 — Tab. 8, the breakdown into n=6 schoolchildren and n=2 students`
- `anchor_granularity: source/7-appendix.tex:L114-L151 — Tab. 7, 4×4 / 6×6 / 8×8 / Self-directed`
- `theoremexplainbench: source/7-appendix.tex:L172-L194 — Tab. 6, human-made Manim 0.77 below Code2Video 0.88`
- `data_collection_appendix: source/7-appendix.tex:L200-L207 — §A.1.6, the yt-dlp scrape, the filtering, the chapters, $\mathcal{P}_{\rm topic}$`
- `dataset_stats: source/7-appendix.tex:L209-L211 — 456 = 117 + 339, 1014.41 s and 201.13 s, 6.28 words`
- `external_db_limits: source/7-appendix.tex:L220-L226 — the admission that abstract topics have no references`
- `judge_prompt_layout_bias: source/eva_aes.tex:L17-L19 — "presentation (left side)" / "animated content (right side)" in the Element Layout criteria`
- `judge_prompt_decimal: source/eva_aes.tex:L62 — "exact decimal allowed" (context for the flat 100.0 of 3B1B)`
- `unlearn_prompt: source/eva_unlearn.tex:L25-L35 — the rules of evidence-gated answering and the NULL output`
- `learn_prompt: source/eva_learn.tex:L19-L29 — video-only evidence, the requirement to quote a scene`
- `coder_grid_right_only: source/d-coder.tex:L20-L37 — "Grid layout (right side only)", the ban on .move_to()/.to_edge()`
- `no_limitations_section: source/A-main.tex:L161-L184 — the composition of the document: no Limitations / Ethics / Reproducibility`
- `architecture_diagram: figures/approach.png — Fig. 2, the full pipeline (the original is source/approach.pdf)`
- `anchor_diagram: figures/anchor.png — Fig. 4, the visual anchor prompt (the original is source/anchor.pdf)`
- `quiz_diagram: figures/quiz.png — Fig. 3, the Learning-from-Video vs Unlearning gap (the original is source/quiz.pdf)`
- `dataset_diagram: figures/dataset.png — Fig. 1, the donut chart of the 13 categories (the original is source/dataset.pdf)`

External artefacts (not in `<DIR>`):
- `repo_quiz_set: github.com/showlab/Code2Video json_files/questions_by_topic_10.json — 117 topics × 5 questions; the key B=296/C=230/A=50/D=9`
- `repo_eval_tq: github.com/showlab/Code2Video src/eval_TQ.py — assess_baseline (not reported in the paper), unlearning_success = post <= pre, the filtering of successful_results, the parser \b[A-D]\b`
- `repo_api_config: github.com/showlab/Code2Video src/api_config.json — gpt-5-chat-2025-08-07, gemini-2.5-pro-preview-05-06`
- `repo_run_agent: github.com/showlab/Code2Video src/run_agent.sh — max_fix_bug_tries=10, feedback_rounds=2, parallel_group_num=3`
- `hf_metadata: huggingface.co/datasets/YanzheChen/MMMC metadata.jsonl — 117 lines, sum(num_slices)=339, reference_image for 43`
- `hf_ytdlp_evidence: huggingface.co/datasets/YanzheChen/MMMC gallery/GT/**/*.info.json — yt-dlp 2025.07.21, extractor=youtube, the chapters field, license=null`
- `hf_clips_map: huggingface.co/datasets/YanzheChen/MMMC gallery/GT/**/*_clips.json — the "clip → YouTube chapter title" correspondence`
- `hf_topics: huggingface.co/datasets/YanzheChen/MMMC gallery/GT/**/video_topics.json — main_topics + a per-segment topic (7 topics for 8 clips in the example)`

---

# Glossary

- `Manim` — a Python library for mathematical animation (Community Edition v0.19.0 is used); the substrate of generation in Code2Video.
- `MMMC` — the "Massive Multi-discipline Multimodal Coding" benchmark: 117 full 3B1B videos + 339 segments cut by YouTube chapters = 456 units, 13 categories.
- `TeachQuiz (TQ)` — the metric $S_2 - S_1$: a VLM's accuracy on the MCQs after watching the video minus its accuracy under the "forgetting" prompt.
- `Unlearning ($\mathcal{P}_{\rm unlearn}$)` — here: a prompt forbidding the use of knowledge about the concept and requiring the output `INSUFFICIENT EVIDENCE / NULL`. The model's parameters are not changed.
- `Visual Anchor Prompt ($\mathcal{P}_{\rm vis}$)` — the discretisation of the right half of the canvas into a 6×6 grid (A1–F6) with a fixed mapping into Manim coordinates; point-level and region-level placement.
- `ScopeRefine (SR)` — a hierarchical auto-fix of the code: line ±1 → the block of a lecture line → a full regeneration of the section.
- `Occupancy table` — a table of "element → occupied anchors → scale → lines of code", from which the Critic finds overlaps and free cells.
- `Lecture lines` — the text lines of the lecture, hard-fixed in the left panel of the frame; only their colour may be changed.
- `CW (Completion Willingness)` — the share of human study participants who watched the video through before answering the questions (0–100).
- `AR (Average Ranking)` — the mean preference rank among the video types, 1 being the best.
