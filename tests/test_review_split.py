"""The 2.5 split of the window review (schema/review.py, contract 1.4)."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "schema"))

import review  # noqa: E402

WINDOW = 1


def check(item, result="ok", proposal=None, split=None, steps=False):
    c = {
        "group": review.ITEM_GROUP[review.Item(item)].value,
        "item": item,
        "target": {"trigger_idx": WINDOW},
        "looked_at": [{"kind": "cue", "t": 100.0, "what": "a line of speech"}],
        "findings": "what was seen in the window",
        "criterion": "the criterion applied to it",
        "result": result,
    }
    if steps:
        c["steps"] = [{"question": "is there a link", "answer_bool": False, "why": "no item needs it"}]
    if proposal:
        c["proposal"] = {"field": proposal, "value": "120.0", "why": "the proposed cure of the item"}
    if split is not None:
        c["split"] = split
    return c


def make_review(split=None, result="ok", verdict="PASS", proposal=None,
                schema_version: str | None = "1.4"):
    raw = {
        "checklist_version": review.CHECKLIST_VERSION,
        "sample_id": "3b1b__vid__q01",
        "role": "full_window",
        "iteration": 1,
        "model": "test",
        "date": "2026-10-06",
        "workspace": ".review_ws/test",
        "budget": {"frames_viewed": 3},
        "window_idx": WINDOW,
        "verdict": verdict,
        "checks": [
            check("window-can-be-tightened"),
            check("author-says-answer-in-window", result, proposal, split),
            check("event-not-earlier-than-window"),
            check("depends-on-is-dependency", steps=True),
            check("evidence-span-is-last"),
        ],
    }
    if schema_version is not None:
        raw["schema_version"] = schema_version
    return raw


def split(level="L2", act="ground", required=True, handed=(1,), residue=(2,), after=(),
          by_question=()):
    return {"reasoning_level": level, "act": act, "window_required": required,
            "handed_over": list(handed), "handed_over_by_question": list(by_question),
            "residue": list(residue), "handed_over_after": list(after)}


class SplitTest(unittest.TestCase):
    def valid(self, raw):
        return review.FullWindowReview.model_validate(raw)

    def invalid(self, raw, fragment):
        with self.assertRaises(ValidationError) as ctx:
            review.FullWindowReview.model_validate(raw)
        self.assertIn(fragment, str(ctx.exception))

    def test_non_empty_residue_passes(self):
        self.valid(make_review(split()))

    def test_split_required_from_1_4(self):
        self.invalid(make_review(None), "without a split")

    def test_older_contract_needs_no_split(self):
        self.valid(make_review(None, schema_version="1.3"))
        self.valid(make_review(None, schema_version=None))

    def test_split_only_on_item_2_5(self):
        raw = make_review(split())
        raw["checks"][0]["split"] = split()
        self.invalid(raw, "carries a split")

    def test_partition(self):
        self.invalid(make_review(split(handed=(1,), residue=(1, 2))), "both handed over")
        self.invalid(make_review(split(handed=(1,), residue=(3,))), "not 1..N")
        self.invalid(make_review(split(handed=(), residue=())), "not 1..N")
        self.invalid(make_review(split(handed=(2,), residue=(1,), after=(2,))), "not in the residue")
        self.invalid(make_review(split(handed=(1, 1), residue=(2,))), "twice")

    def test_handed_over_after_is_a_window_defect(self):
        s = split(level="L1", handed=(1,), residue=(2,), after=(2,))
        self.invalid(make_review(s), "only after the window")
        self.valid(make_review(s, "fail", "FIX_INTERVALS", "t_start"))
        self.valid(make_review(s, "fail", "FIX_QUESTION", "question"))

    def test_empty_residue_required_window(self):
        s = split(level="L3", handed=(1, 2), residue=())
        self.invalid(make_review(s), "residue is empty in a required window")
        self.invalid(make_review(s, "fail", "FIX_QUESTION", "question"), "CRITICAL_FAIL")
        self.valid(make_review(s, "fail", "CRITICAL_FAIL", "question"))
        self.valid(make_review(s, "fail", "FIX_INTERVALS", "t_end"))

    def test_empty_residue_optional_window(self):
        s = split(level="L2", required=False, handed=(1, 2), residue=())
        self.invalid(make_review(s), "optional window")
        self.valid(make_review(s, "fail", "FIX_INTERVALS", "t_end"))
        self.valid(make_review(s, "fail", "CRITICAL_FAIL", "question"))

    def test_empty_residue_is_the_norm_on_l1(self):
        self.valid(make_review(split(level="L1", handed=(1, 2), residue=())))

    def test_predict_reveal_inside_the_window(self):
        s = split(level="L2", act="predict", handed=(1,), residue=(2,))
        self.invalid(make_review(s), "not reading")
        self.invalid(make_review(s, "fail", "FIX_INTERVALS", "t_start"), "not reading")
        self.valid(make_review(s, "fail", "FIX_QUESTION", "rubric[1]"))
        self.valid(make_review(s, "fail", "FIX_INTERVALS", "t_end"))
        s_opt = split(level="L2", act="predict", required=False, handed=(1,), residue=(2,))
        self.valid(make_review(s_opt, "fail", "FIX_INTERVALS", "t_start"))

    def test_predict_with_everything_revealed_by_the_author(self):
        s = split(level="L2", act="predict", handed=(1, 2), residue=())
        self.invalid(make_review(s), "not reading")
        self.invalid(make_review(s, "fail", "FIX_INTERVALS", "t_start"), "not reading")
        self.invalid(make_review(s, "fail", "FIX_QUESTION", "question"), "nothing is left")
        self.valid(make_review(s, "fail", "CRITICAL_FAIL", "question"))
        self.valid(make_review(s, "fail", "FIX_INTERVALS", "t_end"))

    def test_predict_with_items_given_by_the_question(self):
        s = split(level="L2", act="predict", handed=(1, 2), residue=(), by_question=(2,))
        self.valid(make_review(s, "fail", "FIX_QUESTION", "question"))

    def test_empty_residue_by_the_question_is_cured_by_rewording(self):
        s = split(level="L3", handed=(1, 2), residue=(), by_question=(1,))
        self.valid(make_review(s, "fail", "FIX_QUESTION", "question"))
        self.invalid(make_review(s, "fail", "FIX_INTERVALS", "t_start"), "FIX_QUESTION")

    def test_l1_question_that_gives_the_whole_answer(self):
        s = split(level="L1", handed=(1, 2), residue=(), by_question=(1, 2))
        self.invalid(make_review(s), "hands over every item")
        self.valid(make_review(s, "fail", "FIX_QUESTION", "question"))
        self.valid(make_review(split(level="L1", handed=(1, 2), residue=(), by_question=(1,))))

    def test_by_question_must_be_handed_over(self):
        self.invalid(make_review(split(handed=(1,), residue=(2,), by_question=(2,))),
                     "not in handed_over")

    def test_target_must_be_this_window(self):
        raw = make_review(split())
        raw["checks"][0]["target"] = {"trigger_idx": WINDOW + 4}
        self.invalid(raw, "whose target names windows")

    def test_skipped_needs_no_split(self):
        raw = make_review(None, "skipped", "FIX_INTERVALS")
        raw["checks"][1]["uncovered"] = {"t_start": 100.0, "t_end": 110.0}
        self.valid(raw)


class CheckCliTest(unittest.TestCase):
    def run_check(self, raw, *flags):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
        self.addCleanup(Path(f.name).unlink)
        return subprocess.run([sys.executable, str(ROOT / "schema" / "review.py"), "--check",
                               f.name, *flags], text=True, capture_output=True, check=False)

    def test_new_window_review_must_state_the_contract(self):
        raw = make_review(None, schema_version=None)
        out = self.run_check(raw)
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("schema_version=1.4", out.stdout)
        self.assertEqual(self.run_check(raw, "--legacy").returncode, 0)

    def test_new_window_review_with_split_is_accepted(self):
        out = self.run_check(copy.deepcopy(make_review(split())))
        self.assertEqual(out.returncode, 0, out.stdout)


if __name__ == "__main__":
    unittest.main()
