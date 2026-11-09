# Prompt: the coordinator. Acceptance methodology

The coordinator's prompt to itself. The role is steps 3–6 of the pipeline
[../annotation_pipeline.md](../annotation_pipeline.md): launch the reviewers and probes,
apply the fixes on top of their reviews, derive the flags, decide the fate of every sample
and close the video (§8). Nobody accepts the samples after the coordinator: the status it
sets is the final one.

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

Before you start, read [definitions.md](definitions.md), next to this prompt. It defines the
terms this prompt uses, and its definitions are binding.

**You change your video's data, never the tools.** You write the video's files under
`data/annotations/`, its folder `data/reviews/<VIDEO_ID>/` and its workspaces in
`.review_ws/<VIDEO_ID>/`; scratch files go in those workspaces, not in the repository root.
Code, tests, schemas, prompts and documentation (`tools/`, `tests/`, `schema/`, `docs/`,
`CLAUDE.md`) are not yours to edit, and neither is another video's material. **Why:** every
coordinator and every reviewer runs on the same tools. A check one coordinator loosens so that
its own log passes is loosened for all of them, without anyone deciding it, and the logs it then
passes no longer show what the check was written to show. A wrong `adjudicate` row is
corrected as §6 says ("Correcting a stretch"). Anything else a tool rejects that you believe is
right — a log line that no append can make pass included — is a defect for the project to
decide, not for the run to repair. Record it with
`coordinator_log.py <VIDEO_ID> note --text "tool problem: …"` — the command, the tool's message
and why you believe the tool is wrong — and go on with the rest of the video. If it is the only
thing keeping the video open, end the turn and name it in your final message. Do not edit
`coordinator.log` by hand to get round it, and do not log under another round to get round a
check either: a round is a round of review.

---

## 1. Blind solving: a guessed statement of the problem does not count

**The rule.** The semi-blind reviewer's answer, obtained before viewing, sets
`validation.blind_solved = true` only if it is at once **correct** and **honest** in the sense
of [definitions.md](definitions.md), "`blind_solved`". Recalling a known textbook or
historical fact counts as blind solving; content only this video has does not, however the
answer came by it, and neither does predicting which values, example or layout the screen
will show, even when the prediction is exactly right. Whether an assumption is a guess is
decided by the definition, not by whether the reviewer listed it in
`prior_answer_assumptions`.

**Why.** Blind solving measures whether the answer is available without the video, not
whether a reviewer can luckily reconstruct unseen screen content from a familiar genre.

**Whether the blind answer is correct is the judge's call, not yours.** Once the semi-blind
review is saved, run

    /home/user/conda/bin/python3 tools/coordinator_log.py <VIDEO_ID> blind-judge --sample-id <id> \
        --review data/reviews/<VIDEO_ID>/<id>/semiblind.<ROUND>.json

It scores the `prior_answer` with the judge that will score the models
(`tools/eval_judge.py`), against the rubric the record has now, item by item, and logs the
verdict. The judge runs three times and an item is met when most runs credit it: on a
borderline answer one run may differ, and that difference is not a ground for a ruling. One
answer is judged once on one rubric: the tool refuses to draw the verdict again. After every
edit of the rubric, judge again every answer judged before — each round's, not only the
latest — since an earlier answer may meet the new rubric too; `check --final` names the ones
left. A verdict logged from a single run of the judge does not count: judge that answer again.
Do not re-score the answer yourself: an item the judge credits is met. "The accepted band is so wide that the hit is a coincidence" is
an argument about the rubric, not about the answer: narrow the band (a `rubric` edit, with its
reruns) or accept the verdict. Copy the judge's item-by-item verdict into
`coordinator.<ROUND>.md`, so that it is visible what the sample rests on.

**Departing from the judge is a ruling with its grounds.** Without a ruling,
`blind_solved` is the judge's verdict. What the judge cannot see is whether a credited answer
is honest, and whether an uncredited item decides at all. Read the review's
`prior_answer_assumptions` next to the verdict: a credited item that rests on an assumption
about the screen listed there is a `screen-guess`, and the assumption names the alternative.
Each departure is logged, and belongs to one verdict: when the answer is judged again, rule
again if the grounds still hold.

    /home/user/conda/bin/python3 tools/coordinator_log.py <VIDEO_ID> blind-ruling --sample-id <id> \
        --basis <basis> --items <item ids from the verdict> --text "<grounds>"

- `screen-guess` (the flag stays `false`): a credited item rests on a choice among concrete
  alternatives for the screen's content that the question leaves open. Name the alternative
  and what the answer would have been under it. If you cannot name one, it is not a guess.
- `video-content` (`false`): a credited item rests on content only this video has — its
  example, its numbers, its construction — or on memory of this video. Name it. A published
  fact about the thing the video discusses is prior knowledge, not this video's content, even
  when the video shows it too: the measured value of a constant, Kepler's third law for a
  named planet, the textbook proof that √2 is irrational.
- `repaired` (`false`): an earlier round's answer was credited, and the version since took
  from the question what that answer used — a value, a relation, a named case the old wording
  gave and the new one leaves to the screen. Name it. It is a ruling on that round, with
  `--review <its semiblind file>`, once the new wording has its own judged round.
- `look-only` (`true`): the items the judge did not credit are about the look of the screen
  only — a colour, the choice of symbols — and every substantive item is credited. Name every
  uncredited item; if one of them is substantive, the flag stays `false`.

A fact you have counted as prior knowledge in one sample of the video is prior knowledge in
every sample of it. `check --final` fails on a validated sample whose flag disagrees with the
judge and no ruling explains it.

**A rewrite that keeps the rubric keeps the flag.** Once a blind answer has met the rubric of
a version, every later version with the same rubric items stays `blind_solved = true`,
whatever a later semi-blind run answers — a refusal, a sentence about its knowledge, a weaker
answer. Two runs of one model are one measurement, and the first has already shown the answer
is available without the video. Only a repair clears the flag: one that changes what the
answer has to contain — the rubric items — or one that withholds what the old wording gave,
ruled `repaired`. Changing only *when* to ask is neither. `check --final` compares the rubric
the answers were judged on with the one the record has now.

**A hedged answer is not credited with the better of its branches.** "3 ms, or 12 ms if the
resistors turn out to be in series" does not count as solved, whichever branch matches the
reference: in the measurement a model that names two values is penalised for the wrong one,
and listing the plausible options is not solving.

**A caveat about notation, colour or verbatim wording is not an assumption about
content.** The definition of `blind_solved` says which items decide and what a guess is. Two
answers that look alike are ruled differently:

- "The time constant is 12 ms, if the diagram shows 4 kΩ and 3 µF" — the correctness
  depends on an assumption about the screen: a guess, `blind_solved = false`, even when the
  screen shows exactly these values and the judge credits the 12 ms. The ruling is
  `screen-guess`, and the alternative is any other pair of values.
- "The capacitor voltage follows V₀(1 − e^(−t/RC)), so it reaches 63 % of the supply
  voltage after one time constant; which letters and colours the screen uses I cannot say"
  — its correctness does not depend on the screen. The caveat is no ground for a ruling.
  Items about the screen itself that the answer does not name are unmet, and they do not
  decide: if every substantive item is credited, the ruling is `look-only` and
  `blind_solved = true`. A rubric item about a colour does not rescue the sample: such a
  sample tests colour recognition, not the science. It is repaired or kept as a blind
  baseline like any other.

The reviewer is asked for content, not a meta-statement about it ("I know only the general
textbook derivation" scores nothing; the derivation itself does). A `prior_answer` that is a
sentence *about* the reviewer's knowledge is sent back for the content before it is judged —
that is a follow-up to the same subagent, not a new round.

**A blind-solved sample is not dropped: the version that survives gets the whole cycle.**
`blind_solved` is never a reason to reject a sample or to skip `full_sample` and
`full_window`. It is also not a reason to run them early: the full reviews belong to the
version that survives, and the barrier in section 3 applies to a blind-repair exactly as to
any other cheap fix. The flag itself stays recorded on the version that was measured (its
review files and `coordinator.<ROUND>.md`); only a repair clears it on a later version
(above, "A rewrite that keeps the rubric keeps the flag").

Decide once, from the consolidated cheap results, whether a repair is attempted:

- **Repair.** Make the answer depend on a screen-specific value, relation, transition or
  counterfactual. Changing only *when* to repeat the same known fact is not a repair. Before
  writing it, list the other samples of the same video whose windows lie within 30 s of this
  one and say in `coordinator.<ROUND>.md` what the repaired rubric asks that theirs do not: a
  repair that rests on the same displayed value as a neighbour is a duplicate, not a repair.
  Apply the rewrite in the same package as the other cheap fixes. It is a wording change, so
  the sample goes back to `draft` and to the head of the cheap queue under the question-version
  rule in section 3; `full_sample` and every `full_window` run only on the rewritten version,
  once it has passed the barrier. Do not spend full reviews on the measured wording first: it
  is about to be replaced, and the new cycle re-checks everything they would have checked. Only
  the new reviews can clear `blind_solved`, and only when the rewrite changed the rubric items
  or withholds what the measured wording gave (above, "A rewrite that keeps the rubric keeps
  the flag").
- **No repair** (none found, or the sample is deliberately kept as a blind baseline).
  Apply the non-wording cheap fixes, pass the barrier, and run `full_sample` and every
  `full_window` on that version. A waiting-only task (below) is not kept this way.

If the completed cycle finds the sample otherwise correct, it may finish as
`status: validated` with `blind_solved: true`; keep it out of the primary benchmark and
retain it as a blind baseline. Use `rejected` only for an independent defect or when
repair/review is deliberately abandoned, and record that reason.

**A consequence for the wording.** A question whose condition is named in full in the
question itself and whose answer is a known fact recalled from memory measures only the
moment of speaking, however hard the topic may sound. "Recall something known and say it at
the right moment" is a waiting-only task, at any level and act, and such tasks are not
built — not as primary tasks and not as blind baselines. This is a defect of its own,
independent of `blind_solved`: repair the question so that its answer has to be read or
worked out from the video inside the window, or reject it. A legitimate `L1` task reads its
answer from the video inside the window, and the question itself does not give it
([definitions.md](definitions.md), "`reasoning_level`").

---

## 2. The verdict on 4.2 is set by the coordinator, not the reviewer

The `solvable-without-video` line in the semi-blind reviewer's review is **preliminary**.
They compare their answer not against the rubric but against their own impression of the
material: they have no reference answer and must not have one. So their `result` is read
as a self-report, and `validation.blind_solved` is derived under rule 1 from the judge's
verdict on the answer.

The same holds in reverse: an `ok` from the semi-blind reviewer does not mean the sample
is clean. They may have failed to recall a fact another model will recall.

**Score every probe's answer the way the judge will.** The blind answer is scored by the
judge itself (§1). For each probe's answer, go through the rubric item by item, including
what an item excludes, and use only the material that attempt had. An answer that offers
alternatives for one rubric item does not meet that item, whichever alternative is right: a
hedged answer is not credited with the better of its branches. If the alternatives come from
two readings of the question, that is a defect of the question: fix it. Write the
item-by-item score into `coordinator.<ROUND>.md`.

**Two runs of one model are one measurement.** When roles agree, name the model behind each
result; agreement between runs of the same model is not independent confirmation.

**Settle a disputed value with the smallest check that settles it.** A disagreement about a
number, a coefficient, a sign or which object the question refers to is settled by a
calculation, a transcript line or a frame (for the screen, §7), not by another full review.
Write the check into the decision.

---

## 3. The order of the roles: the cheap ones first, then full review for every candidate

Use a **work-conserving, cheap-first scheduler** across questions. Whenever a slot is free,
give priority to a runnable `semiblind`, `probe_text`, `probe_vision` or `probe_frame` job.
These roles are independent and should run in parallel; `probe_frame` runs once per
required window, with one frame each (the window's middle), and is logged as
`probe_frame<idx>`. `probe_text`, `probe_vision` and
`probe_full` run once per sample, on material up to the `t_end` of the last required window,
and their answer is scored against the rubric of every required window: a modality is
sufficient when the answer meets the rubric of at least one of them. There is no global stage
barrier: one question may advance as soon as its own prerequisites are satisfied while
cheap work for other questions continues to fill the remaining slots. A finished agent keeps
its slot until it is closed: call `close_agent` on it as soon as its `finish` is logged, or
the next launches fail with "agent thread limit reached".

**Do not end your turn while a subagent is running.** A completion notice reaches you only
while your turn lasts: once it has ended, nothing wakes the session, and the finished results
lie uncollected for hours. A progress report is written without ending the turn. End the turn
only when the work on the video is done: no subagent is running, nothing is left to launch
or decide, and the video is closed (§8). When there is nothing to do but wait, call
`wait_agent` on the running agents with a timeout of about ten minutes, and call it again
after it returns. `wait_agent` works
only while the agent service is up; when it returns an error, the completion notices do not
reach you either. Then wait in the shell instead: run
`tools/coordinator_log.py <VIDEO_ID> open --wait 50`, with the shell call allowed about a
minute before it yields, and repeat it. For every launch it reports as saved and passing
`--check`, record the finish with that file as `--artifact`. Run the same command whenever a
launch has been running much longer than its role usually takes.

Normally, do not repair a question from the first cheap result while its other cheap
reviewers are still running. Collect all the cheap results for the same question version,
consolidate their findings together, resolve disagreements once, and apply one coherent
set of cheap fixes. This avoids serial boundary changes and repeated semiblind cycles.

Before launching `full_sample` or any `full_window`, the question must pass this barrier:

- all initial cheap reviews (one `probe_frame` per required window) refer to the exact
  current `question` version;
- the coordinator has consolidated all of them;
- `blind_solved`, `textonly_solved`, `visiononly_solved`, `frozenframe_solved`,
  `solvable` and `audio_dependency` have been derived;
- conditional `probe_full`, if required, has finished;
- cheap fixes have been applied, and every cheap role affected by a repair that leaves the
  question text unchanged has been rerun;
- the video's files pass `tools/validate_samples.py` (§8).

Only then is that question eligible for the expensive queue. Runnable cheap jobs retain
priority over full reviews. Once scheduled, run `full_sample` and one `full_window` per
trigger independently; both are required for every non-terminal candidate, including one
marked `blind_solved`. Do not schedule a sample already terminally `rejected` merely to fill
missing measurements: rejection means an independent defect remains or the work was
deliberately abandoned.

**Why.** Full reviewers are the most expensive in frames and context. The barrier keeps
them from judging wording or boundaries that a cheap result is about to invalidate. They
still run for every candidate because they inspect rubric alignment, trigger completeness
and shape, provenance and window semantics needed either for acceptance or repair — and
because `full_sample` supplies the stage-B proposal `t_s` (section 6).

**`probe_full` is conditional.** Launch it exactly when `probe_text` and `probe_vision`
both answered incorrectly; a positive answer from either already proves solvability.

**Flags are set from probe outcomes only.** An outcome is positive when the probe's answer,
scored against the rubric item by item, is correct and does not rest on a guess about material
the probe was not given — unseen screen content or unheard speech — nor on general knowledge in
place of the material, nor on recognising the video; the probe says either in its `basis`.
Otherwise it is negative. A positive outcome stands. A negative one is not argued away; it is
measured again at most once per probe and version of the sample, and only when you can name the
defect of the attempt with evidence — the probe misread a frame (quote the
frame and what the probe wrote), its workspace lacked material, or its `basis` says the answer
came from general knowledge in place of the material or from recognising the video. That last
attempt measured a memory, not the modality; the outcome of its repeat is final, and if it rests
on memory again it is negative — say so in `coordinator.<ROUND>.md`. Record the reason with
`coordinator_log.py note --agent <new agent> --text "…"`. Launch `probe_full` when the outcomes
of `probe_text` and `probe_vision` are negative after these reruns. The flag is the outcome of
the last run. A probe that fails because the question omits a convention exposes a defect of the
question, not of the attempt: fix the question. An edit that changes a probe's inputs gives a
new measurement, not a repeat (the table below).

Why: the coordinator must not override flags by reasoning — admission to the primary
benchmark and the `audio_dependency` label rest on the negative outcomes. Rerunning the same
model without an evidenced defect is a lottery until the first positive answer, and it
inflates the flags.

**A single frame on `L2`/`L3`: read off or computed.** With `frozenframe_solved = true` on an
`L2`/`L3` sample, read the frame probe's saved answer and classify every scored item it meets
as read off or computed ([definitions.md](definitions.md), "`reasoning_level`"). All of them
read off: the level is inflated — relabel to `L1`, `FIX_QUESTION`; never on a `predict`,
`counterfact` or `extend`, which are never `L1` ([definitions.md](definitions.md), "`act`"):
on a `predict` the frame is
the author's reveal inside the window, and the 2.5 verdicts for a `predict` apply (section
6); on a `counterfact` or an `extend` the answer is on the screen, so the act is wrong — fix
the act or the level. At least one computed: re-derive the level from the computation that
remains. Record the classification in
`coordinator.<ROUND>.md`. A frame can hold every input of a computation and none of its
results; that is no contradiction of the level.

**One model for every role.** For now one local model is available: you and every reviewer
and probe run on it. No role is escalated to a stronger model; a negative probe outcome is
measured again only when the defect of the attempt is evidenced, as above. Pass `model` and
`reasoning_effort` at launch and record both in the `spawn` event, and note in
`coordinator.<ROUND>.md` that all roles ran on one model: their agreement is not independent
confirmation (above).

**A changed participant-visible question creates a new review version.** Set
`validation.status` back to `draft`; retain old reviews as audit history, but do not use
their verdicts or modality flags for the new wording. Return the question to the start of
the cheap queue and pass the barrier again before launching fresh `full_sample` and every
`full_window` with new iteration numbers and separate workspaces. Any change to the text of
`question` — a referent, a when-clause, an added or removed demand — is a new version; no
kind of wording change skips `full_window`. Log it as `sample-edit --kind wording`, and
`check --final` will hold the sample until the roles have been spawned again; it counts one
`full_window` as enough, so make sure yourself that every window was reviewed again.

If the participant-visible `question` is unchanged, an interval, provenance, rubric or other
repair that leaves the question text unchanged needs only the roles whose input changed. Which
ones is not a judgement but this table; record the kind in the `sample-edit` event (`--kind`),
and `check --final` verifies that the reviews were rerun:

| Repair (`question` text untouched) | `--kind` | Rerun | Without a rerun |
|---|---|---|---|
| a window boundary, or an `evidence_span` that changes the derived `temporal_rel` — a span only after §6 has checked it against `t_val` | `boundary --window <idx>`, with `--span` when the span changed | `full_window<idx>` of that window — the index is required, or any window's review would settle the debt; and every probe whose input moved: `probe_frame` of that window (its frame is the window's middle), and `probe_text`, `probe_vision`, `probe_full` when the `t_end` their material ran to has moved. The flag of the old run does not carry over | re-adjudicate stage A against the new `t_start` |
| an `evidence_span` that leaves the derived `temporal_rel` unchanged and passes the validator — a span only after §6 has checked it against `t_val` | `metadata --window <idx> --span` | — | — |
| `t_start` or `t_end` moved by **at most 2 s** to a `full_window` or semi-blind review's own frame measurement, or to a `t_s` verified in stage C, widening or shifting the window | `nudge --window <idx>` | — (the reviewer's frames are the verification). A cut of 2 s or less that only narrows a window is not made. An `evidence_span` disagreement of 2 s or less is not applied: the annotated value stands and the measurement goes into a `note` | nothing; if a later review measures a different second within the same 2 s, the first measurement stands and the disagreement goes into a `note` |
| the text of a rubric item | `rubric --window <idx>`, one event per touched window; omit `--window` when every window's rubric changed | `full_sample` (5.x); `full_window<idx>` of each touched window (2.5, the residue) | run `blind-judge` again on the saved blind answer (§1); re-score the probe answers against the new rubric; re-adjudicate stage A |
| `reasoning_level` only | `level` | — | re-read every 2.5 split against the new level — its copies show the level the review ran with, which is not a defect of the review — and re-adjudicate stage A by the route of the new level |
| `question_time` moved by **at most 2 s** | `timing` | — | stage A's `t_val` does not depend on `question_time`. A larger move changes the moment at which the question must make sense: it is a new version of the question, as a wording change ([definitions.md](definitions.md), "Boundary tolerance") |
| provenance, notes, `trap_note` | `metadata` | — | — |

Consolidate all relevant findings before applying the repair, then rerun the roles the table
names; unaffected evidence remains. `check --final` tracks the reviews of the windows and of
the sample, and it names every modality probe whose last run was cut at material the record
no longer gives — the frame probe of a moved window, a text, vision or full probe whose `t_end`
moved. Run each anew before you accept the sample, and name them in `coordinator.<ROUND>.md`. When a
boundary is uncertain within 2 s, set the window wider rather than narrower — `t_start` at the
early edge, `t_end` at the late one — as long as the rule of the author's reveal still holds
(on `L2`/`L3` and `predict` a window closes at least 10 s before the author says or shows the
answer).

An edit that moves a boundary, sets a flag or changes the wording is followed by
re-examining every sentence in `validation.notes`, `question_time_note` and `provenance`
that states the old value. Reviewers of the next round read these fields.

**A `CRITICAL_FAIL` is rejected or rebuilt.** The verdict means the sample cannot be cured by
moving boundaries or by rewording while it keeps measuring what it measures. Either set
`rejected`, or build a new sample from the same idea — another moment for the question,
another question or another level — from the reviewer's `proposal`; the new sample goes
through the full cycle. The exception is lowering the level to `L1` without changing the
windows or the wording: it needs no second review, and it is legitimate only if the
question does not itself give the answer, and never on a `predict`, `counterfact` or
`extend`.

**A follow-up is part of the same reviewer run.** It may ask an existing subagent to
clarify or complete its current finding before a proposed edit is accepted, but it retains
the agent's prior context and is not independent evidence. After any applied sample edit,
for a new iteration or role/modality, or whenever independent confirmation is required,
spawn a fresh subagent with a separate workspace and iteration.

**Coordinator records use the review-version number, not a separate consolidation count.**
Write the decision as `coordinator.<ROUND>.md`, where `<ROUND>` is the newest review
iteration consolidated by that decision. The record may cite earlier reviews as history,
but its filename and heading must match the current review version. Never call the second
coordinator pass `coordinator.2.md` when it consolidates reviewer iteration 3 or 5.

**What the decision records.** For every check that fired and that you did not apply as
proposed, `coordinator.<ROUND>.md` gives the objection in one sentence, what you checked it
with (a calculation, a transcript line, a frame) and the decision: the exact edit, or why no
edit is needed. "No edit" is a decision and is written down with its reason; a bare label —
"no-op", "in tolerance" — is not a reason: name the measured value or the rule it rests on.
An objection you cannot settle, or one that needs a rule this prompt does not give, stays
open: `PASS` verdicts of other roles do not close it, and it goes under **Open objections**
in `coordinator.<ROUND>.md` and into your final report. Settle it while the iteration limit
allows; at the limit the sample is closed by §8 with the objection still written there.

**Keep one append-only operational log per video.** Immediately after every successful
subagent launch and terminal result, call `tools/coordinator_log.py <VIDEO_ID> spawn` or
`finish`; after an applied sample change, call `sample-edit`. A launch is successful once
`spawn_agent` has returned an agent id: log its `spawn` then, never ahead of a batch of
launches. If a launch whose `spawn` is already logged fails to start, log
`finish --status failed` for it at once. `spawn` takes `--workspace`, the
folder §5 prepared, and refuses it if the record has changed since; `finish` goes under the
name the spawn was logged with, never under a thread id, and the tool refuses a name with no
open launch. A span edit carries `--span` and is refused until its stretch has been
adjudicated (§6). Only the coordinator writes
`data/reviews/<VIDEO_ID>/coordinator.log`, never truncates it, and runs `check --final` before
it closes the video (§8). The log records scheduling and edits; it does not replace
per-question `coordinator.<ROUND>.md` decisions.

---

## 4. The screen index is due to the `vision` probe, but a "yes" is checked against a frame

The text index of the video track (`screen_text.md`, `screen.jsonl`) is built **from the
frames and from nothing but the frames** — the metadata of the description run says
`with_transcript: false`. So for `probe_vision` it is not somebody else's modality but a
dense reading of its own, and it must be handed over.

**Why it must be, not merely may be.** Without the index the probe has only the scene-change
frames, which can be sparse over a long lecture. Then `visiononly_solved = false` means
"they showed me a few pictures" rather than "vision was not enough", and the
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

---

## 5. Reviewer workspaces are per role and are deleted after consolidation

Use exactly one workspace per subagent (`$PROJECT` is the repository root):

```
$PROJECT/.review_ws/<VIDEO_ID>/<QUESTION>/<SUBAGENT_NAME>/
```

Use this source matrix; a boundary-clipped source is clipped to the permitted interval for the role:

| Role | Transcript | Screen index (`screen_text.md`, `screen.jsonl`) | Initial real frames | On-demand `--dense` |
|---|---|---|---|---|
| `semiblind` | clipped | clipped | existing scene frames, copied | allowed |
| `full_sample` | full | full | existing scene frames or manifest | allowed |
| `full_window` | full | full | existing scene frames or manifest | allowed |
| `probe_text` | clipped | forbidden | forbidden | forbidden |
| `probe_vision` | forbidden | clipped | existing scene frames, copied | allowed |
| `probe_frame` | forbidden | forbidden | exactly one frozen frame | forbidden |
| `probe_full` | clipped | clipped | existing scene frames, copied | allowed |
| `probe_verify` | clipped to `t_s` | clipped to `t_s` | existing scene frames, copied | allowed |

**Prepare every workspace from the record.** Do not type a boundary: the script finds the
record by its id, cuts the material for the role, and leaves a note of the record's version
next to the folder (`<folder>.inputs.json`). Name the file you edit:

```bash
P=/home/user/conda/bin/python3
$P tools/prepare_review_workspace.py <VIDEO_ID> --sample-id <SAMPLE_ID> \
    --annotations data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl --role <ROLE> \
    [--window <k>] [--until <t_s>] \
    --out "$PROJECT/.review_ws/<VIDEO_ID>/<QUESTION>/<SUBAGENT_NAME>"
```

| `--role` | Also | The material |
|---|---|---|
| `semiblind` | `--window <k>` | up to `t_end` of window `k`, required or optional: one stretch per window; the next stretch is the same command with the next `k`, into the same folder |
| `probe_text`, `probe_vision`, `probe_full` | — | up to `t_end` of the last required window |
| `probe_frame` | `--window <k>` | the middle frame of required window `k`; one probe per required window |
| `probe_verify` | `--until <t_s>` | up to the `t_s` being verified |
| `full_sample`, `full_window` | — | the whole video, frames as a manifest |

Then log the launch with `spawn --workspace` and the same folder. A folder whose record has
changed since it was prepared is refused: prepare it again.

**The file a role writes** is named in its prompt, and you substitute the placeholders:
`<ROUND>` is the review iteration; `<WINDOW_IDX>` is the window `k` of `full_window` and
`probe_frame` (`full_window<k>.<ROUND>.json`, `probe_frame<k>.<ROUND>.json`); `<N>` numbers
the `probe_verify` launches of a sample within a round from 1, in the order you launch them
(`probe_verify<N>.<ROUND>.json`), and the adjudication table names the `N` of each `t_s`.
Without the index two windows, or two `t_s`, of one round write one file.

The initial visual material is the permitted part of `description.jsonl` plus the
existing scene-change frames listed in `bundle.json["frames"]`. Those frames were
produced by `tools/detect_scenes.py`; the coordinator must not pre-fill a uniform or
dense grid. A role marked `allowed` may call `--dense A B --step 1` after the
description or scene frames identify a suspicious interval.

After a review passes `schema/review.py --check` and its decisions have been incorporated
into `coordinator.<ROUND>.md`, remove that role's reproducible workspace:

```bash
/home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --cleanup --out "$PROJECT/.review_ws/<VIDEO_ID>/<QUESTION>/<SUBAGENT_NAME>"
```

Keep an invalid or unconsolidated workspace for diagnosis. Never ask a validator to delete
it, and never share one workspace between roles.

**What the launch message may contain.** Besides the role prompt with its substitutions (the
question or the task, and `question_time` for the semi-blind reviewer), a semi-blind role
(`semiblind`, `probe_verify`) and the modality probes are told only: the sample id, the path
of their workspace, the `until` of the stretch (not to `probe_frame`, which has one frame and
no stretch), and a change in the order of reading the material that does not shorten what the
role prompt says to read in full. Nothing else:
no timecode of the evidence, no description of what the screen shows, no `t_val` or `t_s`
of earlier rounds, no answer, and nothing the coordinator learned from the human's brief.
The reviewer's step 0 is only worth anything if it really is step 0. A reviewer who is told
the content of the screen must report it in `violations`, and the adjudication is marked
`contaminated` (§6).

---

## 6. The left boundary: stages A–C and the adjudication table

**The rule.** No `PASS` on 2.2 or 2.3 without an adjudication table, and no comparison of a
`t_val` against `t_start` that the table did not produce.

**Why.** Comparing the reviewer's `t_val` with `t_start` as two numbers never reads the
answers. Reviewers have written complete answers about moments earlier than their own
`t_val` without marking them sufficient, and nobody checked those answers against the
rubric. The table makes the coordinator read every one.

**Vocabulary.** *Blind* — the answer before any material (`prior_answer`). *Semi-blind* —
material up to `until`, no answer, no rubric, no `t_start`. *Sighted* — the full reviewer,
with the rubric.

**Stage A.** The semi-blind reviewer returns, per stretch, a trajectory: a `Candidate` with a
full answer at every change of the relevant state, the last at the end of the stretch. The
coordinator checks **every** answer against the rubric of the corresponding window, item by
item, and judges each passing answer by what the stream had supplied up to its moment —
read off or computed ([definitions.md](definitions.md), "`reasoning_level`") — not by how the
reviewer reasoned. The first passing answer that the sample's level reaches by its own route
or a cheaper one — on an `L2` sample the author stating the answer is a cheaper route — is
`t_val_A`. An earlier passing answer that only a harder route reaches — on an `L1` sample,
an answer that has to compute what the window later shows — is classified `harder route`
and is not a hit (below). The reviewer's own `t_val` and `sufficient` flags are self-reports
and carry no status.

**Stage B.** `full_sample` may return `t_s`, the sighted proposal for the first moment the
rubric is satisfiable, with a frame in `t_s_basis`. If `t_s` is null or `t_s ≥ t_val_A`,
nothing more is needed: `t_val = t_val_A`.

**Stage C.** If `t_s < t_val_A`, or `t_val_A` is null and `t_s` exists: prepare a fresh
workspace (§5: `--role probe_verify --until <t_s>`), spawn `probe_verify` with the prompt
`prompts/probe_verify.md`, giving it the task **without its when-clause** (strip the "when …"
part by hand; if the clause defines the object of the task, give the task whole and treat "the
object is not there yet" as an answer). Check its `answer` against the rubric and by the same
route test as stage A. Met by the route of the level or a cheaper one → `t_val = t_s`. Met only
by a harder route → `t_val = t_val_A`, and the `t_s` row is classified `harder route`. Not met
→ `t_val = t_val_A`. One call per `t_s`, short material, only on disagreement.

An early **correct** answer of an evaluated model at `t_m < t_start` (from
`data/outputs`) is a ready-made `t_s`: skip stage B and run stage C at `t_m`. The absence
of such an answer means nothing — the models are weak.

**Check every span against `t_val`** (checklist 7.5). For each required window take its
annotated `evidence_span` and any span the window reviewer proposes. First mark the recaps on
stage A: a stretch that gives a passing answer at its very start from material before the
stretch — the answer was derivable before it began. A recap is not compared; it is an open
question of the checklist. A span that ends more than 2 s before `t_val_A` of its stretch, or
before `t_start` when there is no `t_val_A`, is a sighted `t_s` for that stretch — the annotator
and the reviewer both know the answer — unless it ends before the stretch begins. Treat such a
`t_s` exactly like that of `full_sample`: stage C, then the points below. With several `t_s` for
one stretch, `t_val` is the earliest of `t_val_A` and the `t_s` that stage C passes by the route
of the level or a cheaper one. Once 2.2 has decided, a span agrees with `t_val` when `t_val`
lies inside it, 2 s of tolerance on each side, and it starts no more than 2 s before the piece
that completes at `t_val` begins — the transcript line `t_val` falls in, or the last needed part
of a picture. Apply a proposed span only if it agrees, as an ordinary 7.5 edit (§3); set an
annotated span that does not agree by checklist 1.9 on that piece, logged by §3. Never widen a
span past this to let a moved `t_start` pass the validator: a move of `t_start` left of the
span's start takes the start with it only as far as the span may start, and stops there; when a
re-set span starts after `t_start`, move `t_start` to its start (`boundary`). Also not compared:
a stretch with no `t_val`, the author's own answer as `t_val` on `L2`, `L3` or `predict` (the
point below), and a required window kept for a substantive when-clause. On a window that is not
compared, do not apply a proposed span; a span whose `t_s` failed stage C there goes into
`coordinator.<ROUND>.md` as unresolved. Give each `t_s` its own row in the table, with its
stretch and source (`full_sample`, `annotation`, `full_window<k>`, `provenance`, a model), and
log one `adjudicate` event per stretch and per `t_s`: `--window` names the stretch's required
window, `--t-s-source` the source, and `--verified` is `yes` (met by the route of the level or
a cheaper one), `harder` (only by a harder route) or `no`.

**Then** derive 2.2 and 2.3 from `t_val` (`t_val[0] < question_time` → 2.3;
`t_val[k] < t_start[k]` → 2.2). Inside an optional window is not a hit.

**The table**, one per sample and iteration, in `coordinator.<ROUND>.md`. The example is an
invented `L2` sample: the rubric asks for τ, and the window shows R and C.

| t | answer (short) | rubric items ✓/✗ | reviewer's own view | classification |
|---|---|---|---|---|
| 212.0 | τ = 12 ms from R and C on the diagram | 1 ✓ 2 ✓ | sufficient, high | **t_val_A** |
| 226.0 | the same | all ✓ | sufficient, high | confirmation |
| 241.0 | the same, R and C now also in the table | all ✓ | sufficient, high | (annotated t_start) |
| 198.0 (t_s) | — | — | sighted proposal | verified: not met → stays t_val_A |

Classifications: `t_val_A`, `harder route`, `confirmation`, `partial` (some items ✗ — name
them), `no answer`, and one row per `t_s`, with its stretch, its source, the `N` of its
`probe_verify` and the stage-C outcome.
If the launch message broke the rule of §5 on what a semi-blind role may be told, or the
reviewer reported such a leak in `violations`, mark the table **`contaminated`**: that `t_val_A`
still counts as evidence that a hit exists (the leak could only have made the answer earlier),
but not as evidence that the boundary is clean, and a fresh clean run is needed before a `PASS`
on 2.2/2.3. Then record the decision in the log:

```bash
/home/user/conda/bin/python3 tools/coordinator_log.py <VIDEO_ID> adjudicate \
    --sample-id <SAMPLE_ID> --iteration <ROUND> --window 0 --t-val-a 212.0 \
    --t-s 198.0 --t-s-source full_sample --verified no --t-val 212.0 \
    --source semiblind.<ROUND>.json
```

Each window has a `t_val` of its own, derived from the rows of its own stretch: the
boundary of another window, even of the same sample, is not this window's. The tool derives
`t_val` itself (`--t-val` may be omitted; one given that differs is refused), and a later row
of a stretch without `--t-val-a` takes the stretch's. A row that would not pass `check` with
the rows of its stretch is refused before it is written, and the message says what to do.

**Correcting a stretch.** The log is never edited. When an `adjudicate` row turns out wrong —
a copy error, an answer misjudged on stage A, a `t_val` that does not follow from the rows —
log the stretch anew: the same command with `--correction "<what the earlier rows got
wrong>"`, for the same sample, round and window. The earlier rows of that stretch stay in the
log and drop out of the check; from the correction on, the stretch is checked as usual. A
correction re-reads stage A and nothing else:

- its `t_val_a` is the moment of an answer of the window's own stretch in the semi-blind review
  the earlier rows were read from (if none of them cites one, a semi-blind review of the
  stretch's round or an earlier one), named by `--source`. A moment that no answer of the
  stretch has is a `t_s`, and only stage C makes it the boundary;
- it makes the boundary stricter, never looser: `t_val_a` no later than the earliest answer of
  the stretch the earlier rows logged (for a value they logged that is no answer, the first
  answer after it), and null only when no such answer exists. An answer wrongly taken as
  passing is settled by the next round of review, not by a correction. When a correction moves
  past a value that is no answer — a sighted placement logged as stage A — the tool says so:
  if a sighted reviewer proposed that moment, stage C is owed on it as on any `t_s`;
- every `t_s` of the earlier rows is logged again after it, with its source; until it is,
  `check` lists it as a pending correction and `check --final` fails. One whose probe has run
  keeps the outcome the probe gave, and one logged unverified gets an outcome only from a
  `probe_verify` of this round launched at that moment (`--until` the `t_s`). A probe outcome
  or a source recorded wrongly is not corrected: record it as a tool problem ("You change your
  video's data", at the top of this prompt).

Then re-check what was decided on the old `t_val`: 2.2 and 2.3 by the ladder below, and the
spans checked against it. Write the correction and its reason into the table of
`coordinator.<ROUND>.md` too.

**What to do on a hit** is the ladder below, and it is yours to apply to its end.

- **An earlier, harder route** (a `harder route` row before `t_val_A`, or before `t_start`
  when there is no hit): not a hit. The stretch from that answer (or from `question_time`, if
  it is later) to `t_val`, or to `t_start` if no hit comes, gets an optional window when it
  can hold one — at least 5 s, with the transcript line 2.1 keeps between the windows — and
  none otherwise; log `sample-edit --kind boundary --window <idx>` and run `full_window` on
  it. Within 2 s of `t_start` the route is not asked: the point on a gap up to 2 s applies.
  Inserting a window renumbers the later ones: log `--kind boundary --window <idx>` for the
  new window and for every renumbered one, and name the old → new indices in
  `coordinator.<ROUND>.md`.
- **The author's own answer as `t_val`** on an `L2`, `L3` or `predict` sample: do not move a
  window onto it — a window there repeats the author — and the 2 s tolerance and the gaps
  below do not apply to it. Treat it as an empty residue in a required window:
  `FIX_INTERVALS` when a window of at least 5 s that still contains what the answer is
  worked out from can close 10 s before that moment, otherwise `CRITICAL_FAIL` (§3).
- **Gap up to 2 s** (`t_start − t_val`): not a hit. Move `t_start` to `t_val` (the
  `evidence_span` stays as annotated if it agrees with `t_val`, see the spans above), log
  `sample-edit --kind nudge --window <idx>`, no re-review; a sub-second
  gap the frame step cannot resolve is recorded in the table and the boundary stays. For 2.3,
  a `question_time − t_val` of up to 2 s: move `question_time`, log `--kind timing`, no
  re-review, and measure `t_start` against the same `t_val` by these points.
- **Gap of 2 to 10 s** (`t_start − t_val`): an interval edit. Move `t_start` to `t_val` with
  `evidence_span`, log `sample-edit --kind boundary --window <idx>`, re-review the touched
  window with `full_window<idx>` and rerun the probes whose material moved (the repairs table
  in section 3). For 2.3, a `question_time − t_val` over 2 s goes by step 2 of the ladder
  below.
- **Larger gap:** ask which rubric items become satisfiable, by the route of the level or a
  cheaper one, only once the event of the when-clause has occurred. **Substantive** clause →
  keep the window, add an optional trigger for the early form, log `--kind boundary` for it
  (and for the windows it renumbers), `full_window` on it. **Empty**
  clause → the ladder, in this order:

  0. **Referents and uniqueness.** Re-read the question without its when-part and check that
     every referent resolves to one object on the material up to `question_time`; if not,
     replace the clause by a discriminator rather than dropping it — a mathematical property
     of the object first, the state at the moment of the question second (`full_sample`
     checks the same property from the sighted side). Then ask whether the clause keeps the
     trigger unique: a question that names a state fires at every recurrence of that state,
     so such a clause is narrowed to a time qualifier that holds through the window, not
     dropped. On an `L2`/`L3` or `predict` sample, a moment whose answer the author has
     already said or shown is not a recurrence to cover.
  1. **The early window becomes the required one.** It opens at `t_val`, and its
     `evidence_span` sits on the real evidence. The window of the explicit showing stays as an
     optional one on an `L1` sample; on `L2`/`L3` and `predict` it is removed, and the new
     required window closes at least 10 s before the showing. On `L1`, where both windows
     remain, give **both** a fresh `evidence_span`, each on its own evidence and never on the
     cut (an `evidence_span` ending at its own `t_start` is the tell), and do not join them —
     the early window closes at the start of the transcript line the old `t_start` falls in
     (2.1). On `L2`/`L3` and `predict` only the new required window remains, its
     `evidence_span` on its own evidence. Drop or weaken the clause
     just enough that the wording no longer forbids the early answer. The validator derives
     the axis afresh: `pre` if the evidence comes after `question_time`, otherwise `at` or
     `post`. This is the whole fix when `t_val ≥ question_time`.
  2. **If `t_val < question_time`,** move `question_time` back to `t_val` when the wording
     allows: at the new moment a participant must understand every term, name and formula
     the question uses as known — each is common vocabulary, has been introduced by the video
     by then, or is explained by the question itself in words understood at that moment. If
     one has not, reword the question for the new moment; that is a new version of the
     question (§3). A formula or value the question itself writes out is not evidence for
     the answer: if the video derives it later, the question gives the derivation away, and
     the wording changes with the move. Prefer moving `question_time` — a `pre` is worth
     keeping; any move of it by more than 2 s is a new version of the question (§3),
     reworded or not. Only when no wording can be understood at the new moment, open the
     early window at `question_time`, keep its `evidence_span` on the real evidence and let
     the validator derive `at`/`post`.
  3. **Reject** only when step 2 leaves nothing to measure, with the reason in
     `coordinator.<ROUND>.md`.

  On every step re-derive `reasoning_level`: the cheapest legal route to the full rubric
  inside the required window; a value read off the screen there makes the sample `L1`, and
  an earlier, harder route gets an optional window. Steps 0–2 change the participant-visible
  question or the axis, so the sample goes to `draft` and through the question-version rule
  of §3.

Write in `coordinator.<ROUND>.md` which step was taken and why the lower ones were not.

**A verdict on 2.5 is read against the split** the window reviewer gives for each window,
in the `split` of the 2.5 check: `handed_over` — the rubric items, numbered from 1, the
stream hands over inside the window; `handed_over_by_question` — those of them that would not
be handed over without what the question itself states; `residue` — every other item;
`handed_over_after` —
among the residue, the items handed over in the 10 s after the window; and copies of the
sample's `reasoning_level`, `act` and the window's `required` flag. The contract has already
refused a verdict the split does not allow; what is left to you:

- **Compare the copies with the sample** as it was when the review was launched. A reviewer
  who copied a wrong level, act or flag applied the rules of a different sample: rerun the
  review of that window with the correct values in view, rather than correcting its verdict
  yourself.
- **Check the split, not only the verdict.** Count the question's own statements together
  with the stream: an item that follows from them without any work by the participant is
  handed over. When an item's place in the split decides the verdict, look at the
  transcript lines and the frames the reviewer cites for it (section 7). Check in particular
  `handed_over_by_question`: the contract allows `FIX_QUESTION` on an empty residue only
  because of those items, so an item the author's reveal hands over must not be there. On a
  `predict`, `FIX_QUESTION` for revealed items stands only when they can leave the rubric and
  something is still left to predict.
- **Read the findings for a stated disagreement.** A reviewer who disagrees with the rule
  of 2.5 in this case writes `fail` and explains why in `findings`; you decide. If deciding
  needs a rule this prompt does not give, it is an open objection (§3).
- **Re-derive the level** from what the stream hands over inside the window only; the
  contract cannot check this. If the stream handed over an ingredient but not the answer
  built from it, the residue sets the level: the same level as annotated is `ok`, another
  is `FIX_QUESTION` with the re-derived level, not a rejection.

What the author says in `(t_end, t_end + 10]` is a defect of the window (`FIX_INTERVALS` or
`FIX_QUESTION`), whatever the level: fix the window first, have the split made again on the
moved window, and do not change the level because of it — neither lower it nor, on `L1`,
raise it.

Only an empty residue in a required window compromises an `L2`/`L3` sample; in an optional one
it is `FIX_INTERVALS` — close or remove the window, the level unchanged — unless a later
required window scores the same items: then `CRITICAL_FAIL`, because removing the optional
window would hide that the required one comes after the author's answer. In a required window
it is `FIX_INTERVALS` too when the reviewer's `proposal` gives a new `t_end` at which the
window still contains what the answer is worked out from, lasts at least 5 s and closes 10 s
before the author's answer: move it and keep the level. When items handed over by the question
are what empties the residue, it is `FIX_QUESTION`: rewording returns them to it. Otherwise it
is `CRITICAL_FAIL` (§3). On a `predict` an item the author reveals inside the window is not
reading: the window takes the verdicts of an empty residue, or `FIX_QUESTION` when the revealed
items can leave the rubric and something is still left to predict. `reasoning_level` is one per
sample: re-derive it from the required windows, and when they give different levels, take the
lowest.

---

## 7. When reviews disagree about the screen, look

Two roles may report different things about the same stretch of the screen: one says a state
appears at a given second, another that it never appears; one saw labels at some second,
another says they were gone ten seconds earlier. **Do not settle such a disagreement by
reasoning about who is more likely right, and do not settle it from `description.jsonl`.**
Look:

```bash
/home/user/conda/bin/python3 tools/prepare_review_workspace.py <VIDEO_ID> \
    --dense <A> <B> --step 1 --sheet \
    --out "$PROJECT/.review_ws/<VIDEO_ID>/<QUESTION>/coordinator_sheet"
```

One call gives one image of up to 16 frames with the second stamped on each cell; take
the stretch that covers both reviewers' claims, two sheets if it is longer (a second call
into the same folder needs `--force`: the folder carries no `mode.json`). Open the image
yourself, write into `coordinator.<ROUND>.md` what is on each second that matters, and
adjudicate from that. Remove the folder with `--cleanup` afterwards.

This applies when the disagreement is about **what** is on the screen, or about **when** by more
than 2 s ([definitions.md](definitions.md), "Boundary tolerance"). A gap within 2 s is not
looked at: the first measurement stands. A disagreement about from when the answer is derivable
is not settled by your look either: you know the answer too, so it goes through stage C (§6).

**Why.** The description is written by a model from the same frames and shares the
reviewers' blind spots: a role that read the description repeats its wording, so the
description agreeing with one reviewer is one observation, not two. And a sound explanation
of why the other role is mistaken does not confirm the timestamp of the role you side with:
the explanation can be right and that timestamp still be off by several seconds. A state
that changes gradually reads the same on every frame opened alone; side by side it does
not. The same holds for your own claims: **no verdict, boundary or repair may rest on a
second that no role and no sheet has looked at.**

## 8. The proposer's files are edited in place and merged when the video is closed

**The rule.** Work on the proposer's files `data/annotations/partial/<VIDEO_ID>.<INTERVAL>.jsonl`
in place. Before the first review, give every sample its end-to-end `id`
`3b1b__<VIDEO_ID>__q<NN>`, unique across the files, and remove the duplicates between them.
From then on edit each record in the file that holds it: that file is the `--annotations` of
`prepare_review_workspace.py`, and the validator runs on all the files of the video at once:

```bash
/home/user/conda/bin/python3 tools/validate_samples.py data/annotations/partial/<VIDEO_ID>.*.jsonl
```

Close every sample yourself: `rejected` by the rules that reject, `validated` otherwise — a
sample that ran past the iteration limit or oscillated included, with its open objections
written down (§3). No sample is left in `draft`. Then run `check --final`, and when it passes:

```bash
/home/user/conda/bin/python3 tools/merge_partials.py <VIDEO_ID>
```

It writes `data/annotations/<VIDEO_ID>.jsonl` and removes the files from `partial/`. It
refuses while a sample is in `draft`, while the validator or `check --final` fails, or when
`data/annotations/<VIDEO_ID>.jsonl` already exists, and says why; the video is closed once it
has merged. If it refuses because that file exists, leave the parts where they are and say so
in your final report.

**Why.** The ids come first because the review folders and the log are kept by id. A merge at
the start left two copies of every record, the proposer's and the edited one, and a lookup by
id found both; now one file holds each record until the end, and a file in
`data/annotations/` means a closed video. Nobody accepts the samples after you, so a sample
left in `draft` would be neither measured nor rejected.
