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

    def spawn(self, agent, sample_id, role, video="video-id"):
        return self.run_for_video(
            video, "spawn", "--agent", agent, "--sample-id", sample_id, "--role", role,
            "--iteration", "1", "--model", "claude-sonnet-5", "--reasoning-effort", "medium",
        )

    def test_a_note_documents_an_unmatched_finish_or_launch(self):
        self.assertEqual(self.run_cli(
            "finish", "--agent", "sb_q02_b", "--status", "completed",
            "--summary", "Second run after HTTP 429.",
        ).returncode, 0)
        self.assertEqual(self.spawn("sb_q07", "sample-q07", "semiblind").returncode, 0)
        self.assertEqual(self.run_cli("check").returncode, 1)

        noted = self.run_cli(
            "note", "--agent", "sb_q02_b", "--refers-to", "line 1",
            "--text", "spawn of the relaunch was never written; the artifact exists.",
        )
        self.assertEqual(noted.returncode, 0, noted.stderr)
        self.assertEqual(self.run_cli(
            "note", "--agent", "sb_q07", "--text", "fate unknown after the session was cut.",
        ).returncode, 0)

        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 notes", result.stdout)
        events = self.read_events()
        self.assertEqual(events[2]["event"], "note")
        self.assertEqual(events[2]["refers_to"], "line 1")

    def test_a_note_without_text_or_an_unknown_kind_is_rejected(self):
        self.assertNotEqual(self.run_cli("note", "--agent", "x").returncode, 0)
        self.assertNotEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q01", "--kind", "colour",
            "--changes", "x", "--source", "y",
        ).returncode, 0)

    def test_a_kind_tagged_edit_waits_for_its_reruns(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "rubric",
            "--changes", "R2 now names the displayed value.", "--source", "full_sample.5.json",
        ).returncode, 0)
        # a spawn that happened before the edit does not count
        self.assertEqual(self.read_events()[-1]["kind"], "rubric")

        lenient = self.run_cli("check")
        self.assertEqual(lenient.returncode, 0, lenient.stderr)
        self.assertIn("pending rerun", lenient.stderr)
        self.assertIn("full_sample, full_window", lenient.stderr)
        self.assertIn("1 pending reruns", lenient.stdout)

        final = self.run_cli("check", "--final")
        self.assertEqual(final.returncode, 1)
        self.assertIn("not followed by full_sample, full_window", final.stderr)

        # the rerun of another sample does not satisfy it
        self.assertEqual(self.spawn("fs_q04", "sample-q04", "full_sample").returncode, 0)
        self.assertEqual(self.run_cli(
            "finish", "--agent", "fs_q04", "--status", "completed", "--summary", "ok",
        ).returncode, 0)
        self.assertEqual(self.run_cli("check", "--final").returncode, 1)

        # the window review is logged per window, as the real logs do
        for agent, role in (("fs_q03", "full_sample"), ("fw0_q03", "full_window0")):
            self.assertEqual(self.spawn(agent, "sample-q03", role).returncode, 0)
            self.assertEqual(self.run_cli(
                "finish", "--agent", agent, "--status", "completed", "--summary", "ok",
            ).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pending", result.stdout)

    def test_a_boundary_edit_with_a_window_is_settled_only_by_that_window(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "boundary", "--window", "2",
            "--changes", "evidence_span of trigger 2 -> [228.7, 229.6].",
            "--source", "full_window2.11.json",
        ).returncode, 0)
        self.assertEqual(self.read_events()[-1]["window"], 2)
        # a review of another window of the same sample does not settle the debt
        self.assertEqual(self.spawn("fw3", "sample-q03", "full_window3").returncode, 0)
        self.run_cli("finish", "--agent", "fw3", "--status", "completed", "--summary", "ok")
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not followed by full_window2", result.stderr)
        self.assertEqual(self.spawn("fw2", "sample-q03", "full_window2").returncode, 0)
        self.run_cli("finish", "--agent", "fw2", "--status", "completed", "--summary", "ok")
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_window_is_required_for_boundary_and_refused_elsewhere(self):
        missing = self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "boundary",
            "--changes", "t_start 141.0 -> 205.0.", "--source", "full_window0.9.json",
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("needs --window", missing.stderr)
        stray = self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "wording", "--window", "1",
            "--changes", "referent fixed.", "--source", "coordinator.5.md",
        )
        self.assertEqual(stray.returncode, 2)
        self.assertIn("applies to --kind boundary, nudge or rubric", stray.stderr)
        self.assertFalse((self.log_root / "data" / "reviews" / "video-id" /
                          "coordinator.log").exists())

    def test_a_rubric_edit_with_a_window_is_settled_by_that_window_and_full_sample(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q16", "--kind", "rubric", "--window", "0",
            "--changes", "R0 now demands the 1⁴/4! form.", "--source", "full_sample.3.json",
        ).returncode, 0)
        self.assertEqual(self.spawn("fs", "sample-q16", "full_sample").returncode, 0)
        self.assertEqual(self.spawn("fw1", "sample-q16", "full_window1").returncode, 0)
        for agent in ("fs", "fw1"):
            self.run_cli("finish", "--agent", agent, "--status", "completed", "--summary", "ok")
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not followed by full_window0", result.stderr)
        self.assertEqual(self.spawn("fw0", "sample-q16", "full_window0").returncode, 0)
        self.run_cli("finish", "--agent", "fw0", "--status", "completed", "--summary", "ok")
        self.assertEqual(self.run_cli("check", "--final").returncode, 0)

    def test_a_wording_edit_requires_the_whole_cycle(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q02", "--kind", "wording",
            "--changes", "Referent fixed: 'the blue target function now on the screen'.",
            "--source", "coordinator.5.md",
        ).returncode, 0)
        for agent, role in (("sb", "semiblind"), ("pt", "probe_text"), ("pv", "probe_vision"),
                            ("pf", "probe_frame"), ("fs", "full_sample")):
            self.assertEqual(self.spawn(agent, "sample-q02", role).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not followed by full_window", result.stderr)
        self.assertNotIn("probe_", result.stderr)
        self.assertEqual(self.spawn("fw2", "sample-q02", "full_window2").returncode, 0)
        for agent in ("sb", "pt", "pv", "pf", "fs", "fw2"):
            self.run_cli("finish", "--agent", agent, "--status", "completed", "--summary", "ok")
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_nudge_names_its_window_and_owes_no_rerun(self):
        missing = self.run_cli(
            "sample-edit", "--sample-id", "sample-q17", "--kind", "nudge",
            "--changes", "t_start 1218.0 -> 1217.0.", "--source", "full_window0.2.json",
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--window", missing.stderr)
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q17", "--kind", "nudge", "--window", "0",
            "--changes", "t_start 1218.0 -> 1217.0.", "--source", "full_window0.2.json",
        ).returncode, 0)
        self.assertEqual(self.read_events()[-1]["window"], 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pending", result.stderr)

    def test_edits_without_a_kind_and_kinds_without_reruns_are_not_checked(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q01",
            "--changes", "legacy line", "--source", "coordinator.1.md",
        ).returncode, 0)
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q01", "--kind", "level",
            "--changes", "L3 -> L2 by the residue rule.", "--source", "full_window0.3.json",
        ).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 sample edits", result.stdout)

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
