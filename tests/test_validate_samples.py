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
    sample = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    sample["audio_dependency"] = "required"
    sample["validation"].update({
        "status": "validated",
        "solvable": True,
        "blind_solved": False,
        "textonly_solved": False,
        "visiononly_solved": False,
        "frozenframe_solved": False,
    })
    return sample


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


if __name__ == "__main__":
    unittest.main()
