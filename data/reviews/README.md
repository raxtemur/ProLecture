# Reviews

This is where the answers of the step-3 subagents of the pipeline live — one file per run:

```
data/reviews/<VIDEO_ID>/<SAMPLE_ID>/<role>.<ROUND>.json
```

`<role>` is one of `semiblind`, `full`, `probe_text`, `probe_vision`, `probe_frame`,
`probe_full`. The format is set by the classes in
[../../schema/review.py](../../schema/review.py); to check a file, run
`python3 schema/review.py --check <file>`.

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

The viewing budget (`budget`) is kept here as well and deliberately not carried over into
the sample: it is a property of the measurement, not of the data.

**A note on the language.** The round-1 files stored here were produced before the
repository switched to English, and their bodies are in Russian. They are deliberately
kept verbatim: `prior_answer` is the literal answer a semi-blind reviewer gave before
viewing, and `blind_solved` is derived from it — translating the record would make the
evidence for a dataset label a translation rather than the thing that was said. Every
round produced from now on will be in English, because the role prompts are.
