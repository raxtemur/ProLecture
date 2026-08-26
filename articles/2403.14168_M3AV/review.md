---
title: "M³AV: A Multimodal, Multigenre, and Multipurpose Audio-Visual Academic Lecture Dataset"
authors: [Zhe Chen, Heyang Liu, Wenyi Yu, Guangzhi Sun, Hongcheng Liu, Ji Wu, Chao Zhang, Yu Wang, Yanfeng Wang]
venue: ACL 2024 (Main Conference, Long Papers, pp. 9041–9060), DOI 10.18653/v1/2024.acl-long.489
arxiv: 2403.14168
slug: 2403.14168_M3AV
code: https://github.com/Jack-ZC8/M3AV-dataset
data: https://huggingface.co/datasets/CHHHH/M3AV_v1.0 (45.5 GB, CC BY-NC-SA 4.0)
sources: source/
date_reviewed: 2026-08-19
review_type: adversarial
---

# TL;DR

- A dataset of 1113 YouTube lectures (366.9 h, 5 sources), with OCR annotation of the slides and transcriptions of the speech; 3 benchmarks: CASR, spontaneous TTS, Slide↔Script generation [§3, §5].
- The claimed "high-quality human annotations" of speech are untrue for 80.5% of the corpus: the train split (295.4 h) is the raw output of Microsoft STT without a single human edit [§4.2.4, Tab. 3].
- The ASR evaluation is carried out against labels produced by the very Whisper/Microsoft systems being evaluated; the figure "WER 10%" measures agreement with Microsoft STT, not accuracy [§5.1.3, Tab. 5].
- The main "feature" — handwritten text and formulas — amounts to 772 pages (3.1% of the slides), and not a single benchmark is run on the OCR annotation at all [§3.3, Tab. 4].
- Human evaluations: MOS on 20 samples, SSG on 100 samples × 3 annotators from the authors' own team, with no IAA, no CIs, no significance tests [§5.2.3, §5.3.3, App. A.4].
- The code and the data really are available (45.5 GB, CC BY-NC-SA), but GPT-4 is called through the unpinned alias `gpt-4` and the retired `gpt-4-vision-preview` → the numbers in Tab. 7 are irreproducible.

---

# Problem & Motivation

The gap the authors claim: existing academic-lecture datasets fall into two disjoint classes. Some (LectureVideoDB, SlideSpeech) are aimed at the *recognition* of multimodal content, others (LectureBank, TalkSumm, AVIATE, LPM) at the *understanding* of academic knowledge, and none supports both regimes at once. The reason, in the authors' view, is a shortage of quality manual annotation [§1, §2]. From this they derive the need for a corpus that has, simultaneously: (a) manually verified OCR of the slides, including handwritten text and formulas in LaTeX, (b) verified speech transcriptions with word-level timings and in two forms (spoken/written), (c) the texts of the corresponding papers as an external source of knowledge.

The motivation is plausible, but the very statement of the "gap" is built on a comparison table (Tab. 1 in §2) where the authors themselves assign the labels "A" (automatic processing) and "M" (fully or partially manual). The wording "fully **or partially** manual" makes the column almost contentless: M³AV gets an "M" in the Transcription column on the grounds that part of the dev/test segments went through MTurk, while 80.5% of the corpus by duration is the unprocessed output of a commercial ASR. By the same logic several competitors could have got an "M" too. The claim "none of them has yet simultaneously paid attention to recognition and understanding" [§1] is checked only against that table and is not supported by a single experiment in which an existing dataset fails the M³AV task.

A second layer of motivation is applied: helping researchers prepare presentations, generating scripts from slides and slides from scripts. Here the motivation is stronger, because the SSG task really is new relative to LPM (which is cross-modal retrieval, not generation).

The work has no bearing on generating educational videos in the Manim/3Blue1Brown style: no animations are assembled and the video track is not distributed at all (see "How the data were collected") — only slide frames and audio are kept. The closest point of contact is the Oxford Mathematics (MLS) split, which has handwritten derivations and formulas in LaTeX, but that is 51 videos, 26.2 h and 577 slides, i.e. 2.3% of the corpus by slides.

![An overview of the dataset: slides with block annotation, speech in spoken/written form with word-level timings, the text of the paper](figures/figures_1-1.png)

---

# Method (the dataset construction pipeline)

There is no method in the usual sense here — there is an annotation pipeline, and that is the main technical contribution. I go through it in detail, because every complaint about the work grows out of it.

## How the data were collected

**The sources.** Five YouTube playlists, all publicly available [§4.1]:

| Source | Field | Hours | Videos | Slides | Papers |
|---|---|---:|---:|---:|---:|
| CHI 2021 Paper Presentations | HCI / CS | 53.2 | 660 | 9195 | 660 |
| UbiComp 2020 Presentations | HCI / CS | 10.4 | 107 | 1451 | 107 |
| NIH Director's Wednesday Afternoon Lectures | biomed | 235.4 | 228 | 11208 | — |
| Introduction to the Principles and Practice of Clinical Research (IPPCR) | biomed | 41.7 | 67 | 2525 | — |
| Oxford Mathematics | mathematics | 26.2 | 51 | 577 | — |
| **Total** | | **366.9** | **1113** | **24956** | **767** |

The hours and slide figures come from Fig. 5(a,b); the totals from §3.2 and §3.3. The repository README gives the original playlist durations (55.00 / 10.65 / 237.71 / 42.27 / 27.23 = 372.86 h), i.e. ~6 h were discarded during filtering; the paper does not explain this discrepancy.

**A key fact about the balance:** NIH is 64.2% of the corpus's total duration while being 20.5% of the videos. The test split: NIH 23.5 h out of 36.4 h = 64.6%. That is, all the aggregate metrics in Tab. 5 are in essence metrics on NIH biomedical lectures. The word "Multigenre" in the title is not supported by the data: no table breaks the results down by source.

**Downloading.** The videos, descriptions and subtitles are downloaded from YouTube. For the CS videos (CHI + UbiComp = exactly 767 = the number of papers in Tab. 2) the PDFs of the papers are downloaded and parsed with `science-parse` (AllenAI) [§4.1]. The file `download/paper_link.json` in the repository contains exactly 767 non-empty links, all to `dl.acm.org/doi/pdf/...`. What is distributed in the release is not the PDF but `paper/paper_sentences.json` — a list of the paper's sentences.

**Speech transcription (4 steps)** [§4.2]:

1. *Generating candidates.* The authors' YouTube subtitles are declared low-quality "by our observation" (with no measurement). In their place, two commercial/open ASR systems: **Microsoft STT** (giving the written form $M_w$ and the spoken form $M_s$) and **Whisper-large-v2** (written only, $W_w$). The justification for the choice: "both give WER < 10% or even < 5% on several tests of the SpeechColab Leaderboard in October 2022" [§4.2.1].
2. *Audio segmentation.* Re-segmentation by the word-level timings of $M_w$. The rules [App. A.1]: a cut is allowed at a pause > 0.2 s or at a `.`/`!`/`?`; a segment is closed once ≥ 8 s have accumulated or if adding the next piece would give ≥ 10 s; a pause > 5 s is discarded and cuts the segment.
3. *Splitting into sets.* Roughly 8:1:1 by duration. It is claimed that one and the same speaker does not land in different splits, and that the speaker is identified "from the introductory information and the description text" [§4.2.3]. In fact (`download/set_split.json`): train 901 / dev 99 / test 113 videos; in the test set CHI 58, NIH 22, Ubi 16, IPP 13, MLS 4.
4. *Combining the candidates.* **Train: $M_w$ and $M_s$ are taken directly from Microsoft, with no human involvement.** Dev/test: if $M_w \approx W_w$ ("approximately equal", forgiving mismatches at pauses and on frequent words) — Case I, the labels are taken as they are from Microsoft; otherwise Case II: the mismatched words are masked as `[???]` in $M_s$, MTurk annotators fill in the masks ($M_s^{a}$), then other annotators merge $M_s$ and $M_s^{a}$ into the final $M_s^{c}$ [§4.2.4].

![The transcription creation pipeline: 4 steps from ASR candidates to the final labels](figures/figures_2-1.png)

Post-processing of $M_s^c$ [App. A.3]: inverse text normalisation (NeMo WFST), punctuation and capitalisation (NeMo), word-level timings via the Montreal Forced Aligner.

**Slide annotation (4 steps)** [§4.3]:

1. *Pre-annotation.* Frame sampling at 1 fps + **PaddleOCR** for text detection and recognition.
2. *Deduplication.* Automatically: frames with cover blocks $B_{\text{cover}}$ and fixed logos $B_{\text{excluded}}$ are removed; blocks with few letters ($\min^{\text{B}}_{\text{alpha}}$) and frames with too few or too many blocks ($\min^{\text{I}}_{\text{B}}$, $\max^{\text{I}}_{\text{B}}$) are filtered out; then the frames are grouped into segments by a modified error [App. A.2]:
   $$\text{WER}^{\text{mod}} = \frac{S + D + 0 \times I}{H + S + D}, \qquad \text{CER}^{\text{mod}} = \frac{S + D + 0.1 \times I}{H + S + D}$$
   Insertions are almost unpenalised — done deliberately so that a slide built up incrementally counts as "the same" slide. The thresholds are tuned by hand per source. After that, manual deduplication keeping the last frame of each segment.
3. *Manual correction.* Plain text is corrected by "experienced researchers" from the team (coordinates + content), and blocks with URLs and e-mails are discarded. Complex frames (handwriting, formulas) are pre-annotated with the **Mathpix OCR API**, then corrected by hand; formulas are inline LaTeX. The interface is PPOCRLabel.
4. *The rules for merging lines into paragraphs.* Three geometric criteria with the parameters $a=b=0.8$, $c=0.6$:
   $$\max(h_0^a, h_0^b) - \min(h_0^a, h_0^b) \leq a \cdot \max(h_0^a, h_0^b)$$
   $$\min(a_2^x, b_1^x) - \max(a_3^x, b_0^x) \geq b \cdot \min(b_1^x - b_0^x,\ a_2^x - a_3^x)$$
   $$b_0^y - a_3^y \leq c \cdot \min(h_0^a, h_0^b)$$

![The slide annotation pipeline: pre-annotation, deduplication, manual correction, block merging](figures/figures_4-1.png)

**The volume and the format of the release.** HuggingFace `CHHHH/M3AV_v1.0`, 45.5 GB: `dataset_v1.0_noaudio.tar.gz` (2.02 GB — slide JPGs in `ocr/seg_imgs/`, `ocr/ocr_result.json` with the polygons and the text of the blocks, `ocr/seg_speech_ocr.json` with the slide↔speech stitching, `speech/final+timestamps.json`, `paper/paper_sentences.json`) + 9 parts of `dataset_v1.0_onlyaudio` (43.5 GB). **The video track is not distributed** — only `raw/*.mp4.ytbUrl` with a link to YouTube. The licence is CC BY-NC-SA 4.0 with the explicit caveat "M³AV doesn't own the copyright of the videos".

**Annotator pay** [App. A.4]: MTurk masters get **0.06 USD per sample** for filling in the masks and the same for merging; **0.2 USD per batch** of 6 TTS samples + a trap sample for MOS. No hourly rate is given. The OCR annotation was done by "experienced researchers of the team" who received "appropriate remuneration" — with no figures.

**Quality control** [§4.3.3, App. A.4]: "we sampled the results of 9 annotators individually and checked whether 120 annotated images had a large number of omissions or errors, no more than 10 erroneous elements". The wording is ambiguous (120 images in total or per annotator?), but either way that is ≤ 0.5% of the 24956 slides. No IAA, no measured error rate, no share of rejected work is given.

## The benchmarks

- **ASR/CASR.** Their own systems: AED (a Conformer-12 encoder, $d^{\text{ff}}=2048$, $d^{\text{att}}=512$, $H=8$, a 6-block Transformer decoder, BPE 1k, CTC weight 0.3/0.2, SpecAugment, 4×RTX 3090, 60 epochs, averaging the top-10 checkpoints) and RNN-T (Conformer-15, joint 320). Plus pre-trained Whisper-v3, Wav2Vec2+CTC, NeMo Conformer-Transducer/CTC, SeamlessM4T-v2. CASR is TCPGen with GNN encoding of a prefix tree; rare words = everything outside the top-5k by frequency in train (≈38k words out of a ≈43k vocabulary); a biasing list of length 500 in training and 1000 at inference [App. B.1, B.2].
- **Spontaneous TTS.** MQTTS (two-stage: a HiFi-GAN quantiser for 600k steps + an autoregressive Transformer over the codes, conditioned on a speaker embedding), trained on M³AV's train split. Compared against Bark and SpeechT5 [App. B.3].
- **SSG.** Slide→Script: a cascade (gold OCR text → LLaMA-2-7B/13B with LoRA, or GPT-4) and integrated models (fine-tuned InstructBLIP-7B/13B, GPT-4V). Script→Slide: LLaMA-2, GPT-4. RAG: the top-3 sentences of the paper with a cosine similarity > 0.5 under `msmarco-distilbert-base-v4`. Generation: nucleus sampling top_p 0.9, max 300 tokens [App. B.4].

---

# Experiments & Results

**ASR/CASR (Tab. 5).** Their own systems: AED 10.0% WER (dev and test), RNN-T 10.3/10.6%. BWER (the share of errors on rare words) is 35.5–38.0%, i.e. three times worse than the overall WER. Pre-trained: Whisper-v3 7.1/7.2% WER (marked in italics "for reference only"), NeMo Conformer+Transducer 10.7/10.5%, Conformer+CTC 11.1/11.1%, SeamlessM4T-v2 17.1/18.6%, Wav2Vec2+CTC 28.3/28.5%. CASR with TCPGen: a list of 1000 random distractors → BWER 26.7/27.1; a list of "OCR + rare words of the same topic" → 30.5/31.7 (worse); OCR words only → 22.9/25.0. The final claim: a relative BWER drop of 37.8% (dev) and 34.2% (test) relative to RNN-T without biasing. The arithmetic checks out (36.8→22.9; 38.0→25.0).

**TTS (Tab. 6).** MQTTS: FFE 0.3518, MCD 9.40, MOS 3.67 ± 0.94. SpeechT5: 0.4153 / 9.43 / 3.43 ± 1.09. Bark: 0.4269 / 10.57 / 3.31 ± 1.02. Ground truth: MOS 3.86 ± 1.02. The MOS was computed on **20 random samples**.

**SSG (Tab. 7).** Slide→Script: LLaMA-2-13B+OCR gives the best ROUGE-1 (26.9), ROUGE-2 (6.4) and BERTScore (0.102); GPT-4+OCR gives 26.2 / 5.8 / 0.085 but the best BARTScore (−4.621); GPT-4V gives 26.4 / 6.2 / 0.092 / −4.630. InstructBLIP fails (ROUGE-2 2.2–2.3). Human: InstructBLIP 2.4–2.5, LLaMA-2 3.6–3.9, GPT-4 4.6, GPT-4V 4.7. Script→Slide: GPT-4 leads on ROUGE (26.8/7.7/23.0) and human (4.8), LLaMA-2-13B on BERTScore (0.092).

**The RAG ablation (Tab. 8).** LLaMA-2-7B only, the CS subset only. Slide→Script: 24.9→29.2 ROUGE-1, human 3.7→4.1. Script→Slide: 20.9→22.3, human 3.3→3.6, BERTScore unchanged (0.061→0.061).

**Detailed human scores (Tab. 9–10, App. B.5).** GPT-4 and GPT-4V get exactly **5.0** for fluency and relevance in both tasks — the ceiling of the scale.

---

# The critical discussion

## 1. Claims not backed by experiments

**"High-quality human annotations ... of spoken words".** This is the central claim of the annotation and of the abstract, and it is untrue for 295.4 h out of 366.9 h (80.5%): in the train split the labels are the direct output of Microsoft STT [§4.2.4]. For dev/test a human touches **only** the Case II segments, where Microsoft and Whisper disagreed; the Case I segments (where the two ASR systems agree) go into "gold" without a single human glance. The Case I / Case II ratio is given nowhere — and it is the one number that would let one gauge the real volume of manual work. The justification for train is that it "shows high quality, verified by comparison with manual annotation on a subset" [§4.2.4]: no size of the subset, no measured WER, no criterion for "high quality". Meanwhile in the dataset comparison table (Tab. 1) M³AV gets an "M" in the Transcription column — that is a stretch.

**An additional signal: the paper's description diverges from the release.** The repository README (a news item from 2024-04) states: "the training set adopts the text-normalised **Whisper** results, and the development/testing set employs a manual combination of Whisper and microsoft STT results". The ACL camera-ready (p. 706 of the PDF's text layer) and arXiv v3 say the opposite: "For the training set, we directly adopt the **Microsoft** transcription $M_w$ and $M_s$". One of the two descriptions is false. If the README is right, the situation is worse than in the paper: AED/RNN-T were trained to imitate Whisper, and Whisper-v3 is then evaluated on the same corpus — and the caveat "Whisper for reference only" becomes insufficient, because the "honest" baselines are contaminated too.

**"Avoiding the issue of training data contamination"** [§5.1.2] is a non sequitur. The argument: "our videos are correctly transcribed for the first time, so the other open-source ASR systems can be evaluated fairly". But ASR contamination goes through the **audio**, not through the transcripts: Whisper was trained on 680k h of web audio, and NeMo and SeamlessM4T on mixtures that include public YouTube corpora. NIH WALS and Oxford Mathematics are large, old, public playlists, and the probability of their presence in pre-training mixtures is high. No check (for example a memorisation probe or a comparison with a private held-out set) is carried out.

**"The diversity of M³AV makes it a challenging dataset"** (the abstract, §6). No table breaks the results down by source. A claim of difficulty grounded in diversity is checkable only through per-source metrics, and there are none. Moreover, 10% WER on prepared lecture speech is not "challenging" by 2024 standards; on genuinely hard corpora (spontaneous meetings, say) the numbers are several times higher.

**"M³AV ... is completely qualified to cover tasks in the aforementioned datasets"** [§2] — that is, it replaces LectureVideoDB (recognition of handwritten/scene text) and SlideSpeech. There is not a single experiment on recognising the text of the slides in the work. The manually verified OCR — the declared main contribution — is used **only as a gold input** for CASR and SSG, and never as a gold output for an OCR task. In Tab. 1 M³AV ticks the "Recognition" box, while the only recognition task actually implemented is ASR.

**"Real speech in our dataset can drive AI systems to simulate more natural speech"** [§5.2.3]. The conclusion is drawn from MQTTS, trained on M³AV, beating Bark and SpeechT5 on MOS. There is no control: MQTTS is not trained on another corpus (for example the GigaSpeech subset its own authors trained it on) and evaluated on M³AV. Without that comparison no conclusion about the contribution of the *data* is possible.

**"GPT-4V has already exceeded the cascaded pipeline"** [§5.3.3]. The difference GPT-4V vs GPT-4+OCR: ROUGE-1 26.4 vs 26.2, ROUGE-L 23.7 vs 23.7, human 4.7 vs 4.6. This is noise presented as a "significant observation". No confidence intervals, no repeated runs.

**"Open-source models ... are far from the closed-source models"** [§5.3.3] directly contradicts their own Tab. 7: the fine-tuned LLaMA-2-13B beats GPT-4 on ROUGE-1 (26.9 vs 26.2), ROUGE-2 (6.4 vs 5.8) and BERTScore (0.102 vs 0.085) in Slide→Script. The "far from" conclusion rests exclusively on the human evaluation, where GPT-4 hits the ceiling of the scale.

## 2. Weak points of the benchmarks and metrics

**The circularity of the ASR evaluation.** The dev/test reference labels were produced by Microsoft STT and Whisper. In Case I the "gold" is literally Microsoft's output. Consequently: (a) any system resembling Microsoft STT in normalisation, punctuation and number handling gets a bonus; (b) the absolute WERs do not measure recognition accuracy — they measure the distance to the consensus of two ASR systems; (c) even the italicised caveat about Whisper is insufficient, because Whisper took part in deciding *which* segments would reach a human at all. A figure basic to any dataset paper is missing: the WER of the final labels relative to an independent human transcription of at least 1–2 h.

**Incomparable biasing lists in CASR.** The three CASR rows are compared with one another, but the conditions differ in the parameter that affects BWER most — the size of the list. "Random distractors" is a fixed 1000 words. "OCR" is the words from a specific slide, i.e. a list orders of magnitude shorter and almost certainly containing the target words. A short, relevant list is trivially easier. There is no control of "the OCR list padded with distractors up to 1000", and the sizes of the OCR lists are not given. The claimed "relative BWER drop of 37.8%" therefore does not separate the contribution of the visual modality from the contribution of shrinking the search space. On top of that, the OCR hints are the **manually verified** OCR rather than the output of a real OCR model: no such input exists in production, and the evaluation is optimistic by construction.

**Sample size and statistics.**
- MOS: 20 samples [§5.2.3]. The number of raters per sample is not given. The `±` is apparently a standard deviation, not a 95% CI. With a spread of ~1.0 and n=20 the confidence interval is ≈ ±0.45; the gaps MQTTS (3.67) vs SpeechT5 (3.43) and MQTTS vs GT (3.86) are inside the noise. No t-tests, no ANOVA, no bootstrap.
- SSG human: 100 samples, 3 annotators [§5.3.3, App. A.4]. No IAA (Krippendorff's α, Fleiss' κ) is given. The annotators are "three experienced researchers" from the authors' team; nothing is said about blinding (blind evaluation, randomising the order of the systems). This is self-evaluation with a direct conflict of interest: the authors score their own baselines and know which one is supposed to win. Tellingly, MTurk annotation for SSG was first launched and then discarded as "unsatisfactory" — that is, the decision to switch to in-house raters was taken *after* looking at the results.
- The ceiling of the scale: GPT-4/GPT-4V get exactly 5.0/5.0 on fluency and relevance (Tab. 9). The metric does not distinguish models in the upper segment and most likely reflects the merely stylistic "smoothness" of a long LLM text.
- Nowhere are there multiple seeds. Every table is a single run.

**The SSG metrics fit the task badly.** The reference for Slide→Script is the speaker's real spoken words. The task is fundamentally one-to-many: dozens of correct scripts are possible for one slide. ROUGE-1 ~25 and ROUGE-2 ~6 is the level at which the ranking of systems is unstable. A BERTScore around 0.07–0.16 (apparently rescaled) is practically uninformative. Three automatic metrics and the human evaluation give three different orderings of the systems — and the authors pick the one that supports the narrative "closed-source ≫ open-source".

**The RAG ablation without a control.** The only check that "external knowledge helps" [Tab. 8] is done on one model (LLaMA-2-7B), on one subset (CS), with no control condition. The mandatory controls that are missing: (a) sentences from a *random other* paper of the same conference — to separate the effect of relevant knowledge from the effect of extra context and a changed prompt format; (b) the top-3 sentences from the script of the neighbouring segments themselves. Besides, what is retrieved is the text of the very paper this presentation was made from, and speakers at CHI/UbiComp often read out formulations from the paper — the retrieval here is at times close to retrieving the answer itself.

**Unfair comparisons in the baselines.**
- TTS: MQTTS is trained on M³AV's train split and conditioned on a speaker embedding of a speaker from the same domain; Bark and SpeechT5 are applied zero-shot, trained on other data, with different text normalisation and a different target style (clean studio speech). An in-domain model beating an out-of-domain one is a tautology, but it is presented as a property of the data.
- SSG: LLaMA-2 and InstructBLIP are fine-tuned on M³AV's train split (which gives them a stylistic advantage in ROUGE), while GPT-4/GPT-4V are called zero-shot with no few-shot examples and no indication of the target length or style. The comparison mixes three factors: model size, training regime and evaluation format. The conclusion "open-source needs better pre-training data" does not follow from such a design.
- ASR: their own AED/RNN-T are trained on 295 h of in-domain data; SeamlessM4T-v2 and Wav2Vec2 are out-of-domain. That "Whisper is better than our systems" is honestly marked in italics, but the general frame "existing models showcase limited performance" [§1] leans on a mixture of in-domain and out-of-domain systems.

## 3. Data leaks

- **Audio in pre-training.** See above: NIH WALS and Oxford Mathematics are public playlists with a long history; the probability of their appearing in the Whisper/NeMo/Seamless training mixtures is high and is not checked.
- **Circular labels** in dev/test → effectively a leak of Microsoft's/Whisper's training signals into the "gold standard".
- **The speaker split is heuristic.** "Speaker ... identified by the introductory information and description text" [§4.2.3]. No diarisation, no speaker embeddings, no post-hoc verification. Meanwhile IPP (67 videos) is **one course** with recurring lecturers, split as 49/5/13; NIH WALS is a series where invited speakers appear repeatedly in different years. The risk of a speaker leaking into the test set is real and directly inflates both the WER results and the MOS for MQTTS (the model may have seen the test speaker's voice).
- **Topic leakage and slide-template leakage.** The split is by video rather than by session/course. Neighbouring lectures of the IPPCR course share terminology, a slide template and entire repeated slides ("Objectives", "Outline"). CHI 2021 consists of talks from one conference with a common design. For the Script→Slide task, whose metric is the match of the slide's text, this is a noticeable source of inflation.
- **GPT-4 and the CHI/UbiComp papers.** GPT-4's cut-off covers 2021; the CHI 2021 and UbiComp 2020 papers are almost certainly in its pre-training. For Slide→Script on the CS subset this is a direct leak of content into the closed model — which makes the GPT-4 vs LLaMA-2 comparison even less interpretable.
- **Rare words.** The rare-word list is built from the frequencies in train and applied to dev/test — the methodology here is correct.

**Separately on the rare-word statistics.** §3.2: "the vocabulary size of the spoken form is 47865, of which words with a frequency within 1k number 47483 (99.20%)". That statement is true for practically any natural corpus (Zipf's law) and is no evidence of any special saturation with terminology. Plus there is a discrepancy with the appendix: App. B.2 speaks of "about 43k distinct words" and "about 38k" rare ones. 47865 vs 43k are inconsistent numbers in one work.

## 4. Reproducibility: what is actually available

Here the work looks substantially better than the average dataset paper, but with caveats.

**Available:**
- The repository `github.com/Jack-ZC8/M3AV-dataset` (last push 2025-05-29, 24 stars, 3 open issues). It has `set_split.json` (1113 records), `paper_link.json` (767 links), the SHA-256 of every archive, and a demo sample with a description of the format.
- The data on HuggingFace `CHHHH/M3AV_v1.0`, 45.5 GB, public, not gated: 2.02 GB of "noaudio" (slide frames + JSON annotations + the papers' sentences) and 43.5 GB of audio cut into 9 parts.
- The benchmarks: ASR — an ESPnet recipe (`egs2/M3AV/asr1`); CASR — a recipe plus patches; TTS — a full fork of MQTTS (`train.py`, `trainer.py`, `infer.py`, `tester.py`, the quantiser, the measures); SSG — the data preparation code, the LoRA fine-tune of LLaMA-2, the GPT-4/GPT-4V scripts, and ROUGE/BERTScore/BARTScore scoring.

**Not available / problematic:**
- **The video is not distributed.** Only `raw/*.mp4.ytbUrl`. Any work requiring the talking head, gestures or transition animations is irreproducible without re-downloading from YouTube, where the links gradually die. A dataset titled "Audio-**Visual**" in practice hands over audio plus static frames.
- **CASR depends on an unmerged PR** to ESPnet, #5261, plus a manual replacement of `espnet2/text/Butils.py` and `espnet2/bin/asr_inference.py`. This is guaranteed bit-rot: any update to ESPnet breaks the recipe.
- **GPT-4/GPT-4V are irreproducible.** In `ssg_gpt4/gpt4_generate.py` the models are given as `model='gpt-4'` (a floating alias) and `model='gpt-4-vision-preview'` (retired). The paper gives no version or snapshot date. The generation parameters are `temperature=1.0, top_p=0.9, n=1, seed=0` — `seed` in the OpenAI API gives only "best effort" determinism. The numbers in Tab. 7 and Tab. 9 cannot be reproduced in principle.
- **The slide deduplication thresholds are not published.** $\min^{\text{B}}_{\text{alpha}}$, $\min^{\text{I}}_{\text{B}}$, $\max^{\text{I}}_{\text{B}}$, $\min_{\text{ER}}$ and the choice of WER/CER are declared to be source-dependent [App. A.2], but the specific values are given neither in the paper nor in the repository. The dataset cannot be recreated from scratch.
- **The "paper vs release" discrepancy** about the source of the train transcripts (Microsoft in the paper, Whisper in the README) is resolved nowhere.
- There are no model checkpoints, no training logs, no raw annotator scores (so the IAA cannot be recomputed independently).

**Licences and legal status.** The dataset is published under CC BY-NC-SA 4.0 while the authors openly admit they do not own the rights to the videos. Distributing **the full audio** (43.5 GB) and extracted frames of other people's videos under one's own licence is legally contentious and differs by source: NIH (the work of a US federal agency, de facto public domain) — low risk; CHI/UbiComp — recordings whose rights belong to the ACM/the authors; Oxford Mathematics — Oxford's rights. The file `paper_sentences.json` is a derivative of PDFs from `dl.acm.org`, and redistributing it under CC BY-NC-SA is dubious. The Ethical Consideration section [§Ethics] limits itself to the phrase "copyright remains with the original owners" and does not go into these distinctions. The claim of "fair payments" is unsupported: 0.06 USD per sample without any indication of the time per sample makes it impossible to check compliance even with a minimum wage.

## 5. What the authors acknowledge themselves

The Limitations section [§Limitations] honestly lists: possible biases by presentation type and speaker demographics; a limited range of domains (no humanities) and monolingualism (English only); the visual information being under-annotated — illustrations from the slides are not extracted (unlike LPM) and talking heads are not isolated; and, in the Slide Generation task, only the text of the slide being generated, not an image.

What they do not acknowledge: (1) the machine origin of the overwhelming majority of the "gold" transcripts; (2) the circularity of the ASR evaluation; (3) the absence of a benchmark on their own OCR annotation; (4) the extreme imbalance of the sources and the absence of per-source results; (5) the statistical weightlessness of the human evaluations.

---

# Related Work positioning

M³AV stands between two lines of work. The recognition line: **LectureVideoDB** (Dutta et al., 2018; 24 videos, 5474 frames, manual annotation of text and handwriting, no speech) and **SlideSpeech** (Wang et al., 2023; 1705 videos, 1080 h, automatic OCR + manual transcriptions). The understanding line: **LectureBank** (Li et al., 2019; prerequisite chains), **TalkSumm** (Lev et al., 2019; 1716 paper summaries from talk transcripts), **AVIATE** (Atri et al., 2021; 8201 videos, ~2300 h, fully automatic annotation, abstractive summarisation), **LPM** (Lee et al., 2022/2023; 334 videos, 187 h, cross-modal retrieval with extracted illustrations), **GoogleI/O** and **LaRochelle** (video-level retrieval).

M³AV's differentiating claim is to be the only corpus with manual annotation of both the slides (including handwriting and formulas in LaTeX) and the speech, plus the texts of the papers, supporting both groups of tasks. The first half of the claim rests on the elastic definition "M = fully **or partially** manual"; the second (both groups of tasks) is not realised, since the task of recognising the text of the slides is not benchmarked. By volume M³AV is smaller than SlideSpeech (367 h vs 1080 h) and AVIATE (~2300 h) but larger than LPM (187 h), and noticeably richer in the number of annotation types. The closest competitor in spirit is LPM (aligned slides and speech, cross-modal tasks); M³AV's main real advantages over it are word-level timings, spoken/written forms, LaTeX formulas and the framing of a generative SSG task instead of retrieval. By descent the CASR part continues the line of TCPGen (Sun et al., 2021/2023) and audio-visual contextual biasing (Sun et al., 2022), for which M³AV serves as a new test bed.

The overall assessment: as a **resource** M³AV is useful and carefully published — the annotation format is well thought out, the benchmark code really exists, and the data download with a single `wget`. As a **piece of research** it overstates the degree of human involvement in the annotation, builds its ASR evaluation in a circle, does not benchmark its own main artefact (the OCR), and props up its conclusions with human evaluations that do not survive statistical scrutiny.

---

# Anchors

- `dataset_summary: source/03-the_xxx_dataset.tex:L43 — 1113 videos, 366.9 h, the list of the five sources`
- `rare_word_claim: source/03-the_xxx_dataset.tex:L44 — a vocabulary of 47865 words, 99.20% with a frequency < 1k (trivial under Zipf)`
- `split_table: source/03-the_xxx_dataset.tex:L13-17 — Tab. 3, train/dev/test durations by source (295.4/35.1/36.4 h)`
- `complex_pages_table: source/03-the_xxx_dataset.tex:L65-75 — Tab. 4, 772 pages with handwriting/formulas, 577 of them in MLS`
- `data_collection: source/04-creation_pipeline.tex:L5-6 — collection from YouTube, parsing the papers with science-parse`
- `asr_candidates: source/04-creation_pipeline.tex:L22 — the choice of Microsoft STT and Whisper-large-v2 as candidate sources`
- `train_labels_machine_generated: source/04-creation_pipeline.tex:L52 — "For the training set, we directly adopt the Microsoft transcription"`
- `candidate_combination: source/04-creation_pipeline.tex:L54-62 — Case I / Case II, [???] masking, MTurk filling and merging`
- `speaker_split_heuristic: source/04-creation_pipeline.tex:L48 — the speaker is identified from the introduction and the description text`
- `ocr_pipeline: source/04-creation_pipeline.tex:L70-78 — PaddleOCR at 1 fps, deduplication, Mathpix for formulas, QC on 120 images`
- `merge_rules: source/04-creation_pipeline.tex:L86-107 — Eq. (1)-(3), the OCR block merging rules, a=b=0.8, c=0.6`
- `asr_results_table: source/05-benchmarks_and_experiments.tex:L17-30 — Tab. 5, ASR and CASR (WER/BWER)`
- `contamination_claim: source/05-benchmarks_and_experiments.tex:L47 — "avoiding the issue of training data contamination"`
- `casr_conclusion: source/05-benchmarks_and_experiments.tex:L56 — a relative BWER drop of 37.8%/34.2%`
- `tts_results_table: source/05-benchmarks_and_experiments.tex:L82-86 — Tab. 6, FFE/MCD/MOS, GT 3.86±1.02 vs MQTTS 3.67±0.94`
- `mos_sample_size: source/05-benchmarks_and_experiments.tex:L95 — the MOS is computed on 20 random samples`
- `ssg_results_table: source/05-benchmarks_and_experiments.tex:L113-125 — Tab. 7, ROUGE/BERTScore/BARTScore/Human for SSG`
- `rag_ablation_table: source/05-benchmarks_and_experiments.tex:L146-152 — Tab. 8, the effect of adding the paper's sentences (LLaMA-2-7B only, the CS subset)`
- `ssg_human_protocol: source/05-benchmarks_and_experiments.tex:L169 — 100 samples, 3 annotators, the SummEval measures`
- `ssg_claims: source/05-benchmarks_and_experiments.tex:L171 — three "significant observations", including "far from closed-source" and GPT-4V's superiority`
- `annotator_pay: source/08-appendix.tex:L46 — 0.06 USD per sample on MTurk`
- `ocr_qc: source/08-appendix.tex:L51 — quality control over 120 images from 9 annotators`
- `ssg_annotators_internal: source/08-appendix.tex:L57 — MTurk discarded, three researchers of the team do the scoring`
- `casr_details: source/08-appendix.tex:L69-74 — 1000 distractors, rare words outside the top-5k, a vocabulary of ~43k / ~38k rare`
- `dedup_formulas: source/08-appendix.tex:L33-36 — Eq. (4)-(5), WER^mod and CER^mod with almost unpenalised insertions`
- `ssg_training_details: source/08-appendix.tex:L82-84 — LoRA, lr 2e-4, 3 epochs, top_p 0.9, max 300 tokens`
- `detailed_human_scores: source/08-appendix.tex:L100-114 — Tab. 9, GPT-4/GPT-4V get 5.0 for fluency and relevance`
- `limitations: source/07-limit_ethi.tex:L3-9 — the acknowledged limitations (bias, domains, visual information, text-only slides)`
- `ethics_license: source/07-limit_ethi.tex:L13 — CC BY-NC-SA 4.0, copyright remains with the owners of the videos`
- `related_datatype_table: source/02-related_work.tex:L15-31 — Tab. 1, "A" vs "M" annotation across datasets`
- `related_datasize_table: source/02-related_work.tex:L47-63 — Tab. 2 (a size comparison): 1113 videos, 367 h, 24956 slides, 767 papers`
- `dataset_overview_figure: figures/figures_1-1.png — Fig. 1, the three components of the dataset`
- `speech_pipeline_figure: figures/figures_2-1.png — Fig. 2, the four-step transcription pipeline`
- `slide_pipeline_figure: figures/figures_4-1.png — Fig. 4, the slide annotation pipeline`
- `statistics_figure: figures/figures_5-1.png — Fig. 5, hours/slides by source (NIH 235.4 h, MLS 577 slides)`

---

# Glossary

- `M³AV` — the Multimodal, Multigenre, Multipurpose Audio-Visual dataset; 1113 lecture videos from YouTube, 366.9 h.
- `spoken form / written form` — two forms of the transcript: as pronounced ("one hundred thousand") and as written ("100,000"); both are given with word-level timings.
- `CASR` — Contextual ASR: recognition with a hint in the form of a biasing list, a list of rare words that must be recognised exactly.
- `BWER` — biasing WER: errors on rare words only, divided by the number of rare words, counting false insertions of rare words.
- `distractors` — words added to the biasing list but absent from the particular utterance; they imitate a real noisy context.
- `TCPGen` — Tree-Constrained Pointer Generator: a combination of a symbolic search over a prefix tree of the biasing list and a neural pointer.
- `SSG` — Slide and Script Generation: two mirror tasks, Slide→Script (produce the speaker's words from a slide) and Script→Slide.
- `MQTTS` — Multi-codebook Quantized TTS: a two-stage TTS (a waveform quantiser + an autoregressive Transformer over the codes) for spontaneous speech.
- `Case I / Case II` — the fork in combining the candidates: when Microsoft and Whisper agree the label is taken automatically (Case I), otherwise it goes to the annotators (Case II).
- `seg_imgs` — the release directory with the deduplicated slide frames; in effect the only visual modality actually distributed.
