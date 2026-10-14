import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "merge_partials.py"
VIDEO = "INVENTED_RC"


def examples():
    """The two invented samples, closed: the validator grants `validated` only with a bundle
    and the probes' answers, `rejected` without them."""
    rows = [json.loads(line) for line in
            (ROOT / "docs" / "sample_examples.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    for row in rows:
        row["validation"]["status"] = "rejected"
    return rows


class MergePartialsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.partial = self.root / "data" / "annotations" / "partial"
        self.partial.mkdir(parents=True)
        self.target = self.root / "data" / "annotations" / f"{VIDEO}.jsonl"
        log = self.root / "data" / "reviews" / VIDEO / "coordinator.log"
        log.parent.mkdir(parents=True)
        log.write_text("", encoding="utf-8")

    def write_part(self, name, *rows):
        path = self.partial / f"{VIDEO}.{name}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def merge(self):
        env = os.environ.copy()
        env["COORDINATOR_LOG_ROOT"] = str(self.root)
        return subprocess.run([sys.executable, str(SCRIPT), VIDEO], text=True,
                              capture_output=True, env=env, check=False)

    def test_closed_parts_are_merged_in_id_order_and_removed(self):
        q01, q02 = examples()
        q01["validation"]["status"] = "validated"
        later = self.write_part("b", q02)
        earlier = self.write_part("a", q01)
        refused = self.merge()  # validated without the probes' answers: the validator says no
        self.assertEqual(refused.returncode, 1)
        self.assertIn("the validator fails", refused.stderr)
        self.assertFalse(self.target.exists())

        q01["validation"]["status"] = "rejected"
        self.write_part("a", q01)
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("merged 2 samples (0 validated, 2 rejected) from 2 file(s)", result.stdout)
        ids = [json.loads(line)["id"] for line in self.target.read_text().splitlines()]
        self.assertEqual(ids, [q01["id"], q02["id"]])
        self.assertFalse(earlier.exists() or later.exists())

    def test_a_sample_in_draft_or_without_its_end_to_end_id_stops_the_merge(self):
        q01, q02 = examples()
        q01["validation"]["status"] = "draft"
        q02["id"] = "c7"
        part = self.write_part("full", q01, q02)
        result = self.merge()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{q01['id']} is draft: close it first", result.stderr)
        self.assertIn(f"id 'c7' is not an end-to-end id 3b1b__{VIDEO}__q<NN>", result.stderr)
        self.assertTrue(part.exists())
        self.assertFalse(self.target.exists())

    def test_an_id_repeated_across_parts_stops_the_merge(self):
        q01, _ = examples()
        self.write_part("a", q01)
        self.write_part("b", q01)
        result = self.merge()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"id {q01['id']!r} is also in {VIDEO}.a.jsonl:1", result.stderr)

    def test_an_earlier_annotation_of_the_video_is_never_overwritten(self):
        self.target.write_text("{}\n", encoding="utf-8")
        part = self.write_part("full", *examples())
        result = self.merge()
        self.assertEqual(result.returncode, 2)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(self.target.read_text(), "{}\n")
        self.assertTrue(part.exists())

    def test_a_failing_log_check_stops_the_merge(self):
        (self.root / "data" / "reviews" / VIDEO / "coordinator.log").write_text(
            json.dumps({"ts": "2026-10-01T00:00:00+03:00", "event": "spawn", "agent": "a1",
                        "sample_id": examples()[0]["id"], "role": "full_sample",
                        "iteration": 1}) + "\n", encoding="utf-8")
        part = self.write_part("full", *examples())
        result = self.merge()
        self.assertEqual(result.returncode, 1)
        self.assertIn("check --final fails", result.stderr)
        self.assertIn("launch without finish: a1", result.stderr)
        self.assertTrue(part.exists())


if __name__ == "__main__":
    unittest.main()
