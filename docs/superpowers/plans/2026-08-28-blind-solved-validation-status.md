# Blind-solved Validation Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make review validity independent from blind-solvability while keeping blind-solved samples out of the primary benchmark.

**Architecture:** Preserve the existing status enum and make `validation.status` describe review correctness/completeness only. Keep benchmark eligibility as a derived selection rule combining `status` and `blind_solved`; synchronize the validator, schema descriptions, coordinator/proposer rules, normative documentation, and current annotation notes.

**Tech Stack:** Python 3, `unittest`, JSON Schema, JSONL, Markdown, LaTeX.

**Spec:** `docs/superpowers/specs/2026-08-28-blind-solved-validation-status-design.md`

## Global Constraints

- Keep the status vocabulary exactly `draft | validated | rejected`.
- Blind solving alone is not a rejection reason.
- Primary tasks require `status == "validated" and not blind_solved`.
- Keep q02, q02b, q03 and q08 rejected; do not rewrite `data/reviews/**` history.
- Preserve S-18 requirements for complete modality flags, measured `audio_dependency`, and `solvable=true`.

---

### Task 1: Validator semantics and regression tests

**Files:**
- Create: `tests/test_validate_samples.py`
- Modify: `tools/validate_samples.py:376-447`

**Interfaces:**
- Consumes: `tools.validate_samples.semantic_checks(sample: dict) -> list[str]` and tracked samples from `data/annotations/l6DKRf-fAAM.jsonl`.
- Produces: S-18 behavior that accepts a complete `validated + blind_solved=true` sample while retaining all other promotion checks.

- [ ] **Step 1: Write the failing acceptance test and preservation regressions**

```python
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools import validate_samples as validator

ROOT = Path(__file__).resolve().parent.parent


def complete_validated_sample():
    path = ROOT / "data" / "annotations" / "l6DKRf-fAAM.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        sample = json.loads(line)
        validation = sample["validation"]
        if validation["status"] == "validated" and validation.get("blind_solved") is False:
            return sample
    raise AssertionError("no complete validated fixture")


class ValidatedBlindSolvedTest(unittest.TestCase):
    def test_complete_blind_solved_sample_can_be_validated(self):
        sample = copy.deepcopy(complete_validated_sample())
        sample["validation"]["blind_solved"] = True
        errors = validator.semantic_checks(sample)
        self.assertEqual(errors, [])

    def test_validated_sample_still_requires_all_measurements(self):
        sample = copy.deepcopy(complete_validated_sample())
        sample["validation"]["textonly_solved"] = None
        errors = validator.semantic_checks(sample)
        self.assertIn("the probes have not answered", "\n".join(errors))

    def test_validated_sample_still_requires_solvable_true(self):
        sample = copy.deepcopy(complete_validated_sample())
        sample["validation"]["solvable"] = False
        errors = validator.semantic_checks(sample)
        self.assertIn("solvable=false is incompatible with validated", "\n".join(errors))

    def test_all_published_annotation_files_validate(self):
        paths = sorted((ROOT / "data" / "annotations").glob("*.jsonl"))
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "validate_samples.py"), *map(str, paths)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
```

- [ ] **Step 2: Run the new acceptance test and verify RED**

Run: `python3 -m unittest tests.test_validate_samples.ValidatedBlindSolvedTest.test_complete_blind_solved_sample_can_be_validated -v`

Expected: FAIL because S-18 emits `blind_solved=true is incompatible with validated`.

- [ ] **Step 3: Remove only the obsolete S-18 branch and update its rule sheet**

Delete the branch appending the blind-solved incompatibility error. Rewrite S-18's `Breaks` and `To check` text to cover incomplete probes and `solvable=false`, without claiming that blind solving prevents validation. Rewrite S-17 and S-25 comments so rejected samples are described as invalid or abandoned records, not the storage mechanism for valid blind baselines.

- [ ] **Step 4: Run focused and complete validator tests**

Run: `python3 -m unittest tests.test_validate_samples -v`

Expected: all four tests PASS.

- [ ] **Step 5: Commit the isolated validator change**

```bash
git add tools/validate_samples.py tests/test_validate_samples.py
git commit -m "fix: separate blind solving from validation status"
```

---

### Task 2: Schema, prompts, documentation, and legacy notes

**Files:**
- Modify: `schema/sample.schema.json`
- Modify: `docs/prompts/coordinator.md`
- Modify: `docs/prompts/proposer.md`
- Modify: `docs/annotation_pipeline.md`
- Modify: `docs/annotation_checklist.md`
- Modify: `data/annotations/README.md`
- Modify: `docs/plans/general.md`
- Modify: `docs/presentation/prolecture.tex`
- Modify: `data/annotations/l6DKRf-fAAM.jsonl`

**Interfaces:**
- Consumes: the semantics implemented by S-18 in Task 1.
- Produces: one consistent public contract and selection rule for annotators, coordinators, and dataset consumers.

- [ ] **Step 1: Add schema descriptions without changing the enum**

Add descriptions equivalent to:

```json
"status": {
  "description": "Review lifecycle and correctness: validated means complete and correct; rejected means incorrect or deliberately abandoned. Primary benchmark eligibility is determined separately by blind_solved.",
  "enum": ["draft", "validated", "rejected"]
},
"blind_solved": {
  "description": "Whether the answer was obtained without viewing the video. A true value excludes the sample from the primary benchmark but does not by itself prevent status=validated.",
  "type": ["boolean", "null"]
}
```

- [ ] **Step 2: Update coordinator and proposer decision rules**

In both prompts, state that a complete and otherwise correct blind-solved sample may end as `validated + blind_solved=true`. Preserve the repair attempt for primary-set eligibility. Change the expensive-review wording so candidates are carried through the DAG, while a terminal rejected sample is not scheduled merely to fill measurements.

- [ ] **Step 3: Update normative dataset selection text**

In the pipeline, checklist, annotations README, general plan, and presentation, replace every blind-implies-rejected rule with:

```python
primary_tasks = status == "validated" and not blind_solved
blind_baselines = status == "validated" and blind_solved
invalid_samples = status == "rejected"
```

State that validated blind baselines remain measurable but are excluded from primary tasks, and that terminal rejected samples serve audit/rejection accounting rather than mandatory modality measurement.

- [ ] **Step 4: Clarify the four current legacy rejection notes**

Keep each status unchanged and append the independent reason:

- q02: review cycle incomplete; only semiblind completed.
- q02b: unresolved `full_sample` defects and missing probes.
- q03: unresolved `full_sample` trigger/distractor defects and missing probes.
- q08: unresolved `full_sample` defects, missing `full_window`, and missing probes.

Do not modify any file under `data/reviews/`.

- [ ] **Step 5: Run consistency searches and JSON checks**

Run:

```bash
python3 -m json.tool schema/sample.schema.json >/dev/null
python3 -c 'import json; [json.loads(line) for line in open("data/annotations/l6DKRf-fAAM.jsonl")]'
rg -n 'blind_solved\s*=\s*true.*incompatible|blind_solved.*status:? rejected|sample solvable blind.*throw it out|sample solved blind will never reach' docs data/annotations/README.md tools schema
```

Expected: JSON schema parses; the JSONL is checked by the validator in Task 3; the search returns no maintained normative contradiction (historical `data/reviews/**` is excluded from interpretation).

- [ ] **Step 6: Commit the contract and documentation change**

```bash
git add schema/sample.schema.json docs/prompts/coordinator.md docs/prompts/proposer.md docs/annotation_pipeline.md docs/annotation_checklist.md data/annotations/README.md docs/plans/general.md docs/presentation/prolecture.tex data/annotations/l6DKRf-fAAM.jsonl
git commit -m "docs: distinguish blind baselines from rejected samples"
```

---

### Task 3: Repository verification

**Files:**
- Verify only; modify Task 1 or Task 2 files only if a check exposes a defect.

**Interfaces:**
- Consumes: all Task 1 and Task 2 outputs.
- Produces: evidence that code, annotations, and maintained documentation agree.

- [ ] **Step 1: Run the full unit-test suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 2: Validate every published and partial annotation file**

Run:

```bash
python3 tools/validate_samples.py data/annotations/*.jsonl
python3 tools/validate_samples.py data/annotations/partial/*.jsonl
```

Expected: exit code 0 for both sets.

- [ ] **Step 3: Verify legacy statuses and primary-selection contract**

Run a read-only Python check asserting q02, q02b, q03 and q08 are still `rejected`, and use `rg` to confirm maintained documentation contains the two-factor primary selection and no blind-implies-rejected rule.

- [ ] **Step 4: Verify scope and whitespace**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; unrelated pre-existing changes remain untouched.
