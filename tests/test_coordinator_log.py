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
            "--changes", "Moved t_start of trigger 0 to 1706.0; question unchanged.",
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

    def test_adjudicate_is_recorded_and_checked(self):
        ok = self.run_cli(
            "adjudicate", "--sample-id", "sample-q10", "--iteration", "3",
            "--t-val-a", "704.0", "--t-s", "690.0", "--verified", "no",
            "--t-val", "704.0", "--source", "semiblind.3.json",
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        events = self.read_events()
        self.assertEqual(events[-1]["event"], "adjudicate")
        self.assertEqual(events[-1]["t_val_a"], 704.0)
        self.assertEqual(events[-1]["verified"], "no")
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 adjudications", result.stdout)

    def test_check_rejects_an_inconsistent_adjudication(self):
        self.assertEqual(self.run_cli(
            "adjudicate", "--sample-id", "sample-q10", "--iteration", "3",
            "--t-val-a", "704.0", "--t-s", "690.0", "--verified", "yes",
            "--t-val", "704.0", "--source", "semiblind.3.json",
        ).returncode, 0)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verified=yes but t_val != t_s", result.stderr)

        self.assertEqual(self.run_for_video(
            "other-video",
            "adjudicate", "--sample-id", "sample-q11", "--iteration", "1",
            "--t-val-a", "800.0", "--t-s", "790.0", "--verified", "na",
            "--t-val", "800.0", "--source", "semiblind.1.json",
        ).returncode, 0)
        result = self.run_for_video("other-video", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no verification was run", result.stderr)

    def test_check_rejects_unverified_and_unbound_adjudications(self):
        cases = {
            "no-t-val-a": (["--t-s", "690.0", "--verified", "na", "--t-val", "690.0"],
                           "no verification was run"),
            "unbound": (["--t-val-a", "704.0", "--verified", "na", "--t-val", "123.0"],
                        "verified=na but t_val != t_val_a"),
            "yes-without-t-s": (["--t-val-a", "704.0", "--verified", "yes"],
                                "verified=yes without a t_s"),
        }
        for video, (args, message) in cases.items():
            self.assertEqual(self.run_for_video(
                video, "adjudicate", "--sample-id", "sample-q10", "--iteration", "1",
                *args, "--source", "semiblind.1.json",
            ).returncode, 0)
            result = self.run_for_video(video, "check")
            self.assertEqual(result.returncode, 1, video)
            self.assertIn(message, result.stderr, video)

    def test_check_accepts_an_adjudication_with_no_answer_and_no_proposal(self):
        self.assertEqual(self.run_cli(
            "adjudicate", "--sample-id", "sample-q10", "--iteration", "1",
            "--verified", "na", "--source", "semiblind.1.json",
        ).returncode, 0)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)

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
