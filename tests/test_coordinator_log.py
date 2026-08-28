import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "coordinator_log.py"


class CoordinatorLogCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log_root = Path(self.tmp.name)

    def run_cli(self, *args):
        return self.run_for_video("video-id", *args)

    def run_for_video(self, video_id, *args):
        env = os.environ.copy()
        env["COORDINATOR_LOG_ROOT"] = str(self.log_root)
        return subprocess.run(
            [sys.executable, str(SCRIPT), video_id, *args],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def read_events(self):
        path = self.log_root / "data" / "reviews" / "video-id" / "coordinator.log"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_appends_launch_finish_and_sample_edit_events(self):
        launch = self.run_cli(
            "spawn",
            "--agent", "/root/q05_semiblind_r4",
            "--sample-id", "sample-q05",
            "--role", "semiblind",
            "--iteration", "4",
            "--model", "gpt-5.6-sol",
            "--reasoning-effort", "medium",
        )
        self.assertEqual(launch.returncode, 0, launch.stderr)

        finish = self.run_cli(
            "finish",
            "--agent", "/root/q05_semiblind_r4",
            "--status", "completed",
            "--artifact", "data/reviews/video-id/sample-q05/semiblind.4.json",
            "--summary", "Prior could not answer; t_val=951.0.",
        )
        self.assertEqual(finish.returncode, 0, finish.stderr)

        edit = self.run_cli(
            "sample-edit",
            "--sample-id", "sample-q05",
            "--changes", "Added distractor window [1706,1720); question unchanged.",
            "--source", "full_sample.4.json",
        )
        self.assertEqual(edit.returncode, 0, edit.stderr)

        events = self.read_events()
        self.assertEqual([event["event"] for event in events],
                         ["spawn", "finish", "sample_edit"])
        self.assertEqual(events[0]["iteration"], 4)
        self.assertEqual(events[0]["model"], "gpt-5.6-sol")
        self.assertEqual(events[1]["status"], "completed")
        self.assertEqual(events[2]["source"], "full_sample.4.json")
        for event in events:
            self.assertIsNotNone(datetime.fromisoformat(event["ts"]).tzinfo)

    def test_check_accepts_a_balanced_log(self):
        self.assertEqual(self.run_cli(
            "spawn", "--agent", "agent-1", "--sample-id", "sample-q01",
            "--role", "probe_text", "--iteration", "1",
            "--model", "gpt-5.6-sol", "--reasoning-effort", "medium",
        ).returncode, 0)
        self.assertEqual(self.run_cli(
            "finish", "--agent", "agent-1", "--status", "completed",
            "--artifact", "probe_text.1.json", "--summary", "Text was insufficient.",
        ).returncode, 0)

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 launches, 1 finishes, 0 sample edits", result.stdout)

    def test_check_rejects_a_launch_without_finish(self):
        self.assertEqual(self.run_cli(
            "spawn", "--agent", "agent-1", "--sample-id", "sample-q01",
            "--role", "probe_text", "--iteration", "1",
            "--model", "gpt-5.6-sol", "--reasoning-effort", "medium",
        ).returncode, 0)

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("launch without finish: agent-1", result.stderr)

    def test_check_rejects_finish_without_launch(self):
        self.assertEqual(self.run_cli(
            "finish", "--agent", "agent-1", "--status", "failed",
            "--summary", "The reviewer process failed before writing an artifact.",
        ).returncode, 0)

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("finish without launch: agent-1", result.stderr)


    def test_check_rejects_a_second_active_launch_of_the_same_agent(self):
        command = (
            "spawn", "--agent", "agent-1", "--sample-id", "sample-q01",
            "--role", "probe_text", "--iteration", "1",
            "--model", "gpt-5.6-sol", "--reasoning-effort", "medium",
        )
        self.assertEqual(self.run_cli(*command).returncode, 0)
        self.assertEqual(self.run_cli(*command).returncode, 0)

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate active launch: agent-1", result.stderr)

    def test_rejects_a_video_id_that_escapes_the_review_directory(self):
        result = self.run_for_video(
            "../outside",
            "sample-edit",
            "--sample-id", "sample-q01",
            "--changes", "No participant-visible change.",
            "--source", "coordinator.1.md",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("video id", result.stderr.lower())
        self.assertFalse((self.log_root / "data" / "outside" / "coordinator.log").exists())


if __name__ == "__main__":
    unittest.main()
