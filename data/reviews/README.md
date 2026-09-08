# Reviews

This is where the answers of the step-3 subagents of the pipeline live — one file per run:

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/<role>.<ROUND>.json
```

`<role>` is one of `semiblind`, `full_sample`, `full_window`, `probe_text`, `probe_vision`,
`probe_frame`, `probe_full`, `probe_verify` (the last is stage C of the left-boundary check:
a semi-blind probe answering with material up to the sighted proposal `t_s`). The format is
set by the classes in [../../schema/review.py](../../schema/review.py); to check a file, run
`python3 schema/review.py --check <file>`.

A review states the checklist it was made against in `checklist_version`. The files here
made before 2026-09-07 (checklist `2026-08-24`, or no version at all) carry items that were
retired with the `distractor_windows` field and the old shape of the semi-blind
`candidates`; the contract reads them as legacy. `--check` refuses such a file unless it is
told it is an old one: `python3 schema/review.py --check <file> --legacy`. A new review must
state `2026-09-07` explicitly — without it the file is read under the old rules and `--check`
fails, which is the point: forgetting the field must not buy the weaker rules.

Three reasons this directory is under version control rather than in `/tmp`.

**Provenance of the measurements.** A sample remembers the flags (`visiononly_solved` and
the rest) but does not remember who set them. The plan requires the generator, the judge
and the model being evaluated to be different; after the fact that can only be checked
through the `model` field in these files.

**Oscillation.** Rounds do not overwrite each other. From three files in a row one can see
that the window moved left at every iteration while the verdict never budged — from a
single last file that cannot be seen, and the fix cycle looks convergent when it is not.

**Acceptance.** The human at step 6 is handed the sample together with the accumulated
reviews: without them they see the result but not what was actually checked and what was
skipped.

Alongside them lies `coordinator.<ROUND>.md` — free text rather than json: which reviews
and probe answers were read, which flag was set from what, what was derived
arithmetically, what was changed in the sample, what was left unresolved. There is
deliberately no structure here: the coordinator does not answer questions against a
contract, they take decisions on top of somebody else's answers, and what makes that
checkable is the link "these files → these changes" rather than a set of fields.

At the video-directory level, `coordinator.log` is an append-only JSON-lines operational
record. The coordinator writes `spawn` after each successful subagent launch, `finish`
after each terminal result, `sample_edit` after applying a sample change, and `adjudicate`
after deciding the left boundary of a sample (checklist 2.2, stages A–C: the semi-blind
`t_val_a`, the sighted `t_s`, whether the verification probe met the rubric, the resulting
`t_val`; the table itself is in `coordinator.<ROUND>.md`), and `note` for anything the other
events cannot say — a reconstruction of a missing line, an agent whose fate is unknown, a
remark for the audit. It is the chronology of scheduling, edits and boundary decisions, not
a replacement for the per-question decision files.

**Lines are never edited or deleted.** A wrong or missing record is repaired by appending a
`note` that names the agent; `check` then tolerates the unmatched `spawn` or `finish` of
that agent instead of rejecting the log. The lines of `3d6DsjIBzJ4` and `l6DKRf-fAAM`
reconstructed by hand on 2026-09-08, before the event existed, are the one exception on
record; the coordinator owes each of those logs a `note` listing them.

`sample_edit` carries a `kind` — `boundary`, `rubric`, `level`, `timing`, `metadata` or
`wording` — which names the roles that have to be rerun after it (the table in
`docs/prompts/coordinator.md`, §3). `check` reports a missing rerun as pending; `check
--final`, run before acceptance, fails on it. Write and validate the log with:

```bash
python3 tools/coordinator_log.py <VIDEO_ID> spawn --help
python3 tools/coordinator_log.py <VIDEO_ID> finish --help
python3 tools/coordinator_log.py <VIDEO_ID> sample-edit --help
python3 tools/coordinator_log.py <VIDEO_ID> adjudicate --help
python3 tools/coordinator_log.py <VIDEO_ID> note --help
python3 tools/coordinator_log.py <VIDEO_ID> check [--final]
```

The viewing budget (`budget`) is kept here as well and deliberately not carried over into
the sample: it is a property of the measurement, not of the data.

**A note on the language.** The round-1 files stored here were produced before the
repository switched to English, and their bodies are in Russian. They are deliberately
kept verbatim: `prior_answer` is the literal answer a semi-blind reviewer gave before
viewing, and `blind_solved` is derived from it — translating the record would make the
evidence for a dataset label a translation rather than the thing that was said. Every
round produced from now on will be in English, because the role prompts are.
