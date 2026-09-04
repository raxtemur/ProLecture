# Salvage review 2 — `3b1b__l6DKRf-fAAM__q08`

## Corrected decision

The original substantive task is **not solvable from modality material by `t_end = 1283.0`**. The transcript up to 1283 only raises the `P[Language]` question; the frames show the same question and Shannon's portrait. Neither channel supplies the human-guesser source together with corpus sparsity and human generalisation. Under `docs/annotation_pipeline.md:392–396`, the already validated blind answer has `basis = general knowledge` and cannot be reused as evidence for `textonly_solved`, `visiononly_solved`, `frozenframe_solved`, or the full-material solvability probe.

Therefore the prior proposal `textonly_solved = visiononly_solved = frozenframe_solved = true` was incorrect. With the old window the defensible modality result is:

```json
{
  "blind_solved": true,
  "textonly_solved": false,
  "visiononly_solved": false,
  "frozenframe_solved": false,
  "solvable": false,
  "audio_dependency": null,
  "status": "rejected"
}
```

`solvable = false` is a `CRITICAL_FAIL`, so the old predict-ahead task cannot be promoted merely by repairing metadata. To preserve q08 as a validated blind baseline, make the minimal substantive rewrite below: move the firing to the end of the explanation, where the transcript itself contains both required halves.

## Exact salvage edits

1. Replace `question` with:

   > When the author identifies the visible brain in the on-screen interviewee silhouette as the underlying model of language and finishes describing its ability to predict letters from context, state how this answers the earlier on-screen P[Language] ??? question: which source of next-letter probabilities Shannon turned to, and why that source avoids the problem that makes a corpus frequency table unusable.

   This is screen-grounded in two concrete states: the earlier `P[Language] ???` screen and the later silhouette with a visible brain. It also makes the firing depend on completion of the final model-and-context explanation instead of demanding an answer before the material exists.

2. Change labels:

   - `act`: `"predict"` -> `"ground"`
   - keep `temporal_rel = "pre"`
   - keep `reasoning_level = "L1"`: the substantive historical answer is still honestly available blind, so under the coordinator rule this remains a known-fact alarm and a blind baseline, not a primary L2 task
   - `template`: `"prediction_ahead"` -> `"cross-scene grounding"`

3. Replace trigger-0 timing and modality metadata:

   - `t_start`: `1259.0` -> `1461.9`
   - `t_end`: `1283.0` -> `1475.0`
   - `t_ideal`: `1260.0` -> `1462.9`
   - `trigger_modality`: `["speech"]` -> `["visual", "speech"]`
   - `evidence_span`: `[1251.6, 1259.5]` -> `[1458.1, 1461.9]`

   The last required transcript line is 1458.1–1461.9: “language and an ability to predict characters based on the context.” The proposed 13.1-second window starts as that line completes. Per the explicit waiver, these interval edits do not require another interval-viewing pass.

4. Remove this unsupported item from `triggers[0].rubric`:

   > a complete answer additionally notes that long context is the most valuable case

   The rewritten question still asks exactly two substantive things. The remaining rubric covers those two things and its legitimate exclusions; the extra correct detail may remain in `response` but must not determine completeness.

5. Keep the distractor as the progressive-but-incomplete reveal and align its right edge to the new trigger:

   - `distractor_windows[0].t_end`: `1400.0` -> `1461.9`
   - replace `distractor_windows[0].why` with:

     > The author is progressively supplying pieces of the requested explanation, so the stretch is tempting, but the final model-and-context relation named in the question is not complete until the trigger.

   This closes both old distractor defects: the temptation is covered to the trigger, and `why` leaks neither the human-guesser answer nor corpus sparsity/generalisation.

6. Extend the final provenance record:

   - `provenance.evidence[3].t_end`: `1458.1` -> `1461.9`
   - `provenance.evidence[3].explanation`:

     > the interviewee brain is described as an underlying language model able to predict characters from context

7. Set the modality opinion and derived label:

   - keep `audio_dependency_claim = "required"`
   - `audio_dependency`: `null` -> `"required"`

8. Replace `question_time_note` with:

   > The question is issued while language modelling and next-letter probabilities are being introduced. The answer is assembled later from the n-gram failure, human-guessing experiment, and interviewee-brain model, with the final relation completing at 1461.9.

9. Replace `validation.notes` with:

   > Salvage round 2: validated as a blind baseline after a substantive rewrite from predict-ahead to cross-scene grounding. The honest pre-view answer still establishes blind_solved=true, but it is not reused as modality evidence. Transcript evidence by 1461.9 independently supplies corpus sparsity, the human-guesser source, and the brain-as-language-model/context relation, so textonly_solved=true and solvable=true. Vision-only and frozen-frame remain conservatively false because no independent frame probe established the entire rubric from visual material alone; audio_dependency is therefore required. The old full-sample defects were closed by the screen-grounded wording, rubric cleanup, complete distractor coverage, and leak-free distractor reason. Interval values were accepted under the explicit no-recheck waiver.

## Concrete modality evidence

### Old window, through 1283: insufficient

- Transcript 1251.6–1259.5 only asks how the next-letter probabilities are known and says the animation used a language model.
- Transcript 1274.2–1280.4 only announces a step back to Shannon.
- Frames through 1276 show `P[Language] ???`; frames 1279–1281 show Shannon alone.
- No material before 1283 names human guessers, corpus absence of long strings, or a person's context-based generalisation.

Thus for the old wording/window: text `false`, vision `false`, frame `false`, full `false`, solvable `false`.

### Rewritten window, through 1475: transcript is sufficient

The complete answer follows from transcript material, without general knowledge:

- 1283.9–1307.9: n-gram tables are introduced as corpus statistics.
- 1309.9–1318.4: the table breaks down for longer strings, especially strings absent from all analysed books.
- 1339.6–1348.2: Shannon's alternative source is his wife Betty, asked to guess each next letter.
- 1413.3–1430.9: the extended experiment uses human guessers and maps number of guesses to implicit next-letter probability.
- 1437.2–1461.9: this is contrasted with book lookup; the interviewee's brain is the underlying language model, a black box able to predict characters from context.

This satisfies all substantive rubric requirements with `basis = transcript`, hence `textonly_solved = true` and `solvable = true`.

`visiononly_solved` remains `false`: although the visual history contains suggestive n-gram, guessing, paper-table, and brain animations, there is no independent frame-probe artifact proving that the entire corpus-sparsity/generalisation rubric was recovered from frames rather than inferred from topic knowledge. The midpoint of the new `[1461.9, 1475.0)` window is approximately 1468.45, where the screen has moved to an abstract modern-model transition; a single frame does not contain the source and contrast, so `frozenframe_solved = false`.

## Resolution of the four old `full_sample` findings

| Finding | Resolution | Final result |
|---|---|---|
| `question-anchored-to-screen` | The question names the earlier `P[Language] ???` state and the later visible-brain silhouette. | `ok` |
| `rubric-within-question` | Delete the unsupported long-context completeness item. | `ok` |
| `distractor-fully-covered` | Extend the progressive reveal distractor to the new trigger at 1461.9. | `ok` |
| `distractor-why-hides-answer` | Replace `why` with the leak-free wording above. | `ok` |

After these edits the aggregate `full_sample` assessment is **PASS**. Existing checks of the reference answer, provenance substance, unique trigger, and absence of a later duplicate retain their prior support; the participant-visible rewrite is the necessary salvage change that makes the task solvable from actual video material.

## Final flags and lifecycle

```json
{
  "audio_dependency": "required",
  "audio_dependency_claim": "required",
  "validation": {
    "status": "validated",
    "solvable": true,
    "blind_solved": true,
    "textonly_solved": true,
    "visiononly_solved": false,
    "frozenframe_solved": false
  }
}
```

This remains a **validated blind baseline**, excluded from primary tasks by `blind_solved = true`. Its modality and audio labels now come only from material-grounded evidence, not from the blind recollection.

## Verification

- Both existing review artifacts pass `schema/review.py --check`.
- A hypothetical q08 object with the corrected edits above was passed in memory to `tools.validate_samples.semantic_checks`; result: no errors.
- No JSONL file or existing review artifact was modified.
