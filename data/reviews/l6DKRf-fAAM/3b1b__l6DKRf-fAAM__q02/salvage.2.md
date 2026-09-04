# Salvage-review 2: `3b1b__l6DKRf-fAAM__q02` + `3b1b__l6DKRf-fAAM__q02b`

## Scope and evidence read

This is an independent minimal salvage review of the **current JSONL versions** of both twins. I read `docs/prompts/coordinator.md` in full, the relevant checklist/pipeline rules and role prompts, both current annotation rows, and every existing artifact under the two review directories:

- q02: `coordinator.1.md`, `semiblind.1.json`;
- q02b: `coordinator.1.md`, `semiblind.1.json`, `full_sample.1.json`, `full_window0.1.json`.

Per the user's explicit instruction, I did **not** re-review interval boundaries. The prior windows/full-window conclusions are accepted for salvage. In particular, the absence of a saved q02 full-window artifact is not treated as a new interval defect in this review. I did not edit the annotation JSONL or any pre-existing review file.

## Full-sample correctness and twin consistency

The substantive answer is correct and the twins agree. At 1822.0--1825.6 the author says that the interviewees had **at least 100 preceding letters of context**; at 1825.6--1829.4 he gives Shannon's estimate as **about one bit per character**. The existing real-frame evidence at 1828/1830 shows `Bits Per Character ≈ 1.0`. The common `response` contains the same two facts, and the two responses are identical. `L1` is correct: the two facts are consecutive halves of one spoken sentence and require no derivation.

The pair remains a valid timing/control pair. q02 asks the participant to wait for the named estimate; q02b asks for recall after it has passed. Their intended substantive task, answer, rubric, act, and reasoning level agree. q02's early `4.2`, `1.1`, and `1.0 Limit?` material is correctly treated as distractor material: it is attributed to Huffman/neural methods or posed as a question, not presented with Shannon's `≥100`-letter condition. q02b correctly has no distractor windows because those moments precede its `question_time`.

One genuine current full-sample defect remains, but it is metadata-only and trivially repairable: rubric item 3 says that the answer must also state that the estimate came from experiments with people rather than an algorithm. Neither question asks for this third component, and rubric item 4 itself calls the score “1 of 2”. This could punish an answer that supplies exactly the two requested facts.

The q02b full-sample finding `question-anchored-to-screen = fail` is not an additional independent correctness defect for the proposed disposition. It is the structural manifestation of the already measured blind shortcut: the questions ask for a known Shannon result rather than a video-specific unknown. The coordinator rules explicitly allow an otherwise correct blind-solved sample to be `validated` as a blind baseline. Rewriting the participant-visible question merely to clear that structural alarm would create a new review version, and adding only an on-screen label whose value is the same known Shannon estimate would not honestly clear blind solving anyway. For this minimal salvage, keep the questions and preserve `blind_solved = true`.

No independent unfixable defect supports `rejected` after the rubric repair. The previous rejection notes cite incomplete review/probe coverage, not a contradiction in the underlying sample.

## Minimum required edits (apply symmetrically)

For **both** q02 and q02b:

1. Delete exactly this rubric item from `triggers[0].rubric`:

   `it is stated that this is an estimate from experiments with people rather than a measurement by an algorithm`

   Keep the two requested scoring components, the “number alone is partial (1 of 2)” rule, and the two distractor exclusions. This is a rubric-only repair; it does not change the participant-visible question or expected answer.

2. Fill the modality fields and lifecycle fields with the exact values below; replace the stale rejection note with a note saying the sample is a validated blind baseline and citing this salvage review.

Optional wording hardening, not required for salvage: narrow each `do NOT count X` line to “do not count X **when it is offered as Shannon's estimate**”, so merely mentioning the historical 0.6--1.3 range or contrasting the distractor does not accidentally invalidate an otherwise correct answer.

## Honest modality assessment

The flags aggregate over the whole sample, and the evidence is the same for both twins because each modality history extends past 1829.4.

- **Blind: `true`.** Both independent semiblind prior answers, written before viewing, gave about one bit per character and about 100 preceding characters from general knowledge of Shannon's experiment, with no screen-content assumptions and no recognition of this video. This is substantively the rubric answer; the difference between “about 100” and the video's “at least 100” does not change the requested context scale and was consistently credited by the two existing coordinator comparisons. This is contamination, not a correctness failure.
- **Text-only: `true`.** The transcript itself explicitly supplies both required components in the adjacent cues 1822.0--1829.4. No frame or general-knowledge fill-in is needed.
- **Vision-only: `false`.** Frames 1828--1837 clearly supply `Bits Per Character ≈ 1.0`, but they do not explicitly state the condition “at least 100 preceding letters”. The displayed Dickens prefix visible in the frame is only 86 characters including spaces / 66 letters in the transcribed on-screen string, so inferring the exact `≥100` experimental condition from it would be guesswork or outside knowledge. A vision-only answer therefore has at most one of the two required components. This negative is also consistent with the existing visual inspections around 1400--1470 and 1800--1837, which found the experiment imagery and the final counter but no visual `100` label.
- **Frozen-frame: `false`.** q02's midpoint is about 1841 s, where the video has already moved to a binary-number/probability-interval animation and no longer shows either required fact. q02b's midpoint is about 1919.5 s, where the screen shows the talent/supporter outro. Neither single frame answers the question. (Even an earlier 1830 frame would lack the explicit `≥100` condition.)
- **Overall solvable: `true`.** `textonly_solved = true` already proves solvability arithmetically; no conditional full-material probe is necessary. The full-sample evidence independently reconstructs the reference answer from the video.
- **Audio dependency: `required`.** By the mandated derivation, `visiononly_solved = false` and `solvable = true` imply `audio_dependency = "required"`. Here “required” means the speech/transcript content is required under the benchmark's modality definition. The existing annotator claim `audio_dependency_claim = "required"` agrees with the measurement.

## Exact final fields and disposition

### `3b1b__l6DKRf-fAAM__q02`

```json
"audio_dependency": "required",
"validation": {
  "status": "validated",
  "blind_solved": true,
  "textonly_solved": true,
  "visiononly_solved": false,
  "frozenframe_solved": false,
  "solvable": true
}
```

Disposition: **validated blind baseline**, not a primary task. Do not use `rejected`: after deleting the unsupported rubric item, no independent unresolved correctness defect remains. The accepted old interval conclusion stays outside this salvage decision.

### `3b1b__l6DKRf-fAAM__q02b`

```json
"audio_dependency": "required",
"validation": {
  "status": "validated",
  "blind_solved": true,
  "textonly_solved": true,
  "visiononly_solved": false,
  "frozenframe_solved": false,
  "solvable": true
}
```

Disposition: **validated blind baseline**, not a primary task. The saved `full_window0.1.json` is `PASS`; the fact that its evidence precedes the post question/window is the intended `post_control_twin` construction, not a defect. Do not use `rejected` after the shared rubric repair.

## Baseline eligibility

Yes: after the one synchronized rubric deletion and filling the fields above, both records satisfy the intended selector

`blind_baselines = status == "validated" and blind_solved`.

They must be excluded from `primary_tasks` because `blind_solved = true`. Their value is specifically as a matched blind timing/control baseline pair; calling them `rejected` solely because they are blind-solvable or because the original run omitted probes would contradict the coordinator's acceptance rule.
