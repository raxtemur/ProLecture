# Prompt: the coordinator. Acceptance methodology

The coordinator's prompt to itself. The role is steps 4–6 of the pipeline
[../annotation_pipeline.md](../annotation_pipeline.md): apply the fixes on top of the
subagents' reviews, derive the flags, decide the fate of the sample.

**Only the non-obvious is written here.** Anything that already follows from the
checklist, the contract or common sense is not repeated. Every item is a decision arrived
at by agreement, usually after the opposite behaviour has already done damage once. Each
one records **why**: without that, two rounds later the rule looks arbitrary and gets
repealed all over again.

This is not a replacement for [annotation_checklist.md](../annotation_checklist.md) (what
is checked) and not a replacement for
[annotation_pipeline.md](../annotation_pipeline.md) (in what order and by whose hands).
It is a third thing: **how to judge** where somebody else's structured answer has to be
turned into a decision.

---

## 1. Blind solving: a guessed statement of the problem does not count

**The rule.** The semi-blind reviewer's answer, obtained before viewing, counts as
compromising the sample (`validation.blind_solved = true`) only if it satisfies **both**
conditions:

- **correct** — it agrees with the rubric;
- **honest** — it does not stand on assumptions about material that was not seen.

If the reviewer assumed **what would turn out to be on screen** — which numbers there
would be, which example the author would take, how many bars there would be — and turned
out to be right, that is **not** blind solving. Not even on an exact hit. Look at the
`prior_answer_assumptions` field: a non-empty list almost always means the agreement was
bought with guessing.

**Why.** The statement of the problem was guessed, the answer was not found. The
participating model in a measurement gets no hint that "this is that familiar textbook
example": it sees the screen and is obliged to read the actual numbers off it. The
reviewer, meanwhile, guesses the distribution from the genre — and guesses well, because
the authors of educational videos take common examples. If such hits are counted, exactly
those tasks that require computing from what is visible will be washed out of the set —
that is, the most valuable ones.

The test "what if something else had been on screen": if with a different set of numbers
(1/32 instead of 1/16, a fifth bar, other probabilities) the guessed answer would have
been wrong, then the reviewer did not solve the task but placed a bet.

**A hedged answer** ("2.5, and if otherwise then 2.0") counts only when the wrong branch
would have cost the participant a point. Otherwise it is enough to list the plausible
options to declare anything at all solved blind.

**The pilot example the rule was written for.** The semi-blind reviewer on `q01` (a
counterfactual on the table of codes) wrote: "I cannot name an exact number, I was given
neither the code words nor the probabilities" — and offered a conditional guess of 2.5
with 2.0 as an alternative, guessing the canonical example 1/2, 1/4, 1/8, 1/8. They gave
themselves a `fail`. The coordinator's correct decision is **not to count it**: the sample
stayed in the set. The same reviewer on `q07` guessed the series `p = 1/2, 1/4, 1/8, 1/16`
and the heights 1, 2, 3, 4 — and that too is a bet, not a solution: with 1/32 or a fifth
bar the answer would have been wrong.

**What does count.** `q02`, `q02b`, `q03`, `q08` — there the blind answer rested on a
commonly known fact (Shannon's estimate of ≈1 bit per character with ~100 characters of
context; the i.i.d. condition for entropy; the experiment of guessing the next letter)
rather than on a guess about the content of a frame. In these samples the video is needed
only in order to work out **when** to speak. This sets `validation.blind_solved = true`,
but it is not by itself a reason to stop reviewing the sample: blind-solved samples are
repair targets, not work to discard before the full reviewers have seen them.

**A blind-solved sample is carried to the end of the cycle.** Keep the contamination flag
on the version that was actually measured, run `full_sample` and every `full_window` on
it, and use their findings to try to move the discriminating part of the answer onto the
video: a screen-specific value, relation, transition or counterfactual whose answer would
change if the author had used different material. A wording wrapper that changes only
*when* to repeat the same textbook fact is not a repair.

After a substantive rewrite, set the sample back to `draft` and run a fresh semi-blind
check and the affected probes/reviewers. Only the new review can clear `blind_solved` for
the rewritten version. Set `status: rejected` only after the full reviews and a genuine
repair attempt show that no faithful video-dependent task can be recovered from the
moment. The coordinator record must say what was tried and why it failed; `blind_solved`
alone is not an adequate rejection note.

**A consequence for the wording.** A question whose condition is named in full in the
question itself and which requires the model to retrieve a known fact from memory is
neither `L3` nor `predict`: it is an `L1` alarm, "recall something known and say it at the
right moment", however hard the topic may sound.

---

## 2. The verdict on 4.2 is set by the coordinator, not the reviewer

The `solvable-without-video` line in the semi-blind reviewer's review is **preliminary**.
They compare their answer not against the rubric but against their own impression of the
material: they have no reference answer and must not have one. So their `result` is read
as a self-report, and `validation.blind_solved` is derived by the coordinator under rule
1.

The same holds in reverse: an `ok` from the semi-blind reviewer does not mean the sample
is clean. They may have failed to recall a fact another model will recall.

---

## 3. The order of the roles: five cheap ones first, then full review for every sample

`full_sample` and `full_window` are launched **last**, once the semi-blind reviewer and
the probes have been consolidated and cheap fixes have been applied. They are not launched
simultaneously with everyone else, as in round 1, but they are launched for **every**
sample — including one currently marked `blind_solved` or `rejected`.

**Why.** The full reviewers are the most expensive in frames and context, so running them
before cheap defects are fixed wastes their judgement on stale wording and boundaries.
But skipping them altogether is worse: a blind-solved or otherwise defective draft may
still contain a strong video-dependent task, and the full reviewers are precisely the
roles that inspect the rubric, distractors, trigger completeness, provenance and window
semantics needed to recover it. Their work is evidence for repair, not a reward reserved
for samples that already look clean.

The order: semi-blind + `probe_text` + `probe_vision` + `probe_frame` (those four in
parallel and independently) → the coordinator's decisions → `probe_full` where it is
needed → cheap fixes and schema validation → `full_sample` plus one `full_window` per
trigger on **all** samples → repair or acceptance → a fresh targeted review of anything
that changed.

**`probe_full` is not always launched**, and that is not an economy but a logic: a
positive answer from any single-modality probe already proves solvability. It is needed
exactly where `text` and `vision` **both** answered incorrectly.

---

## 4. The screen index is due to the `vision` probe, but a "yes" is checked against a frame

The text index of the video track (`screen_text.md`, `screen.jsonl`) is built **from the
frames and from nothing but the frames** — the metadata of the description run says
`with_transcript: false`. So for `probe_vision` it is not somebody else's modality but a
dense reading of its own, and it must be handed over.

**Why it must be, not merely may be.** Without the index the probe gets forty frames for a
half-hour video — one frame every forty-five seconds. Then `visiononly_solved = false`
means "they showed me forty pictures" rather than "vision was not enough", and the
`audio_dependency` label, which is derived straight from that flag, drifts systematically
to `required`. The index is built on a 0.5-second grid — denser than any budget that could
be handed to the probe as frames. That is, it moves the measurement towards honesty rather
than away from it.

**The asymmetry of the check.** A `false` answer is accepted as is: the probe looked
denser than usual and still did not find it. A `true` answer requires confirmation from a
frame — `audio_dependency: unnecessary` is derived from it, and recognition makes
mistakes: it confuses similar digits and finishes off things that are not there. Check
`looked_at`: there must be a frame in there, not a line of the index. One frame per
positive answer is cheap, and positive answers are few.

**Who is not given the index.** `probe_text` — it would receive the visual channel in
words, and `textonly_solved` would stop measuring anything. `probe_frame` — the index is a
timeline, and a frozen-frame probe must see one frame and no history. The script enforces
both bans itself.

**Measurements with the index and without it are not comparable**, which is why the
`screen_index_used` flag exists in `budget`. When assembling the set, look at it: a
`visiononly_solved` obtained the two ways looks the same from outside.
