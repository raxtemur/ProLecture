import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import review_inputs  # noqa: E402
import sample_edit  # noqa: E402
from sample_edit import EditError, diff_record  # noqa: E402

# An invented sample with four required windows; it passes the validator.
EXAMPLE = [json.loads(line) for line in
           (ROOT / "docs" / "sample_examples.jsonl").read_text(encoding="utf-8").splitlines()][1]


def kinds(rows):
    return [(row["kind"], row["window"], row["span"]) for row in rows]


class KindOfAnEditTest(unittest.TestCase):
    def edited(self, change, measured=lambda value: False):
        new = copy.deepcopy(EXAMPLE)
        change(new)
        return diff_record(EXAMPLE, new, measured)

    def test_every_field_of_the_schema_has_a_kind(self):
        schema = json.loads((ROOT / "schema" / "sample.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["properties"]), set(sample_edit.TOP_FIELDS))
        trigger = schema["properties"]["triggers"]["items"]["properties"]
        self.assertEqual(set(trigger), set(sample_edit.TRIGGER_FIELDS))

    def test_the_kinds_are_those_the_log_knows(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import coordinator_log
        used = (set(sample_edit.TOP_FIELDS.values()) | set(sample_edit.TRIGGER_FIELDS.values())
                | {"nudge", "timing", "wording", "boundary"}) - {sample_edit.REFUSE, sample_edit.SPECIAL}
        self.assertEqual(used, set(coordinator_log.RERUN_AFTER))
        self.assertEqual(set(coordinator_log.AFTER_EDIT), set(coordinator_log.RERUN_AFTER))

    def test_the_question_and_its_moment(self):
        rows, _, _ = self.edited(lambda r: r.update(question="Another question?"))
        self.assertEqual(kinds(rows), [("wording", None, False)])
        self.assertEqual(rows[0]["fields"]["question"][1], "Another question?")
        rows, _, _ = self.edited(lambda r: r.update(question_time=r["question_time"] - 2.0))
        self.assertEqual(kinds(rows), [("timing", None, False)])
        rows, _, remarks = self.edited(lambda r: r.update(question_time=r["question_time"] - 2.5))
        self.assertEqual(kinds(rows), [("wording", None, False)])
        self.assertIn("new version of the question", remarks[0])

    def test_the_level_the_act_and_the_service_fields(self):
        rows, _, _ = self.edited(lambda r: r.update(reasoning_level="L1", act="ground"))
        self.assertEqual(kinds(rows), [("level", None, False)])
        self.assertEqual(set(rows[0]["fields"]), {"act", "reasoning_level"})

        def service(r):
            r["validation"]["status"] = "validated"
            r["validation"]["blind_solved"] = False
            r["provenance"]["trap_note"] = "a trap"
            r["template"] = "another"
            r["triggers"][0]["t_ideal"] = 324.0
        rows, _, _ = self.edited(service)
        self.assertEqual(kinds(rows), [("metadata", 0, False), ("metadata", None, False)])
        self.assertEqual(rows[1]["fields"]["validation.blind_solved"], [None, False])
        rows, _, _ = self.edited(lambda r: r.update(twin_of="3b1b__INVENTED_RC__q01"))
        self.assertEqual(kinds(rows), [("rubric", None, False)])

    def test_the_identity_of_a_sample_and_unknown_fields_are_refused(self):
        for change in (lambda r: r.update(id="another"),
                       lambda r: r["video"].update(duration=1.0)):
            with self.assertRaisesRegex(EditError, "cannot be changed"):
                self.edited(change)
        with self.assertRaisesRegex(EditError, "the field\\(s\\) notes are not fields"):
            self.edited(lambda r: r.update(notes="x"))
        with self.assertRaisesRegex(EditError, r"triggers\[1\]\.note is not a field of a window"):
            self.edited(lambda r: r["triggers"][1].update(note="x"))

    def test_a_rubric_a_reference_answer_and_a_dependence_are_the_rubric_of_their_window(self):
        def change(r):
            r["triggers"][1]["rubric"] = r["triggers"][1]["rubric"] + ["one more item"]
            r["triggers"][2]["response"] = "another reference answer"
            r["triggers"][3]["depends_on"] = [2]
        rows, moved, _ = self.edited(change)
        self.assertEqual(kinds(rows), [("rubric", 1, False), ("rubric", 2, False), ("rubric", 3, False)])
        self.assertEqual(moved, {"renumbered": {}, "removed": []})

    def test_a_boundary_within_the_tolerance_is_a_nudge_only_to_a_measurement(self):
        widen = lambda r: r["triggers"][1].update(t_start=334.5)  # noqa: E731
        rows, _, remarks = self.edited(widen, measured=lambda t: t == 334.5)
        self.assertEqual(kinds(rows), [("nudge", 1, False)])
        self.assertEqual(remarks, [])
        rows, _, remarks = self.edited(widen)
        self.assertEqual(kinds(rows), [("boundary", 1, False)])
        self.assertIn("logged as boundary, not nudge: 334.5", remarks[0])

        shift = lambda r: r["triggers"][1].update(t_start=337.0, t_end=351.0)  # noqa: E731
        rows, _, _ = self.edited(shift, measured=lambda t: True)
        self.assertEqual(kinds(rows), [("nudge", 1, False)])
        rows, _, _ = self.edited(shift, measured=lambda t: t == 337.0)  # one end unmeasured
        self.assertEqual(kinds(rows), [("boundary", 1, False)])

        cut = lambda r: r["triggers"][1].update(t_start=337.0)  # noqa: E731
        rows, _, remarks = self.edited(cut, measured=lambda t: True)
        self.assertEqual(kinds(rows), [("boundary", 1, False)])
        self.assertIn("only narrows a window is not usually made", remarks[0])

        far = lambda r: r["triggers"][1].update(t_start=333.0)  # noqa: E731
        rows, _, remarks = self.edited(far, measured=lambda t: True)
        self.assertEqual(kinds(rows), [("boundary", 1, False)])
        self.assertEqual(remarks, [])

    def test_a_span_is_a_boundary_edit_when_the_derived_relation_changes(self):
        inside = lambda r: r["triggers"][2].update(evidence_span=[352.0, 364.0])  # noqa: E731
        rows, _, _ = self.edited(inside)
        self.assertEqual(kinds(rows), [("metadata", 2, True)])

        def before_the_question(r):  # the evidence now starts before question_time: pre -> at
            r["triggers"][0]["evidence_span"] = [310.0, 336.0]
            r["temporal_rel"] = "at"
        rows, _, _ = self.edited(before_the_question)
        self.assertEqual(kinds(rows), [("boundary", 0, True), ("metadata", None, False)])

    def test_an_inserted_window_renumbers_the_later_ones_without_a_rubric_debt(self):
        old = copy.deepcopy(EXAMPLE)
        old["triggers"][3]["depends_on"] = [2]
        new = copy.deepcopy(old)
        early = {**copy.deepcopy(new["triggers"][1]), "required": False, "t_start": 330.0,
                 "t_end": 336.0, "t_ideal": 331.0, "response": "the early form",
                 "rubric": ["the early form"], "evidence_span": [330.0, 336.0]}
        new["triggers"].insert(1, early)
        for idx, trigger in enumerate(new["triggers"]):
            trigger["idx"] = idx
        new["triggers"][4]["depends_on"] = [3]  # the same window under its new number

        rows, moved, _ = diff_record(old, new)

        self.assertEqual(kinds(rows), [("boundary", 1, False), ("boundary", 2, False),
                                       ("boundary", 3, False), ("boundary", 4, False)])
        self.assertEqual(moved, {"renumbered": {1: 2, 2: 3, 3: 4}, "removed": []})
        self.assertEqual(rows[1]["fields"], {"triggers[2].idx": [1, 2]})

        new["triggers"][4]["depends_on"] = [2]  # now it depends on another window
        rows, _, _ = diff_record(old, new)
        self.assertIn(("rubric", 4, False), kinds(rows))

    def test_a_removed_window_and_a_window_turned_optional(self):
        def remove(r):
            del r["triggers"][3]
        rows, moved, _ = self.edited(remove)
        self.assertEqual(kinds(rows), [("boundary", None, False)])
        self.assertEqual(list(rows[0]["fields"]), ["triggers[3] (removed)"])
        self.assertEqual(moved, {"renumbered": {}, "removed": [3]})

        def remove_first(r):
            del r["triggers"][0]
            for idx, trigger in enumerate(r["triggers"]):
                trigger["idx"] = idx
        rows, moved, _ = self.edited(remove_first)
        self.assertEqual(kinds(rows), [("boundary", 0, False), ("boundary", 1, False),
                                       ("boundary", 2, False), ("boundary", None, False)])
        self.assertEqual(moved, {"renumbered": {1: 0, 2: 1, 3: 2}, "removed": [0]})

        rows, _, _ = self.edited(lambda r: r["triggers"][3].update(required=False))
        self.assertEqual(kinds(rows), [("boundary", 3, False)])

    def test_windows_that_changed_in_place_are_matched_in_order(self):
        def change(r):
            r["triggers"][1].update(t_start=330.0, rubric=["rewritten"], response="rewritten")
        rows, moved, _ = self.edited(change)
        self.assertEqual(kinds(rows), [("boundary", 1, False), ("rubric", 1, False)])
        self.assertEqual(moved["renumbered"], {})


class RecordFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "video.full.jsonl"
        self.records = [{"id": "a", "question": "вопрос"}, {"id": "b", "n": 1}, {"id": "c"}]
        self.file.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self.records),
                             encoding="utf-8")

    def test_one_record_is_replaced_and_the_other_lines_are_untouched(self):
        before = self.file.read_text(encoding="utf-8").splitlines()
        sha = review_inputs.record_sha(self.records[1])
        self.assertIsNone(sample_edit.write_record(self.file, "b", sha, {"id": "b", "n": 2}))
        after = self.file.read_text(encoding="utf-8").splitlines()
        self.assertEqual([after[0], after[2]], [before[0], before[2]])
        self.assertEqual(json.loads(after[1]), {"id": "b", "n": 2})
        self.assertEqual([p.name for p in self.file.parent.iterdir()], [self.file.name])

    def test_a_record_that_changed_in_between_is_left_as_it_is(self):
        text = self.file.read_text(encoding="utf-8")
        why = sample_edit.write_record(self.file, "b", "0" * 64, {"id": "b", "n": 2})
        self.assertIn("not the version the edit was made from", why)
        self.assertEqual(self.file.read_text(encoding="utf-8"), text)

    def test_a_new_record_goes_to_the_end(self):
        self.assertIsNone(sample_edit.write_record(self.file, "d", None, {"id": "d"}))
        self.assertEqual(list(review_inputs.read_records(self.file)), ["a", "b", "c", "d"])
        self.assertIn("already in", sample_edit.write_record(self.file, "d", None, {"id": "d"}))


class ValidatorTest(unittest.TestCase):
    def test_only_the_errors_an_edit_adds_are_named(self):
        self.assertEqual(sample_edit.record_errors(EXAMPLE), [])
        broken = copy.deepcopy(EXAMPLE)
        broken["reasoning_level"] = "L9"
        fresh = sample_edit.new_errors(EXAMPLE, broken)
        self.assertEqual(len(fresh), 1)
        self.assertIn("reasoning_level", fresh[0])
        # the same error with another value is not a new one
        worse = copy.deepcopy(broken)
        worse["reasoning_level"] = "L8"
        self.assertEqual(sample_edit.new_errors(broken, worse), [])
        self.assertEqual(sample_edit.new_errors(None, broken), fresh)


if __name__ == "__main__":
    unittest.main()
