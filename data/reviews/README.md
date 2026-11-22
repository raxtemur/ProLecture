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
after each terminal result, `sample_edit` when it changes a record, and `adjudicate`
after deciding the left boundary of a sample (checklist 2.2, stages A–C: the semi-blind
`t_val_a`, the sighted `t_s`, whether the verification probe met the rubric, the resulting
`t_val`; the table itself is in `coordinator.<ROUND>.md`), and `note` for anything the other
events cannot say — an agent service that was down, a tool problem, a remark for the audit.
It is the chronology of scheduling, edits and boundary decisions, not
a replacement for the per-question decision files.

**Lines are never edited or deleted**, and nothing in a log is repaired by a note. A launch
whose `spawn` was never logged is restored by its `finish` from the workspace it ran on
(`recovered: true`); a launch that did not start is finished as `failed`. A wrong `adjudicate`
row is repaired by logging its stretch anew with `adjudicate --correction`
(`docs/prompts/coordinator.md`, §6, "Correcting a stretch"). The lines of `3d6DsjIBzJ4` and
`l6DKRf-fAAM` reconstructed by hand on 2026-09-08, before the event existed, are the one
exception on record.

**Records are changed through the same tool.** `sample-edit` (`--set <field>=<value>`, or the
file `sample-get` wrote) checks the edit, logs it and writes the record; the coordinator
writes no file of `data/annotations/` itself. `sample_edit` carries a `kind` — `boundary`,
`nudge`, `rubric`, `level`, `timing`, `metadata` or `wording` — which the tool reads off the
change (`tools/sample_edit.py`) and which names the roles that have to be rerun after it (the
table in `docs/prompts/coordinator.md`, §3). An edit that touches several things gives one
event per kind and window, all with the same `sha_before` and `sha_after` of the record and
the changed values in `fields`. A `boundary` or `rubric` event names its `window`, so that
only that window's review settles the debt; a `nudge` — `t_start` or `t_end` moved by at most
2 s to a reviewer's frame measurement — names its window too but owes no rerun. `check`
reports a missing rerun as pending; `check --final`, run before acceptance, fails on it.
Next to a sample's reviews the tool keeps `.versions/` (every version of the record it has
seen), `.edit/` (the file `sample-get` wrote) and `.finished/` (a copy of each review file as
it stood at its `finish`, named by its hash: a repeated probe writes the same file name).

**A row names a window by the number it had when the row was written.** An optional window
put before the others, or a window removed, shifts the numbers after it. The `sample_edit`
that does it carries the map on its first row — `renumbered` (`{"old": new}`) and `removed` —
and the tool reads the rows before it through that map: the `adjudicate` rows of a stretch
follow their window to its new number, the rows of a removed window drop out of `check`, the
window reviews that earlier edits still owe are owed under the new numbers (and no more for a
window that is gone), and a stretch of a semi-blind review is read under the number its window
had at the launch that walked it (the `spawn` of that round with that `window` and
`inputs.until`). Nothing in the log or in a review file is renumbered. Only `sample-edit` of format 2 writes the map, so the logs
from before read as they did; one of them had its rows renumbered by hand (`ldxFjLJ3rVY`,
2026-10-16).

### Formats of a row

Every row written from 2026-11-22 on carries `"v": 2`. A row without `v` is format 1. The
rules below changed how a log *reads*; each applies by the format of the row named, never by
its date, so that a log written before them checks exactly as it did.

| Rule | Which row decides | Format 1 | Format 2 |
|---|---|---|---|
| a `note` that names an agent | the unmatched `spawn` or `finish` of that agent, and the note | a note of format 1 excuses it | no note excuses it |
| an edit closes the adjudicated stretch of its window | the `sample_edit` row | closes nothing | a `boundary`, `rubric` or `level` edit closes the stretch: the next `adjudicate` row of that window and round re-adjudicates stage A. A row that only renumbers a window or removes one closes nothing |
| a record is compared with the version the log knows | the last `sample_edit` (`sha_after`) or `spawn` (`record_sha`) of the sample | not compared | compared while the record is in `data/annotations/partial/` |

Fields that exist only in format 2:

| Event | Fields |
|---|---|
| `spawn` | `prepared_at`; `repeat_of` (the line of the launch it measures again) and `reason`; `kept` (review files of earlier attempts copied at this launch); `recovered: true` on a launch restored by `finish`, whose `model`, `reasoning_effort` and prompt hashes are null |
| `finish` | `sample_id`, `role`, `iteration` (copied from the `spawn`); `artifact_copy`, `artifact_sha`; `material: "not found"` on a finish whose launch could not be restored — its outcome sets no flag |
| `sample_edit` | `kind` on every row; `fields`, `sha_before`, `sha_after`, `annotations`; `renumbered` and `removed` when the windows were renumbered; `adopted: true` for a change made without the tool and logged after the fact; `added: true` for a new sample |

What format 1 holds and format 2 does not: `spawn` without `record_sha`, `workspace` or a
window index in the role; `sample_edit` without a `kind`; `adjudicate` without a `window`;
launches logged under a nickname instead of the agent id; `reasoning_effort` in free spelling.
The old logs are not rewritten into format 2: the fields were never recorded, and filling
them in now would be inventing them.

Write and validate the log with:

```bash
python3 tools/coordinator_log.py <VIDEO_ID> spawn --help
python3 tools/coordinator_log.py <VIDEO_ID> finish --help
python3 tools/coordinator_log.py <VIDEO_ID> sample-get --help
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
