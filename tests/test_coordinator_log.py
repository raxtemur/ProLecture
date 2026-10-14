import hashlib
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
sys.path.insert(0, str(ROOT / "tools"))
import review_inputs  # noqa: E402


def record(sample_id, windows=((100.0, 110.0), (200.0, 210.0), (300.0, 310.0), (400.0, 410.0))):
    return {"id": sample_id, "validation": {"status": "draft"},
            "triggers": [{"idx": i, "required": True, "t_start": a, "t_end": b}
                         for i, (a, b) in enumerate(windows)]}


class CoordinatorLogCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log_root = Path(self.tmp.name)
        self.annotations = self.log_root / "data" / "annotations" / "video-id.jsonl"
        self.annotations.parent.mkdir(parents=True)
        self.write_records(*(record(f"sample-q{n:02d}") for n in range(1, 18)))

    def write_records(self, *records):
        self.annotations.write_text("".join(json.dumps(r) + "\n" for r in records),
                                    encoding="utf-8")

    def records(self):
        return review_inputs.read_records(self.annotations)

    def workspace(self, agent, sample_id, role):
        """A workspace note as prepare_review_workspace.py --sample-id leaves it."""
        base = role.rstrip("0123456789")
        window = int(role[len(base):]) if role != base else None
        if base == "semiblind":
            window = 0
        current = self.records()[sample_id]
        ws = self.log_root / ".review_ws" / "video-id" / sample_id / agent
        ws.mkdir(parents=True, exist_ok=True)
        inputs = (review_inputs.derive_inputs(base, current, window, until=95.0, duration=1000.0)
                  if base in review_inputs.ROLES else {})
        review_inputs.write_sidecar(ws, {
            "sample_id": sample_id, "annotations": str(self.annotations),
            "record_sha": review_inputs.record_sha(current), "role": base,
            "window": window, "inputs": inputs})
        return ws

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
            "--workspace", str(self.workspace("q05_semiblind_r4", "sample-q05", "semiblind")),
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
            "adjudicate", "--sample-id", "sample-q10", "--iteration", "3", "--window", "0",
            "--t-val-a", "704.0", "--t-s", "690.0", "--t-s-source", "full_sample",
            "--verified", "no",
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

    def write_log(self, *events, video="video-id"):
        """Events as an old log holds them, bypassing the checks of the command line."""
        path = self.log_root / "data" / "reviews" / video / "coordinator.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            for event in events:
                stream.write(json.dumps({"ts": "2026-10-01T00:00:00+03:00", **event}) + "\n")

    def adjudicate(self, *args, video="video-id"):
        return self.run_for_video(video, "adjudicate", "--sample-id", "sample-q10",
                                  "--iteration", "1", "--source", "semiblind.1.json", *args)

    def test_adjudicate_refuses_inconsistent_arithmetic_at_once(self):
        cases = {
            "unverified": (["--window", "0", "--t-val-a", "800.0", "--t-s", "790.0",
                            "--t-s-source", "full_sample", "--verified", "na", "--t-val", "800.0"],
                           "no verification was run"),
            "no-t-val-a": (["--window", "0", "--t-s", "690.0", "--t-s-source", "annotation",
                            "--verified", "na", "--t-val", "690.0"], "no verification was run"),
            "yes-without-t-s": (["--window", "0", "--t-val-a", "704.0", "--verified", "yes"],
                                "verified=yes without a t_s"),
            "source-missing": (["--window", "0", "--t-val-a", "704.0", "--t-s", "690.0",
                                "--verified", "no", "--t-val", "704.0"], "go together"),
            "source-unknown": (["--window", "0", "--t-val-a", "704.0", "--t-s", "690.0",
                                "--t-s-source", "reviewer", "--verified", "no", "--t-val", "704.0"],
                               "full_window<N>"),
        }
        for video, (args, message) in cases.items():
            result = self.adjudicate(*args, video=video)
            self.assertEqual(result.returncode, 2, video)
            self.assertIn(message, result.stderr, video)
        missing_window = self.adjudicate("--t-val-a", "704.0", "--verified", "na", "--t-val", "704.0")
        self.assertEqual(missing_window.returncode, 2)

    def test_several_t_s_of_one_stretch_settle_on_the_earliest_that_passed(self):
        rows = [("full_sample", "690.0", "harder"), ("annotation", "695.0", "yes"),
                ("full_window0", "698.0", "yes")]
        for source, t_s, verified in rows:
            self.assertEqual(self.adjudicate(
                "--window", "0", "--t-val-a", "704.0", "--t-s", t_s, "--t-s-source", source,
                "--verified", verified, "--t-val", "695.0").returncode, 0, source)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_events()[0]["t_s_source"], "full_sample")

        # a row that keeps t_val at a later t_s than the earliest one that passed
        self.assertEqual(self.adjudicate(
            "--window", "1", "--t-val-a", "704.0", "--t-s", "695.0", "--t-s-source", "annotation",
            "--verified", "yes", "--t-val", "695.0", video="v2").returncode, 0)
        self.assertEqual(self.adjudicate(
            "--window", "1", "--t-val-a", "704.0", "--t-s", "690.0", "--t-s-source", "full_sample",
            "--verified", "yes", "--t-val", "695.0", video="v2").returncode, 0)
        result = self.run_for_video("v2", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("earliest of t_val_a and the t_s verified yes is 690.0", result.stderr)

    def test_a_stretch_logged_stage_by_stage_holds_the_boundary_as_it_stood(self):
        # stage A as soon as the semi-blind review is scored, stage C once its probe has run
        self.assertEqual(self.adjudicate(
            "--window", "0", "--t-val-a", "300.0", "--verified", "na",
            "--t-val", "300.0").returncode, 0)
        self.assertEqual(self.adjudicate(
            "--window", "0", "--t-val-a", "300.0", "--t-s", "295.0", "--t-s-source", "annotation",
            "--verified", "yes", "--t-val", "295.0").returncode, 0)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)

        # an earlier row that holds neither the boundary of its time nor the final one
        row = {"event": "adjudicate", "sample_id": "q10", "iteration": 1, "window": 0,
               "t_val_a": 300.0, "source": "semiblind.1.json"}
        self.write_log({**row, "t_s": None, "verified": "na", "t_val": 298.0},
                       {**row, "t_s": 295.0, "t_s_source": "annotation", "verified": "yes",
                        "t_val": 295.0}, video="v2")
        result = self.run_for_video("v2", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("line 1: q10, round 1, window 0: t_val 298.0 but the earliest of t_val_a "
                      "and the t_s verified yes is 300.0 after this row and 295.0 at the end",
                      result.stderr)
        self.assertNotIn("line 2", result.stderr)

    def test_a_harder_route_leaves_t_val_at_t_val_a(self):
        self.assertEqual(self.adjudicate(
            "--window", "0", "--t-val-a", "704.0", "--t-s", "690.0", "--t-s-source", "full_sample",
            "--verified", "harder", "--t-val", "690.0").returncode, 0)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("earliest of t_val_a and the t_s verified yes is 704.0", result.stderr)

    def test_old_adjudications_without_a_window_are_read_by_the_old_rules(self):
        self.write_log(
            {"event": "adjudicate", "sample_id": "q10", "iteration": 3, "t_val_a": 704.0,
             "t_s": 690.0, "verified": "yes", "t_val": 704.0, "source": "semiblind.3.json"},
            {"event": "adjudicate", "sample_id": "q11", "iteration": 1, "t_val_a": 800.0,
             "t_s": 790.0, "verified": "na", "t_val": 800.0, "source": "semiblind.1.json"},
            # two windows of one sample and round, logged before --window existed
            {"event": "adjudicate", "sample_id": "q12", "iteration": 2, "t_val_a": 90.0,
             "t_s": None, "verified": "na", "t_val": 90.0, "source": "semiblind.2.json"},
            {"event": "adjudicate", "sample_id": "q12", "iteration": 2, "t_val_a": 85.0,
             "t_s": None, "verified": "na", "t_val": 85.0, "source": "semiblind.2.json"},
        )
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("line 1: verified=yes but t_val != t_s", result.stderr)
        self.assertIn("line 2: t_s lies before t_val_a", result.stderr)
        self.assertNotIn("line 3", result.stderr)
        self.assertNotIn("line 4", result.stderr)

    def test_check_accepts_an_adjudication_with_no_answer_and_no_proposal(self):
        self.assertEqual(self.adjudicate("--window", "0", "--verified", "na").returncode, 0)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)

    def spawn(self, agent, sample_id, role, video="video-id", workspace=None):
        if workspace is None:
            workspace = self.workspace(agent, sample_id, role)
        return self.run_for_video(
            video, "spawn", "--agent", agent, "--sample-id", sample_id, "--role", role,
            "--iteration", "1", "--model", "local", "--reasoning-effort", "default",
            "--workspace", str(workspace),
        )

    def finish(self, agent, *args, video="video-id"):
        return self.run_for_video(video, "finish", "--agent", agent, "--status", "completed",
                                  "--summary", "ok", *args)

    def test_check_accepts_a_balanced_log(self):
        self.assertEqual(self.spawn("agent-1", "sample-q01", "probe_text").returncode, 0)
        self.assertEqual(self.finish("agent-1", "--artifact", "probe_text.1.json").returncode, 0)

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 launches, 1 finishes, 0 sample edits", result.stdout)

    def probe_file(self, sample_id, name, valid=True):
        sys.path.insert(0, str(ROOT / "schema"))
        import review  # noqa: E402
        answer = review.ProbeAnswer(
            checklist_version=review.CHECKLIST_VERSION, sample_id=sample_id, role="probe_text",
            iteration=1, model="local", date="2026-10-13", workspace="ws",
            budget=review.Budget(frames_viewed=0), answer="an answer", basis="lines 1-2",
            confidence="high").model_dump(mode="json")
        if not valid:
            del answer["answer"]
        path = self.log_root / "data" / "reviews" / "video-id" / sample_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(answer), encoding="utf-8")
        return path

    def test_open_tells_a_saved_review_from_a_running_agent(self):
        self.assertEqual(self.spawn("q01_text", "sample-q01", "probe_text").returncode, 0)
        self.assertEqual(self.spawn("q02_text", "sample-q02", "probe_text").returncode, 0)
        self.assertEqual(self.spawn("q03_text", "sample-q03", "probe_text").returncode, 0)
        self.probe_file("sample-q01", "probe_text.1.json")
        self.probe_file("sample-q02", "probe_text.1.json", valid=False)

        result = self.run_cli("open")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("open launches: 3", result.stdout)
        self.assertRegex(result.stdout, r"q01_text .*saved and passes --check: "
                                        r"data/reviews/video-id/sample-q01/probe_text\.1\.json")
        self.assertRegex(result.stdout, r"q02_text .*does not pass --check yet")
        self.assertRegex(result.stdout, r"q03_text .*no review file yet")
        self.assertIn("record the finish with --artifact", result.stdout)

    def test_open_ignores_a_file_older_than_the_launch_and_finished_launches(self):
        stale = self.probe_file("sample-q01", "probe_text.1.json")
        hour_ago = stale.stat().st_mtime - 3600
        os.utime(stale, (hour_ago, hour_ago))
        self.assertEqual(self.spawn("q01_text", "sample-q01", "probe_text").returncode, 0)
        self.assertEqual(self.spawn("q02_text", "sample-q02", "probe_text").returncode, 0)
        self.assertEqual(self.finish("q02_text").returncode, 0)

        result = self.run_cli("open")

        self.assertIn("open launches: 1", result.stdout)
        self.assertRegex(result.stdout, r"q01_text .*no review file yet")
        self.assertNotIn("q02_text", result.stdout)

    def test_open_finds_the_file_of_a_repeat(self):
        self.assertEqual(self.spawn("q01_text_r1b", "sample-q01", "probe_text").returncode, 0)
        self.probe_file("sample-q01", "probe_text.1b.json")

        result = self.run_cli("open")

        self.assertRegex(result.stdout, r"q01_text_r1b .*sample-q01/probe_text\.1b\.json")

    def test_a_note_naming_the_record_file_relative_to_the_repository_is_read(self):
        ws = self.workspace("q01_text", "sample-q01", "probe_text")
        note_path = Path(str(ws) + ".inputs.json")
        note = json.loads(note_path.read_text(encoding="utf-8"))
        note["annotations"] = "data/annotations/video-id.jsonl"
        note_path.write_text(json.dumps(note), encoding="utf-8")

        self.assertEqual(self.spawn("q01_text", "sample-q01", "probe_text", workspace=ws).returncode, 0)
        self.assertEqual(self.finish("q01_text").returncode, 0)
        result = self.run_cli("check", "--final")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_events()[0]["annotations"], "data/annotations/video-id.jsonl")

    def test_check_rejects_a_launch_without_finish(self):
        self.assertEqual(self.spawn("agent-1", "sample-q01", "probe_text").returncode, 0)

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("launch without finish: agent-1", result.stderr)

    def test_finish_refuses_a_name_with_no_open_launch(self):
        self.assertEqual(self.spawn("q03_probe_text_r1", "sample-q03", "probe_text").returncode, 0)

        result = self.finish("019a2f-thread-id")

        self.assertEqual(result.returncode, 2)
        self.assertIn("not under a thread id", result.stderr)
        self.assertIn("Open launches: q03_probe_text_r1", result.stderr)
        self.assertEqual(len(self.read_events()), 1)

    def test_check_rejects_finish_without_launch_in_an_old_log(self):
        self.write_log({"event": "finish", "agent": "agent-1", "status": "failed",
                        "summary": "The reviewer process failed before writing an artifact."})

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("finish without launch: agent-1", result.stderr)

    def test_a_relaunch_under_the_same_name_needs_a_note(self):
        self.assertEqual(self.spawn("agent-1", "sample-q01", "probe_text").returncode, 0)
        second = self.spawn("agent-1", "sample-q01", "probe_text")
        self.assertEqual(second.returncode, 2)
        self.assertIn("is still open", second.stderr)

        self.assertEqual(self.run_cli(
            "note", "--agent", "agent-1", "--text", "First start hit the thread limit; relaunched.",
        ).returncode, 0)
        self.assertEqual(self.spawn("agent-1", "sample-q01", "probe_text").returncode, 0)
        self.assertEqual(self.finish("agent-1").returncode, 0)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_rejects_a_second_active_launch_in_an_old_log(self):
        launch = {"event": "spawn", "agent": "agent-1", "sample_id": "sample-q01",
                  "role": "probe_text", "iteration": 1}
        self.write_log(launch, launch)

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate active launch: agent-1", result.stderr)

        # a note documents the relaunch (5.1)
        self.write_log({"event": "note", "agent": "agent-1", "text": "relaunched after HTTP 429"},
                       {"event": "finish", "agent": "agent-1", "status": "completed",
                        "summary": "ok"})
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_note_documents_an_unmatched_finish_or_launch(self):
        self.assertEqual(self.run_cli(
            "note", "--agent", "sb_q02_b", "--refers-to", "line 1",
            "--text", "spawn of the relaunch was never written; the artifact exists.",
        ).returncode, 0)
        self.assertEqual(self.finish("sb_q02_b").returncode, 0)
        self.assertEqual(self.spawn("sb_q07", "sample-q07", "semiblind").returncode, 0)
        self.assertEqual(self.run_cli("check").returncode, 1)

        self.assertEqual(self.run_cli(
            "note", "--agent", "sb_q07", "--text", "fate unknown after the session was cut.",
        ).returncode, 0)

        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 notes", result.stdout)
        events = self.read_events()
        self.assertEqual(events[0]["event"], "note")
        self.assertEqual(events[0]["refers_to"], "line 1")

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
        self.assertEqual(self.finish("fs_q04").returncode, 0)
        self.assertEqual(self.run_cli("check", "--final").returncode, 1)

        # the window review is logged per window, as the real logs do
        for agent, role in (("fs_q03", "full_sample"), ("fw0_q03", "full_window0")):
            self.assertEqual(self.spawn(agent, "sample-q03", role).returncode, 0)
            self.assertEqual(self.finish(agent).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pending", result.stdout)

    def test_a_rejected_sample_owes_no_reruns(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "wording",
            "--changes", "v2 of the question.", "--source", "coordinator.2.md",
        ).returncode, 0)
        self.assertEqual(self.run_cli("check", "--final").returncode, 1)
        records = self.records()
        records["sample-q03"]["validation"]["status"] = "rejected"
        self.write_records(*records.values())
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_boundary_edit_with_a_window_is_settled_only_by_that_window(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "boundary", "--window", "2",
            "--changes", "t_start of trigger 2 -> 296.0.", "--source", "full_window2.11.json",
        ).returncode, 0)
        self.assertEqual(self.read_events()[-1]["window"], 2)
        # a review of another window of the same sample does not settle the debt
        self.assertEqual(self.spawn("fw3", "sample-q03", "full_window3").returncode, 0)
        self.finish("fw3")
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not followed by full_window2", result.stderr)
        self.assertEqual(self.spawn("fw2", "sample-q03", "full_window2").returncode, 0)
        self.finish("fw2")
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
        self.assertIn("applies to --kind boundary, nudge, rubric or metadata", stray.stderr)
        self.assertFalse((self.log_root / "data" / "reviews" / "video-id" /
                          "coordinator.log").exists())

    def test_a_span_edit_waits_for_the_adjudication_of_its_stretch(self):
        early = self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "metadata", "--window", "1",
            "--span", "--changes", "evidence_span of trigger 1 -> [198.0, 201.0].",
            "--source", "full_window1.2.json",
        )
        self.assertEqual(early.returncode, 2)
        self.assertIn("checked against t_val", early.stderr)
        nudge = self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "nudge", "--window", "1",
            "--span", "--changes", "x", "--source", "y",
        )
        self.assertEqual(nudge.returncode, 2)
        self.assertIn("never a nudge", nudge.stderr)

        self.assertEqual(self.run_cli(
            "adjudicate", "--sample-id", "sample-q03", "--iteration", "2", "--window", "1",
            "--t-val-a", "201.0", "--verified", "na", "--t-val", "201.0",
            "--source", "semiblind.2.json",
        ).returncode, 0)
        late = self.run_cli(
            "sample-edit", "--sample-id", "sample-q03", "--kind", "metadata", "--window", "1",
            "--span", "--changes", "evidence_span of trigger 1 -> [198.0, 201.0].",
            "--source", "full_window1.2.json",
        )
        self.assertEqual(late.returncode, 0, late.stderr)
        self.assertTrue(self.read_events()[-1]["span"])
        self.assertEqual(self.run_cli("check", "--final").returncode, 0)

        # an old log with the order reversed
        self.write_log({"event": "sample_edit", "sample_id": "sample-q04", "kind": "metadata",
                        "window": 0, "span": True, "changes": "x", "source": "y"}, video="v2")
        result = self.run_for_video("v2", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("edited before its stretch was adjudicated", result.stderr)

    def test_a_rubric_edit_with_a_window_is_settled_by_that_window_and_full_sample(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q16", "--kind", "rubric", "--window", "0",
            "--changes", "R0 now demands the 1⁴/4! form.", "--source", "full_sample.3.json",
        ).returncode, 0)
        self.assertEqual(self.spawn("fs", "sample-q16", "full_sample").returncode, 0)
        self.assertEqual(self.spawn("fw1", "sample-q16", "full_window1").returncode, 0)
        for agent in ("fs", "fw1"):
            self.finish(agent)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not followed by full_window0", result.stderr)
        self.assertEqual(self.spawn("fw0", "sample-q16", "full_window0").returncode, 0)
        self.finish("fw0")
        self.assertEqual(self.run_cli("check", "--final").returncode, 0)

    def test_a_wording_edit_requires_the_whole_cycle(self):
        self.assertEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q02", "--kind", "wording",
            "--changes", "Referent fixed: 'the blue target function now on the screen'.",
            "--source", "coordinator.5.md",
        ).returncode, 0)
        for agent, role in (("sb", "semiblind"), ("pt", "probe_text"), ("pv", "probe_vision"),
                            ("pf", "probe_frame0"), ("fs", "full_sample")):
            self.assertEqual(self.spawn(agent, "sample-q02", role).returncode, 0, role)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not followed by full_window", result.stderr)
        self.assertNotIn("probe_", result.stderr)
        self.assertEqual(self.spawn("fw2", "sample-q02", "full_window2").returncode, 0)
        for agent in ("sb", "pt", "pv", "pf", "fs", "fw2"):
            self.finish(agent)
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

    def test_spawn_records_the_prompt_and_the_material_its_subagent_reads(self):
        self.assertEqual(self.spawn("pf1", "sample-q01", "probe_frame1").returncode, 0)

        event = self.read_events()[0]

        prompt = ROOT / "docs" / "prompts" / "probe_frame.md"
        checklist = ROOT / "docs" / "annotation_checklist.md"
        self.assertEqual(event["prompt"], "docs/prompts/probe_frame.md")
        self.assertEqual(event["prompt_sha"], hashlib.sha256(prompt.read_bytes()).hexdigest())
        self.assertEqual(event["checklist_sha"],
                         hashlib.sha256(checklist.read_bytes()).hexdigest())
        self.assertRegex(event["git_head"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(event["prompts_dirty"], bool)
        self.assertEqual(event["window"], 1)
        self.assertEqual(event["inputs"], {"frame": 205.0})
        self.assertEqual(event["record_sha"],
                         review_inputs.record_sha(self.records()["sample-q01"]))

    def test_spawn_refuses_a_bare_indexed_role_and_unknown_roles(self):
        for role in ("full_window", "probe_frame"):
            bare = self.spawn("fw", "sample-q01", role, workspace=self.log_root / "none")
            self.assertEqual(bare.returncode, 2, role)
            self.assertIn("needs the window index", bare.stderr)
        for role in ("full", "semiblind2", "reviewer"):
            result = self.spawn("x", "sample-q01", role, workspace=self.log_root / "none")
            self.assertEqual(result.returncode, 2, role)
            self.assertIn("unknown --role", result.stderr)
        self.assertFalse((self.log_root / "data" / "reviews" / "video-id" / "coordinator.log").exists())

    def test_spawn_refuses_a_workspace_that_does_not_match_the_record(self):
        missing = self.spawn("pt", "sample-q01", "probe_text", workspace=self.log_root / "bare")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--sample-id <ID>", missing.stderr)

        ws = self.workspace("pf", "sample-q01", "probe_frame1")
        wrong_window = self.spawn("pf", "sample-q01", "probe_frame2", workspace=ws)
        self.assertEqual(wrong_window.returncode, 2)
        self.assertIn("cut at window 1", wrong_window.stderr)
        wrong_sample = self.spawn("pf", "sample-q02", "probe_frame1", workspace=ws)
        self.assertEqual(wrong_sample.returncode, 2)
        self.assertIn("prepared for sample-q01", wrong_sample.stderr)

        records = self.records()
        records["sample-q01"]["triggers"][1]["t_start"] = 196.0
        self.write_records(*records.values())
        changed = self.spawn("pf", "sample-q01", "probe_frame1", workspace=ws)
        self.assertEqual(changed.returncode, 2)
        self.assertIn("has changed since", changed.stderr)

    def test_a_probe_whose_window_moved_is_stale_until_run_again(self):
        self.assertEqual(self.spawn("pf_r1", "sample-q05", "probe_frame1").returncode, 0)
        self.assertEqual(self.spawn("pt_r1", "sample-q05", "probe_text").returncode, 0)
        records = self.records()
        records["sample-q05"]["triggers"][1]["t_start"] = 190.0
        self.write_records(*records.values())

        late = self.finish("pf_r1")
        self.assertEqual(late.returncode, 0)
        self.assertIn("stale", late.stderr)
        self.assertIn("frame=205.0, the record now gives frame=200.0", late.stderr)
        self.assertIn("stale_inputs", self.read_events()[-1])
        self.assertEqual(self.finish("pt_r1").returncode, 0)

        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("probe_frame1 of sample-q05 (pf_r1) is stale", result.stderr)
        self.assertNotIn("probe_text", result.stderr)  # t_end of the last window did not move

        self.assertEqual(self.spawn("pf_r2", "sample-q05", "probe_frame1").returncode, 0)
        self.assertEqual(self.finish("pf_r2").returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_probe_prepared_from_a_part_is_checked_against_the_merged_file(self):
        part = self.annotations.parent / "partial" / "video-id.a.jsonl"
        part.parent.mkdir()
        self.annotations.rename(part)
        self.annotations = part
        self.assertEqual(self.spawn("pf_r1", "sample-q05", "probe_frame1").returncode, 0)
        self.assertEqual(self.finish("pf_r1").returncode, 0)

        merged = part.parent.parent / "video-id.jsonl"
        part.rename(merged)
        self.annotations = merged
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

        records = self.records()
        records["sample-q05"]["triggers"][1]["t_start"] = 190.0
        self.write_records(*records.values())
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("it ran on frame=205.0, the record now gives frame=200.0", result.stderr)

    def test_finish_records_the_artifact_and_warns_on_a_mismatch(self):
        artifact = self.log_root / "full_window2.3.json"
        artifact.write_text(json.dumps({"role": "full_window", "sample_id": "sample-q04",
                                        "verdict": "FIX_QUESTION"}), encoding="utf-8")
        self.assertEqual(self.spawn("fw2", "sample-q03", "full_window2").returncode, 0)

        result = self.finish("fw2", "--artifact", str(artifact))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("does not match the launch", result.stderr)
        event = self.read_events()[-1]
        self.assertEqual(event["artifact_verdict"], "FIX_QUESTION")
        self.assertEqual(event["artifact_role"], "full_window")
        self.assertIn("sample sample-q04", event["artifact_mismatch"])


if __name__ == "__main__":
    unittest.main()
