import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "coordinator_log.py"
sys.path.insert(0, str(ROOT / "tools"))
import review_inputs  # noqa: E402


def record(sample_id, windows=((100.0, 110.0), (200.0, 210.0), (300.0, 310.0), (400.0, 410.0))):
    return {"id": sample_id, "validation": {"status": "draft"},
            "triggers": [{"idx": i, "required": True, "t_start": a, "t_end": b}
                         for i, (a, b) in enumerate(windows)]}


class FakeJudge(BaseHTTPRequestHandler):
    """An OpenAI-compatible server that credits the items listed in server.credit: True
    credits every item, False none, a set the judged item ids (i1, i2, ...) it names."""

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][-1]["content"]
        ids = re.search(r"Item ids: (.*)$", prompt).group(1).split(", ")
        credit = self.server.credit
        if isinstance(credit, list):  # one verdict per request, in turn
            with self.server.lock:
                credit = credit[self.server.calls % len(credit)]
                self.server.calls += 1
        items = [{"id": i, "correct": [1] if credit is True or (credit and i in credit) else [],
                  "wrong": []} for i in ids]
        answer = {"id": "x", "object": "chat.completion", "created": 0, "model": "local",
                  "choices": [{"index": 0, "finish_reason": "stop",
                               "message": {"role": "assistant",
                                           "content": json.dumps({"items": items})}}]}
        data = json.dumps(answer).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class CoordinatorLogCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log_root = Path(self.tmp.name)
        self.annotations = self.log_root / "data" / "annotations" / "video-id.jsonl"
        self.annotations.parent.mkdir(parents=True)
        self.write_records(*(record(f"sample-q{n:02d}") for n in range(1, 18)))
        self.walked = {}  # the trajectories the adjudicate helper wrote: file -> window -> moments

    def write_records(self, *records):
        self.annotations.write_text("".join(json.dumps(r) + "\n" for r in records),
                                    encoding="utf-8")

    def records(self):
        return review_inputs.read_records(self.annotations)

    def workspace(self, agent, sample_id, role, until=95.0):
        """A workspace note as prepare_review_workspace.py --sample-id leaves it."""
        base = role.rstrip("0123456789")
        window = int(role[len(base):]) if role != base else None
        if base == "semiblind":
            window = 0
        current = self.records()[sample_id]
        ws = self.log_root / ".review_ws" / "video-id" / sample_id / agent
        ws.mkdir(parents=True, exist_ok=True)
        inputs = (review_inputs.derive_inputs(base, current, window, until=until, duration=1000.0)
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

        edit = self.edit("sample-q05", "triggers[0].t_start=90.0", source="full_sample.4.json")
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
        self.trajectory([704.0], name="semiblind.3.json")
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
        self.walk(args, video=video)
        return self.run_for_video(video, "adjudicate", "--sample-id", "sample-q10",
                                  "--iteration", "1", "--source", "semiblind.1.json", *args)

    def walk(self, args, video="video-id", sample="sample-q10", name="semiblind.1.json"):
        """Unless the test wrote the semi-blind review itself, give it the stretch of the row's
        window, with an answer at the row's --t-val-a: stage A is read from a trajectory."""
        path = self.log_root / "data" / "reviews" / video / sample / name
        if path.exists() and path not in self.walked:
            return
        options = dict(zip(args[::2], args[1::2]))
        if "--window" not in options or "--correction" in options:
            return
        moments = self.walked.setdefault(path, {}).setdefault(int(options["--window"]), set())
        if "--t-val-a" in options:
            moments.add(float(options["--t-val-a"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scans": [
            {"idx": idx, "candidates": [{"t": t} for t in sorted(found)]}
            for idx, found in sorted(self.walked[path].items())]}), encoding="utf-8")

    def edit(self, sample_id, *assignments, source="coordinator.1.md", video="video-id"):
        """An edit of a record through the tool: sample-edit --set."""
        sets = [part for assignment in assignments for part in ("--set", assignment)]
        return self.run_for_video(video, "sample-edit", "--sample-id", sample_id, *sets,
                                  "--source", source)

    def to_partial(self):
        """Move the records where an open video keeps them: data/annotations/partial/."""
        part = self.annotations.parent / "partial" / "video-id.full.jsonl"
        part.parent.mkdir(exist_ok=True)
        self.annotations.rename(part)
        self.annotations = part

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
        # the tool derives t_val, and a later row takes the stretch's t_val_a
        rows = [("full_sample", "690.0", "harder", "704.0"), ("annotation", "695.0", "yes", None),
                ("full_window0", "698.0", "yes", None)]
        for source, t_s, verified, t_val_a in rows:
            result = self.adjudicate(
                "--window", "0", *(["--t-val-a", t_val_a] if t_val_a else []), "--t-s", t_s,
                "--t-s-source", source, "--verified", verified)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(e["t_val_a"], e["t_val"]) for e in self.read_events()],
                         [(704.0, 704.0), (704.0, 695.0), (704.0, 695.0)])
        self.assertEqual(self.read_events()[0]["t_s_source"], "full_sample")

        # a t_val that does not follow from the rows is refused before it is written
        self.assertEqual(self.adjudicate(
            "--window", "1", "--t-val-a", "704.0", "--t-s", "695.0", "--t-s-source", "annotation",
            "--verified", "yes", "--t-val", "695.0", video="v2").returncode, 0)
        result = self.adjudicate(
            "--window", "1", "--t-s", "690.0", "--t-s-source", "full_sample",
            "--verified", "yes", "--t-val", "695.0", video="v2")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not logged: nothing was written", result.stderr)
        self.assertIn("--t-val 695.0, but the boundary after this row is 690.0", result.stderr)
        self.assertIn("695.0 (line 1), 690.0 (this row)", result.stderr)
        self.assertEqual(self.run_for_video("v2", "check").returncode, 0)

    def test_a_row_is_weighed_with_its_stretch_before_it_is_written(self):
        self.assertEqual(self.adjudicate("--window", "0", "--t-val-a", "300.0",
                                         "--verified", "na").returncode, 0)
        disagree = self.adjudicate("--window", "0", "--t-val-a", "290.0", "--verified", "na")
        self.assertEqual(disagree.returncode, 2)
        self.assertIn("t_val_a 290.0 disagrees with 300.0", disagree.stderr)
        self.assertIn("--correction", disagree.stderr)
        # a stretch check already rejects cannot be extended, only corrected
        row = {"event": "adjudicate", "sample_id": "sample-q10", "iteration": 1, "window": 0,
               "t_val_a": None, "t_s": None, "t_s_source": None, "verified": "na",
               "source": "semiblind.1.json"}
        self.write_log({**row, "t_val": 73.0}, video="v2")
        further = self.adjudicate("--window", "0", "--t-s", "60.0", "--t-s-source",
                                  "annotation", "--verified", "no", video="v2")
        self.assertEqual(further.returncode, 2)
        self.assertIn("already fails check, and a further row cannot repair it (line 1: "
                      "sample-q10, round 1, window 0: t_val 73.0 but", further.stderr)
        self.assertEqual(further.stderr.count("Correcting a stretch"), 1)
        self.assertIn("Log the stretch anew", further.stderr)
        self.assertEqual(len(self.read_events()), 1)

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

    def trajectory(self, *scans, video="video-id", sample="sample-q10", name="semiblind.1.json"):
        """A semi-blind review with the answers at these moments, one list per window."""
        path = self.log_root / "data" / "reviews" / video / sample / name
        self.walked.pop(path, None)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scans": [
            {"idx": idx, "candidates": [{"t": t, "answer": "an answer"} for t in moments]}
            for idx, moments in enumerate(scans)]}), encoding="utf-8")

    def test_a_correction_opens_the_stretch_anew(self):
        self.trajectory([573.2, 582.9, 587.0])
        self.assertEqual(self.adjudicate(
            "--window", "0", "--t-val-a", "587.0", "--verified", "na",
            "--t-val", "587.0").returncode, 0)
        # a stretch that already disagrees, from a log of the time before the refusal
        self.write_log({"event": "adjudicate", "sample_id": "sample-q10", "iteration": 1,
                        "window": 0, "t_val_a": 582.9, "t_s": None, "t_s_source": None,
                        "verified": "na", "t_val": 582.9, "source": "semiblind.1.json"})
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("rows disagree on t_val_a", result.stderr)
        self.assertIn("--correction", result.stderr)

        corrected = self.adjudicate(
            "--window", "0", "--t-val-a", "582.9", "--verified", "na", "--t-val", "582.9",
            "--correction", "line 1 missed the answer at 582.9")
        self.assertEqual(corrected.returncode, 0, corrected.stderr)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("lines 1, 2 superseded: line 1 missed the answer at 582.9", result.stdout)
        self.assertIn("1 corrected stretches", result.stdout)

        # a correction never makes the boundary looser: not later than an answer logged before,
        # not null where an answer was logged; that is for the next round of review
        for t_val_a in ("587.0", None):
            args = ["--t-val-a", t_val_a, "--t-val", t_val_a] if t_val_a else []
            looser = self.adjudicate("--window", "0", *args, "--verified", "na",
                                     "--correction", "582.9 misses item 2")
            self.assertEqual(looser.returncode, 2, t_val_a)
            self.assertIn("stricter, never looser", looser.stderr, t_val_a)
        self.assertEqual(self.adjudicate(
            "--window", "0", "--t-val-a", "573.2", "--verified", "na", "--t-val", "573.2",
            "--correction", "573.2 already passes").returncode, 0)
        self.assertEqual(self.run_cli("check").returncode, 0)

        # a stretch that found no answer may be corrected to none: no trajectory to weigh
        row = {"event": "adjudicate", "sample_id": "sample-q10", "iteration": 1, "window": 0,
               "t_val_a": None, "t_s": None, "t_s_source": None, "verified": "na",
               "source": "full_window0.1.json"}
        self.write_log({**row, "t_val": 73.0}, video="v2")
        other = self.run_for_video(
            "v2", "adjudicate", "--sample-id", "sample-q10", "--iteration", "1", "--window", "0",
            "--verified", "na", "--source", "full_window0.1.json", "--correction", "copy error")
        self.assertEqual(other.returncode, 0, other.stderr)
        result = self.run_for_video("v2", "check")
        self.assertEqual(result.returncode, 0, result.stderr)

        # none for a value logged off the trajectory, after its last answer: read from the
        # trajectory the earlier rows cite
        self.trajectory([573.2, 582.9, 587.0], video="v3")
        self.write_log({**row, "t_val_a": 590.0, "t_val": 590.0, "source": "semiblind.1.json"},
                       video="v3")
        elsewhere = self.run_for_video(
            "v3", "adjudicate", "--sample-id", "sample-q10", "--iteration", "1", "--window", "0",
            "--verified", "na", "--source", "semiblind.2.json", "--correction", "590.0 is q01's")
        self.assertEqual(elsewhere.returncode, 2)
        self.assertIn("the earlier rows of this stretch cite semiblind.1.json", elsewhere.stderr)
        none = self.adjudicate("--window", "0", "--verified", "na", "--correction",
                               "590.0 is q01's", video="v3")
        self.assertEqual(none.returncode, 0, none.stderr)
        self.assertIn("line 1 logged t_val_a 590.0, which is no answer", none.stdout)

    def test_a_correction_takes_its_t_val_a_from_the_trajectory(self):
        self.trajectory([573.2, 582.9], [590.0])
        self.assertEqual(self.adjudicate(
            "--window", "0", "--t-val-a", "582.9", "--verified", "na",
            "--t-val", "582.9").returncode, 0)
        refusals = {
            # where the sighted reviewers place the answer: a t_s, for stage C
            "576.0": "moment of no answer in the stretch of window 0 of semiblind.1.json",
            # an answer of the next window's stretch is not this window's
            "590.0": "moment of no answer",
        }
        for t_val_a, message in refusals.items():
            result = self.adjudicate("--window", "0", "--t-val-a", t_val_a, "--verified", "na",
                                     "--t-val", t_val_a, "--correction", "re-read")
            self.assertEqual(result.returncode, 2, t_val_a)
            self.assertIn(message, result.stderr, t_val_a)
        result = self.run_for_video(
            "video-id", "adjudicate", "--sample-id", "sample-q10", "--iteration", "1",
            "--window", "0", "--t-val-a", "573.2", "--verified", "na", "--t-val", "573.2",
            "--source", "coordinator.1.md", "--correction", "re-read")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cites the semi-blind review", result.stderr)
        nothing = self.adjudicate("--window", "1", "--t-val-a", "590.0", "--verified", "na",
                                  "--t-val", "590.0", "--correction", "re-read")
        self.assertEqual(nothing.returncode, 2)
        self.assertIn("nothing to correct", nothing.stderr)
        blank = self.adjudicate("--window", "0", "--t-val-a", "582.9", "--verified", "na",
                                "--t-val", "582.9", "--correction", " ")
        self.assertEqual(blank.returncode, 2)
        self.assertIn("says what the earlier rows got wrong", blank.stderr)
        self.assertEqual(len(self.read_events()), 1)

        # nor is an answer of an earlier window's stretch: each window has its own boundary
        self.assertEqual(self.adjudicate("--window", "1", "--t-val-a", "590.0", "--verified",
                                         "na", "--t-val", "590.0").returncode, 0)
        result = self.adjudicate("--window", "1", "--t-val-a", "582.9", "--verified", "na",
                                 "--t-val", "582.9", "--correction", "re-read")
        self.assertEqual(result.returncode, 2)
        self.assertIn("moment of no answer in the stretch of window 1", result.stderr)
        other = self.run_for_video(
            "video-id", "adjudicate", "--sample-id", "sample-q10", "--iteration", "1",
            "--window", "1", "--t-val-a", "590.0", "--verified", "na", "--t-val", "590.0",
            "--source", "semiblind.2.json", "--correction", "re-read")
        self.assertEqual(other.returncode, 2)
        self.assertIn("--source semiblind.2.json, but the earlier rows of this stretch cite "
                      "semiblind.1.json", other.stderr)
        # a review that cannot be read gives stage A nothing, in a first row or a correction
        unread = ["--t-val-a", "500.0", "--source", "semiblind.2.json"]
        self.write_log({"event": "adjudicate", "sample_id": "sample-q10", "iteration": 1,
                        "window": 2, "t_val_a": 500.0, "t_s": None, "t_s_source": None,
                        "verified": "na", "t_val": 500.0, "source": "semiblind.2.json"})
        for args in ([*unread, "--window", "3"], [*unread, "--window", "2", "--correction", "x"]):
            result = self.run_for_video(
                "video-id", "adjudicate", "--sample-id", "sample-q10", "--iteration", "1",
                "--verified", "na", *args)
            self.assertEqual(result.returncode, 2)
            self.assertIn("semiblind.2.json cannot be read", result.stderr)

        # a hand-written correction is held to the same rule by check
        row = {"event": "adjudicate", "sample_id": "sample-q10", "iteration": 1, "window": 0,
               "t_s": None, "t_s_source": None, "verified": "na", "source": "semiblind.1.json"}
        self.write_log({**row, "t_val_a": 582.9, "t_val": 582.9},
                       {**row, "t_val_a": 576.0, "t_val": 576.0, "correction": "re-read"},
                       video="v2")
        self.trajectory([573.2, 582.9], video="v2")
        result = self.run_for_video("v2", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("line 2: sample-q10, round 1, window 0: t_val_a 576.0 is the moment of no "
                      "answer", result.stderr)

    def test_a_correction_keeps_every_sighted_proposal_and_its_outcome(self):
        self.trajectory([582.9, 600.0])
        self.assertEqual(self.adjudicate(
            "--window", "0", "--t-val-a", "600.0", "--t-s", "590.0", "--t-s-source", "full_sample",
            "--verified", "no", "--t-val", "600.0").returncode, 0)
        corrected = self.adjudicate(
            "--window", "0", "--t-val-a", "582.9", "--verified", "na", "--t-val", "582.9",
            "--correction", "line 1 missed the answer at 582.9")
        self.assertEqual(corrected.returncode, 0, corrected.stderr)
        owed = ("log again the t_s 590.0 (full_sample) of line 1 with the corrected t_val_a: "
                "--t-s 590.0 --t-s-source full_sample --verified no")
        self.assertIn(owed, corrected.stdout)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"pending correction: line 2: sample-q10, round 1, window 0: {owed}",
                      result.stderr)
        self.assertIn("1 rows owed by corrections", result.stdout)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn(owed, result.stderr)

        # logged again with what its probe did not measure: refused before it is written
        for outcome in ("na", "yes"):
            changed = self.adjudicate(
                "--window", "0", "--t-s", "590.0", "--t-s-source", "full_sample",
                "--verified", outcome)
            self.assertEqual(changed.returncode, 2, outcome)
            self.assertIn(f"this row: sample-q10, round 1, window 0: the t_s 590.0 (full_sample) "
                          f"was verified no (line 1), and this row says {outcome}", changed.stderr)
        self.assertEqual(len(self.read_events()), 2)
        again = self.adjudicate("--window", "0", "--t-s", "590.0", "--t-s-source", "full_sample",
                                "--verified", "no")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("owed", again.stdout)
        self.assertNotIn("pending correction", self.run_cli("check").stderr)

        # logged again as measured
        row = {"event": "adjudicate", "sample_id": "sample-q10", "iteration": 1, "window": 0,
               "source": "semiblind.1.json"}
        self.write_log({**row, "t_val_a": 600.0, "t_s": 590.0, "t_s_source": "full_sample",
                        "verified": "no", "t_val": 600.0},
                       {**row, "t_val_a": 582.9, "t_s": None, "t_s_source": None, "verified": "na",
                        "t_val": 582.9, "correction": "line 1 missed the answer at 582.9"},
                       {**row, "t_val_a": 582.9, "t_s": 590.0, "t_s_source": "full_sample",
                        "verified": "no", "t_val": 582.9}, video="v2")
        self.trajectory([582.9, 600.0], video="v2")
        result = self.run_for_video("v2", "check")
        self.assertEqual(result.returncode, 0, result.stderr)

        # an earlier t_val_a leaves the proposal where it was, and the rows after the
        # correction answer to check_adjudication as any other
        self.write_log({**row, "t_val_a": 600.0, "t_s": 590.0, "t_s_source": "full_sample",
                        "verified": "no", "t_val": 600.0},
                       {**row, "t_val_a": 582.9, "t_s": 570.0, "t_s_source": "annotation",
                        "verified": "na", "t_val": 582.9, "correction": "missed 582.9"},
                       {**row, "t_val_a": 582.9, "t_s": 590.0, "t_s_source": "full_sample",
                        "verified": "no", "t_val": 582.9}, video="v3")
        self.trajectory([582.9, 600.0], video="v3")
        result = self.run_for_video("v3", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("line 2: t_s lies before t_val_a", result.stderr)
        self.assertNotIn("line 1", result.stderr)

    def test_a_value_logged_off_the_trajectory_still_bounds_a_correction(self):
        # 576.0 is no answer: stage A reading the same trajectory would have put the boundary
        # at the first answer after it, so that answer bounds the correction
        self.trajectory([573.2, 582.9, 587.0])
        row = {"event": "adjudicate", "sample_id": "sample-q10", "iteration": 2, "window": 0,
               "t_s": None, "t_s_source": None, "verified": "na", "source": "semiblind.1.json"}
        self.write_log({**row, "t_val_a": 576.0, "t_val": 576.0})
        later = self.run_for_video(
            "video-id", "adjudicate", "--sample-id", "sample-q10", "--iteration", "2",
            "--window", "0", "--t-val-a", "587.0", "--verified", "na",
            "--source", "semiblind.1.json", "--correction", "576.0 is no answer")
        self.assertEqual(later.returncode, 2)
        self.assertIn("later than 582.9, the first answer at or after the 576.0", later.stderr)
        right = self.run_for_video(
            "video-id", "adjudicate", "--sample-id", "sample-q10", "--iteration", "2",
            "--window", "0", "--t-val-a", "582.9", "--verified", "na",
            "--source", "semiblind.1.json", "--correction", "576.0 is no answer")
        self.assertEqual(right.returncode, 0, right.stderr)
        # whether stage C was owed on the placement is the sighted reviewers' call, as in §6
        self.assertIn("line 1 logged t_val_a 576.0, which is no answer of the trajectory", right.stdout)
        self.assertIn("--t-s 576.0 --t-s-source <that reviewer>", right.stdout)

    def test_a_correction_is_not_weighed_against_a_stretch_the_review_lacks(self):
        # one scan over the whole sample: its answers are not window 1's stretch, and "no
        # answer there" must not read as "no answer"
        path = self.log_root / "data" / "reviews" / "video-id" / "sample-q10" / "semiblind.1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scans": [{"idx": 0, "t_from": 0.0, "t_to": 741.0,
                                               "candidates": [{"t": 588.0}, {"t": 680.0}]}]}),
                        encoding="utf-8")
        first = self.adjudicate("--window", "1", "--t-val-a", "588.0", "--verified", "na")
        self.assertEqual(first.returncode, 2)  # stage A is read from the window's own stretch
        self.assertIn("has no stretch of window 1 (its stretches: 0)", first.stderr)
        self.assertIn("run the semi-blind reviewer over that stretch first", first.stderr)
        self.write_log({"event": "adjudicate", "sample_id": "sample-q10", "iteration": 1,
                        "window": 1, "t_val_a": 588.0, "t_s": None, "t_s_source": None,
                        "verified": "na", "t_val": 588.0, "source": "semiblind.1.json"})
        for args in ([], ["--t-val-a", "680.0"]):
            result = self.adjudicate("--window", "1", *args, "--verified", "na",
                                     "--correction", "re-read")
            self.assertEqual(result.returncode, 2, args)
            self.assertIn("has no stretch of window 1 (its stretches: 0)", result.stderr)
            self.assertIn("settle it in the next round of review", result.stderr)
        # the legacy shape has no moments to weigh either
        path.write_text(json.dumps({"scans": [{"idx": 1, "candidates": [{"answer": "x"}]}]}),
                        encoding="utf-8")
        result = self.adjudicate("--window", "1", "--verified", "na", "--correction", "re-read")
        self.assertEqual(result.returncode, 2)
        self.assertIn("has no timed answers in its stretch of window 1", result.stderr)
        self.assertEqual(len(self.read_events()), 1)

    def test_a_correction_gives_an_outcome_only_to_a_measured_proposal(self):
        self.trajectory([582.9, 600.0])
        row = {"event": "adjudicate", "sample_id": "sample-q10", "iteration": 1, "window": 0,
               "t_val_a": 600.0, "t_s": 550.0, "t_s_source": "full_sample", "verified": "na",
               "t_val": 600.0, "source": "semiblind.1.json"}
        self.write_log(row)
        corrected = self.adjudicate("--window", "0", "--t-val-a", "582.9", "--verified", "na",
                                    "--correction", "missed 582.9")
        self.assertEqual(corrected.returncode, 0, corrected.stderr)
        self.assertIn("it lies before the corrected t_val_a, so run stage C at it first",
                      corrected.stdout)
        unmeasured = ("the t_s 550.0 gets the outcome no, but no probe_verify of sample-q10 "
                      "launched in round 1 at it (--until 550.0) has finished")
        result = self.adjudicate("--window", "0", "--t-s", "550.0", "--t-s-source",
                                 "full_sample", "--verified", "no")
        self.assertEqual(result.returncode, 2)
        self.assertIn(unmeasured, result.stderr)
        # a probe at another moment measured something else
        self.assertEqual(self.spawn("verify-1", "sample-q10", "probe_verify",
                                    until=560.0).returncode, 0)
        self.assertEqual(self.finish("verify-1").returncode, 0)
        result = self.adjudicate("--window", "0", "--t-s", "550.0", "--t-s-source",
                                 "full_sample", "--verified", "no")
        self.assertIn(unmeasured, result.stderr)
        self.assertEqual(self.spawn("verify-2", "sample-q10", "probe_verify",
                                    until=550.0).returncode, 0)
        self.assertEqual(self.finish("verify-2").returncode, 0)
        result = self.adjudicate("--window", "0", "--t-s", "550.0", "--t-s-source",
                                 "full_sample", "--verified", "no")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pending correction", result.stderr)

        # check holds a hand-written stretch to the same rule
        self.trajectory([582.9, 600.0], video="v2")
        self.write_log(row, {**row, "t_val_a": 582.9, "t_s": None, "t_s_source": None,
                             "t_val": 582.9, "correction": "missed 582.9"},
                       {**row, "t_val_a": 582.9, "verified": "no", "t_val": 582.9}, video="v2")
        result = self.run_for_video("v2", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"line 3: sample-q10, round 1, window 0: {unmeasured}", result.stderr)

    def test_a_tool_error_says_whether_the_row_was_written(self):
        import contextlib
        import io
        from unittest import mock
        import coordinator_log
        self.trajectory([300.0])
        args = ["video-id", "adjudicate", "--sample-id", "sample-q10", "--iteration", "1",
                "--window", "0", "--t-val-a", "300.0", "--verified", "na",
                "--source", "semiblind.1.json"]
        path = self.log_root / "data" / "reviews" / "video-id" / "coordinator.log"

        def failing(*_):
            raise KeyError("t_val_a")

        original = coordinator_log.append_event

        def write_then_fail(*arguments):
            original(*arguments)
            raise OSError("disk")

        for name, replacement, written in (("adjudicate_event", failing, False),
                                           ("append_event", write_then_fail, True)):
            stderr = io.StringIO()
            with mock.patch.object(coordinator_log, name, replacement), \
                    mock.patch.object(coordinator_log, "ROOT", self.log_root), \
                    contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
                code = coordinator_log.main(args)
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", stderr.getvalue())
            if written:
                self.assertIn("after it wrote its row", stderr.getvalue())
                self.assertIn("the row stands, do not log it again", stderr.getvalue())
                self.assertEqual(len(self.read_events()), 1)
            else:
                self.assertIn("not logged: `adjudicate` stopped on an error of its own "
                              "(KeyError: 't_val_a'). Nothing was written", stderr.getvalue())
                self.assertFalse(path.exists())

    def test_a_failure_of_a_command_that_writes_nothing_says_so(self):
        import contextlib
        import io
        from unittest import mock
        import coordinator_log
        stderr = io.StringIO()
        with mock.patch.object(coordinator_log, "validate_log", side_effect=KeyError("x")), \
                mock.patch.object(coordinator_log, "ROOT", self.log_root), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(coordinator_log.main(["video-id", "check"]), 2)
        self.assertIn("`check` stopped on an error of its own (KeyError: 'x'); it writes "
                      "nothing", stderr.getvalue())
        self.assertNotIn("not logged", stderr.getvalue())

    def test_a_row_after_a_cut_off_line_starts_a_line_of_its_own(self):
        path = self.log_root / "data" / "reviews" / "video-id" / "coordinator.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"ts":"2026-10-01T00:00:00+03:00","event":"note","text":"a"}\n'
                        '{"ts":"2026-10-01T00:00:00+03:00","event":"no', encoding="utf-8")
        self.assertEqual(self.run_cli("note", "--text", "tool problem: a cut-off line")
                         .returncode, 0)
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[2])["text"], "tool problem: a cut-off line")
        self.assertIn("line 2: invalid JSON", self.run_cli("check").stderr)

    def test_a_harder_route_leaves_t_val_at_t_val_a(self):
        result = self.adjudicate(
            "--window", "0", "--t-val-a", "704.0", "--t-s", "690.0", "--t-s-source", "full_sample",
            "--verified", "harder", "--t-val", "690.0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("the boundary after this row is 704.0", result.stderr)
        self.assertEqual(self.adjudicate(
            "--window", "0", "--t-val-a", "704.0", "--t-s", "690.0", "--t-s-source", "full_sample",
            "--verified", "harder").returncode, 0)
        self.assertEqual(self.read_events()[-1]["t_val"], 704.0)

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

    def spawn(self, agent, sample_id, role, *args, video="video-id", workspace=None, until=95.0,
              iteration=1):
        if workspace is None:
            workspace = self.workspace(agent, sample_id, role, until=until)
        return self.run_for_video(
            video, "spawn", "--agent", agent, "--sample-id", sample_id, "--role", role,
            "--iteration", str(iteration), "--model", "local", "--workspace", str(workspace), *args,
        )

    def launched(self, agent, video="video-id"):
        """The last spawn row logged under this name, if any."""
        path = self.log_root / "data" / "reviews" / video / "coordinator.log"
        rows = ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                if path.exists() else [])
        spawns = [r for r in rows if r.get("event") == "spawn" and r.get("agent") == agent]
        return spawns[-1] if spawns else None

    def answer_file(self, sample_id, role, iteration=1, video="video-id", **fields):
        """A review file as a subagent leaves it: only what finish reads."""
        path = (self.log_root / "data" / "reviews" / video / sample_id
                / f"{role}.{iteration}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"role": role.rstrip("0123456789"), "sample_id": sample_id,
                                    "iteration": iteration, **fields}), encoding="utf-8")
        return path

    def finish(self, agent, *args, video="video-id", status="completed"):
        spawn = self.launched(agent, video)
        if ("--artifact" not in args and status == "completed" and spawn
                and spawn["role"].startswith("probe_")):
            # a completed probe leaves its review file
            args = (*args, "--artifact", str(self.answer_file(
                spawn["sample_id"], spawn["role"], spawn["iteration"], video=video)))
        return self.run_for_video(video, "finish", "--agent", agent, "--status", status,
                                  "--summary", "ok", *args)

    def test_check_accepts_a_balanced_log(self):
        self.assertEqual(self.spawn("agent-1", "sample-q01", "probe_text").returncode, 0)
        self.assertEqual(self.finish("agent-1").returncode, 0)

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

        result = self.finish("another-name")

        self.assertEqual(result.returncode, 2)
        self.assertIn("no open launch named 'another-name'", result.stderr)
        self.assertIn("the agent_id that spawn_agent returned", result.stderr)
        self.assertIn("Open launches: q03_probe_text_r1", result.stderr)
        self.assertIn("--artifact <file>", result.stderr)
        self.assertEqual(len(self.read_events()), 1)

        # with the review file of a role that is open under another name, it names that launch
        review = self.answer_file("sample-q03", "probe_text")
        result = self.finish("another-name", "--artifact", str(review))
        self.assertEqual(result.returncode, 2)
        self.assertIn("open under another name: q03_probe_text_r1 (line 1)", result.stderr)
        self.assertEqual(len(self.read_events()), 1)

        self.assertEqual(self.finish("q03_probe_text_r1").returncode, 0)
        again = self.finish("q03_probe_text_r1")
        self.assertEqual(again.returncode, 2)
        self.assertIn("already has a finish (line 2)", again.stderr)
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_finish_names_the_review_files_when_a_probe_saved_several(self):
        self.assertEqual(self.spawn("agent-1", "sample-q03", "probe_text").returncode, 0)
        self.probe_file("sample-q03", "probe_text.1.json")
        self.probe_file("sample-q03", "probe_text.1b.json")

        result = self.run_cli("finish", "--agent", "agent-1", "--status", "completed",
                              "--summary", "ok")

        self.assertEqual(result.returncode, 2)
        self.assertIn("has saved several that pass --check", result.stderr)
        self.assertIn("probe_text.1.json", result.stderr)
        self.assertIn("probe_text.1b.json", result.stderr)
        self.assertEqual(len(self.read_events()), 1)

    def test_a_frame_probe_of_another_window_is_not_the_open_launch(self):
        self.assertEqual(self.spawn("agent-0", "sample-q03", "probe_frame0").returncode, 0)
        same = self.finish("agent-9", "--artifact",
                           str(self.answer_file("sample-q03", "probe_frame0")))
        self.assertEqual(same.returncode, 2)
        self.assertIn("open under another name: agent-0 (line 1)", same.stderr)
        other = self.finish("agent-9", "--artifact",
                            str(self.answer_file("sample-q03", "probe_frame1")))
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertIn('material "not found"', other.stderr)

    def test_check_rejects_finish_without_launch_in_an_old_log(self):
        self.write_log({"event": "finish", "agent": "agent-1", "status": "failed",
                        "summary": "The reviewer process failed before writing an artifact."})

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("finish without launch: agent-1", result.stderr)

    def test_a_name_is_launched_again_only_after_a_failed_or_interrupted_finish(self):
        self.assertEqual(self.spawn("agent-1", "sample-q01", "probe_text").returncode, 0)
        second = self.spawn("agent-1", "sample-q01", "probe_text")
        self.assertEqual(second.returncode, 2)
        self.assertIn("is still open", second.stderr)
        self.assertIn("failed if it never started", second.stderr)

        # a note repairs nothing in a log of format 2
        self.assertEqual(self.run_cli(
            "note", "--agent", "agent-1", "--text", "First start hit the thread limit.",
        ).returncode, 0)
        self.assertEqual(self.spawn("agent-1", "sample-q01", "probe_text").returncode, 2)

        self.assertEqual(self.finish("agent-1", status="failed").returncode, 0)
        self.assertEqual(self.spawn("agent-1", "sample-q01", "probe_text").returncode, 0)
        self.assertEqual(self.finish("agent-1").returncode, 0)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)

        third = self.spawn("agent-1", "sample-q02", "probe_text")
        self.assertEqual(third.returncode, 2)
        self.assertIn("a new launch is logged under a new name", third.stderr)

    def test_the_next_stretch_of_a_semiblind_reviewer_keeps_its_name(self):
        self.assertEqual(self.spawn("sb", "sample-q01", "semiblind0").returncode, 2)  # no index
        ws = self.workspace("sb", "sample-q01", "semiblind", until=95.0)
        self.assertEqual(self.spawn("sb", "sample-q01", "semiblind", workspace=ws).returncode, 0)
        self.assertEqual(self.finish("sb").returncode, 0)

        note_path = Path(str(ws) + ".inputs.json")
        note = json.loads(note_path.read_text(encoding="utf-8"))
        same = self.spawn("sb", "sample-q01", "semiblind", workspace=ws)
        self.assertEqual(same.returncode, 2)  # the same stretch again is a new launch
        note["window"], note["inputs"] = 1, {"until": 210.0}
        note_path.write_text(json.dumps(note), encoding="utf-8")
        further = self.spawn("sb", "sample-q01", "semiblind", workspace=ws)
        self.assertEqual(further.returncode, 0, further.stderr)
        self.assertEqual(self.finish("sb").returncode, 0)
        other = self.spawn("sb", "sample-q02", "semiblind")
        self.assertEqual(other.returncode, 2)
        self.assertEqual(self.run_cli("check").returncode, 0)

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

    def test_a_note_excuses_only_the_rows_of_format_1(self):
        old_launch = {"event": "spawn", "agent": "sb_q07", "sample_id": "sample-q07",
                      "role": "semiblind", "iteration": 1}
        self.write_log({"event": "note", "agent": "sb_q02_b", "refers_to": "line 1",
                        "text": "spawn of the relaunch was never written; the artifact exists."},
                       {"event": "finish", "agent": "sb_q02_b", "status": "completed",
                        "summary": "ok"},
                       old_launch)
        self.assertEqual(self.run_cli("check").returncode, 1)
        # an old note excuses the old rows of its agent
        self.write_log({"event": "note", "agent": "sb_q07",
                        "text": "fate unknown after the session was cut."})
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 notes", result.stdout)

        # a new note excuses nothing, old or new
        self.write_log({"event": "spawn", "agent": "old-open", "sample_id": "sample-q08",
                        "role": "semiblind", "iteration": 1})
        self.assertEqual(self.run_cli("note", "--agent", "old-open", "--refers-to", "line 5",
                                      "--text", "fate unknown.").returncode, 0)
        event = self.read_events()[-1]
        self.assertEqual((event["event"], event["refers_to"], event["v"]), ("note", "line 5", 2))
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("launch without finish: old-open", result.stderr)
        self.assertEqual(self.finish("old-open", status="interrupted").returncode, 0)

        # an old note does not excuse a new row of the same agent
        self.assertEqual(self.spawn("sb_q07", "sample-q07", "semiblind").returncode, 2)
        self.assertEqual(self.spawn("sb_q07_new", "sample-q07", "semiblind").returncode, 0)
        self.write_log({"event": "note", "agent": "sb_q07_new", "text": "an old note."})
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("launch without finish: sb_q07_new", result.stderr)

    def test_a_note_without_text_or_an_unknown_kind_is_rejected(self):
        self.assertNotEqual(self.run_cli("note", "--agent", "x").returncode, 0)
        self.assertNotEqual(self.run_cli(
            "sample-edit", "--sample-id", "sample-q01", "--kind", "colour",
            "--changes", "x", "--source", "y",
        ).returncode, 0)

    def test_an_edit_waits_for_the_reruns_its_kind_owes(self):
        edited = self.edit("sample-q03", 'triggers[1].rubric=["names the displayed value"]',
                           source="full_sample.5.json")
        self.assertEqual(edited.returncode, 0, edited.stderr)
        self.assertIn("rubric, window 1", edited.stdout)
        self.assertIn("run full_sample and full_window1 again", edited.stdout)
        event = self.read_events()[-1]
        self.assertEqual((event["kind"], event["window"]), ("rubric", 1))
        self.assertEqual(self.records()["sample-q03"]["triggers"][1]["rubric"],
                         ["names the displayed value"])

        lenient = self.run_cli("check")
        self.assertEqual(lenient.returncode, 0, lenient.stderr)
        self.assertIn("pending rerun", lenient.stderr)
        self.assertIn("full_sample, full_window1", lenient.stderr)
        self.assertIn("1 pending reruns", lenient.stdout)

        final = self.run_cli("check", "--final")
        self.assertEqual(final.returncode, 1)
        self.assertIn("not followed by full_sample, full_window1", final.stderr)

        # the rerun of another sample does not satisfy it
        self.assertEqual(self.spawn("fs_q04", "sample-q04", "full_sample").returncode, 0)
        self.assertEqual(self.finish("fs_q04").returncode, 0)
        self.assertEqual(self.run_cli("check", "--final").returncode, 1)

        # nor does the review of another window; the window's own review does
        for agent, role in (("fs_q03", "full_sample"), ("fw0_q03", "full_window0")):
            self.assertEqual(self.spawn(agent, "sample-q03", role).returncode, 0)
            self.assertEqual(self.finish(agent).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not followed by full_window1", result.stderr)
        self.assertEqual(self.spawn("fw1_q03", "sample-q03", "full_window1").returncode, 0)
        self.assertEqual(self.finish("fw1_q03").returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pending", result.stdout)

        # a row of format 1 with no window is settled by any window's review
        self.write_log({"event": "sample_edit", "sample_id": "sample-q04", "kind": "rubric",
                        "changes": "x", "source": "y"}, video="v2")
        result = self.run_for_video("v2", "check", "--final")
        self.assertIn("not followed by full_sample, full_window", result.stderr)

    def test_a_rejected_sample_owes_no_reruns(self):
        edited = self.edit("sample-q03", "question=What does the second term stand for?",
                           source="coordinator.2.md")
        self.assertEqual(edited.returncode, 0, edited.stderr)
        self.assertIn("a new version of the question", edited.stdout)
        self.assertEqual(self.read_events()[-1]["kind"], "wording")
        self.assertEqual(self.run_cli("check", "--final").returncode, 1)
        rejected = self.edit("sample-q03", "validation.status=rejected", source="coordinator.2.md")
        self.assertEqual(rejected.returncode, 0, rejected.stderr)
        self.assertEqual(self.read_events()[-1]["kind"], "metadata")
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_boundary_edit_is_settled_only_by_the_review_of_its_window(self):
        edited = self.edit("sample-q03", "triggers[2].t_start=296.0", source="full_window2.11.json")
        self.assertEqual(edited.returncode, 0, edited.stderr)
        event = self.read_events()[-1]
        self.assertEqual((event["kind"], event["window"]), ("boundary", 2))
        self.assertEqual(event["fields"], {"triggers[2].t_start": [300.0, 296.0]})
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

    def test_the_flags_the_tool_no_longer_takes_are_refused_with_what_to_do(self):
        for flags in (["--kind", "boundary", "--window", "0", "--changes", "t_start 141.0 -> 205.0."],
                      ["--changes", "referent fixed."], ["--span"]):
            old = self.run_cli("sample-edit", "--sample-id", "sample-q03", *flags,
                               "--source", "full_window0.9.json")
            self.assertEqual(old.returncode, 2, flags)
            self.assertIn(f"sample-edit no longer takes {flags[0]}", old.stderr)
            self.assertIn("--set <field>=<value>", old.stderr)
            self.assertIn("sample-get --sample-id sample-q03", old.stderr)
        self.assertFalse((self.log_root / "data" / "reviews" / "video-id" /
                          "coordinator.log").exists())

    def test_a_span_edit_waits_for_the_adjudication_of_its_stretch(self):
        span = "triggers[1].evidence_span=[198.0, 201.0]"
        early = self.edit("sample-q03", span, source="full_window1.2.json")
        self.assertEqual(early.returncode, 2)
        self.assertIn("checked against t_val", early.stderr)
        self.assertNotIn("evidence_span", self.records()["sample-q03"]["triggers"][1])

        self.trajectory([], [201.0], sample="sample-q03", name="semiblind.2.json")
        self.assertEqual(self.run_cli(
            "adjudicate", "--sample-id", "sample-q03", "--iteration", "2", "--window", "1",
            "--t-val-a", "201.0", "--verified", "na", "--t-val", "201.0",
            "--source", "semiblind.2.json",
        ).returncode, 0)
        late = self.edit("sample-q03", span, source="full_window1.2.json")
        self.assertEqual(late.returncode, 0, late.stderr)
        event = self.read_events()[-1]
        self.assertEqual((event["kind"], event["window"], event["span"]), ("metadata", 1, True))
        self.assertEqual(self.run_cli("check", "--final").returncode, 0)

        # an old log with the order reversed
        self.write_log({"event": "sample_edit", "sample_id": "sample-q04", "kind": "metadata",
                        "window": 0, "span": True, "changes": "x", "source": "y"}, video="v2")
        result = self.run_for_video("v2", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("edited before its stretch was adjudicated", result.stderr)

    def test_a_rubric_edit_is_settled_by_its_window_and_full_sample(self):
        self.assertEqual(self.edit("sample-q16", 'triggers[0].rubric=["demands the 1/4! form"]',
                                   source="full_sample.3.json").returncode, 0)
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
        self.assertEqual(self.edit(
            "sample-q02", "question=What does the blue function now on the screen approach?",
            source="coordinator.5.md").returncode, 0)
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

    def test_a_boundary_moved_to_a_reviewers_measurement_is_a_nudge(self):
        # the review the edit names measured the frame at 98.5
        self.answer_file("sample-q17", "full_window0", 2, checks=[{"note": "the curve is drawn "
                         "from t=98.5 on"}])
        nudged = self.edit("sample-q17", "triggers[0].t_start=98.5", source="full_window0.2.json")
        self.assertEqual(nudged.returncode, 0, nudged.stderr)
        self.assertIn("nudge, window 0", nudged.stdout)
        self.assertIn("no rerun is owed", nudged.stdout)
        event = self.read_events()[-1]
        self.assertEqual((event["kind"], event["window"]), ("nudge", 0))
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pending", result.stderr)

        # the same move to a value no reviewer measured is a boundary edit, and so is a cut
        unmeasured = self.edit("sample-q17", "triggers[1].t_start=199.0", source="full_window1.2.json")
        self.assertEqual(unmeasured.returncode, 0, unmeasured.stderr)
        self.assertIn("logged as boundary, not nudge: 199.0 is not among the numbers",
                      unmeasured.stdout)
        self.answer_file("sample-q17", "full_window2", 2, measured=301.0)
        cut = self.edit("sample-q17", "triggers[2].t_start=301.0", source="full_window2.2.json")
        self.assertEqual(cut.returncode, 0, cut.stderr)
        self.assertIn("only narrows a window is not usually made", cut.stdout)
        self.assertEqual([e["kind"] for e in self.read_events()], ["nudge", "boundary", "boundary"])
        result = self.run_cli("check", "--final")
        self.assertIn("not followed by full_window1", result.stderr)
        self.assertIn("not followed by full_window2", result.stderr)

    def test_edits_without_a_kind_and_kinds_without_reruns_are_not_checked(self):
        self.write_log({"event": "sample_edit", "sample_id": "sample-q01",
                        "changes": "legacy line", "source": "coordinator.1.md"})
        level = self.edit("sample-q01", "reasoning_level=L2", source="full_window0.3.json")
        self.assertEqual(level.returncode, 0, level.stderr)
        self.assertIn("re-adjudicate stage A by the route of the new level", level.stdout)
        self.assertEqual(self.read_events()[-1]["kind"], "level")
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

    def test_spawn_reads_the_sample_the_role_and_the_window_from_the_note(self):
        ws = self.workspace("pf", "sample-q01", "probe_frame2")
        result = self.run_cli("spawn", "--agent", "pf", "--iteration", "1", "--model", "local",
                              "--workspace", str(ws))
        self.assertEqual(result.returncode, 0, result.stderr)
        event = self.read_events()[-1]
        self.assertEqual((event["sample_id"], event["role"], event["window"]),
                         ("sample-q01", "probe_frame2", 2))
        self.assertEqual(event["reasoning_effort"], "default")

        # a role typed without the index takes it from the note too
        bare = self.spawn("fw", "sample-q01", "full_window",
                          workspace=self.workspace("fw", "sample-q01", "full_window3"))
        self.assertEqual(bare.returncode, 0, bare.stderr)
        self.assertEqual(self.read_events()[-1]["role"], "full_window3")

        # a note of the old kind, with no window for the window review
        old = self.workspace("fw_old", "sample-q01", "full_window")
        result = self.run_cli("spawn", "--agent", "fw_old", "--iteration", "1", "--model",
                              "local", "--workspace", str(old))
        self.assertEqual(result.returncode, 2)
        self.assertIn("--role full_window --window <idx>", result.stderr)

    def test_spawn_refuses_unknown_roles_and_efforts(self):
        for role in ("full", "semiblind2", "reviewer"):
            result = self.spawn("x", "sample-q01", role, workspace=self.log_root / "none")
            self.assertEqual(result.returncode, 2, role)
            self.assertIn("unknown --role", result.stderr)
        effort = self.spawn("x", "sample-q01", "probe_text", "--reasoning-effort", "very high")
        self.assertEqual(effort.returncode, 2)
        self.assertIn("one of default, none, minimal, low, medium, high, xhigh", effort.stderr)
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

    def test_a_frame_probe_of_a_window_that_turned_optional_is_superseded(self):
        records = self.records()
        records["sample-q05"]["triggers"] = [
            {"idx": 0, "required": True, "t_start": 100.0, "t_end": 110.0}]
        self.write_records(*records.values())
        self.assertEqual(self.spawn("pf0_r1", "sample-q05", "probe_frame0").returncode, 0)
        self.assertEqual(self.finish("pf0_r1").returncode, 0)

        # an optional window is put before the required one, which becomes window 1
        records["sample-q05"]["triggers"] = [
            {"idx": 0, "required": False, "t_start": 90.0, "t_end": 99.0},
            {"idx": 1, "required": True, "t_start": 100.0, "t_end": 110.0}]
        self.write_records(*records.values())
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cut at window 0, which is optional now", result.stderr)
        self.assertIn("run probe_frame1", result.stderr)
        self.assertNotIn("is stale", result.stderr)

        self.assertEqual(self.spawn("pf1_r1", "sample-q05", "probe_frame1").returncode, 0)
        self.assertEqual(self.finish("pf1_r1").returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_frame_probe_of_a_window_that_went_away_is_superseded(self):
        self.assertEqual(self.spawn("pf0_r1", "sample-q05", "probe_frame0").returncode, 0)
        self.assertEqual(self.spawn("pf3_r1", "sample-q05", "probe_frame3").returncode, 0)
        for agent in ("pf0_r1", "pf3_r1"):
            self.assertEqual(self.finish(agent).returncode, 0)
        records = self.records()
        records["sample-q05"]["triggers"] = records["sample-q05"]["triggers"][:1]
        self.write_records(*records.values())

        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

        # the window that is still required keeps its own check
        records["sample-q05"]["triggers"][0]["t_start"] = 90.0
        self.write_records(*records.values())
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("probe_frame0 of sample-q05 (pf0_r1) is stale", result.stderr)
        self.assertNotIn("probe_frame3", result.stderr)

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

    def test_finish_restores_a_launch_whose_spawn_was_never_logged(self):
        ws = self.workspace("pv", "sample-q03", "probe_vision")
        review = self.answer_file("sample-q03", "probe_vision")

        result = self.finish("agent-7", "--artifact", str(review))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("logged spawn and finish", result.stdout)
        self.assertIn("was never logged: it is restored from", result.stderr)
        spawn, finish = self.read_events()
        self.assertEqual((spawn["event"], spawn["recovered"], spawn["role"], spawn["sample_id"]),
                         ("spawn", True, "probe_vision", "sample-q03"))
        self.assertEqual(spawn["record_sha"], review_inputs.record_sha(self.records()["sample-q03"]))
        self.assertEqual(spawn["inputs"], {"until": 410.0})
        self.assertEqual(spawn["workspace"], ".review_ws/video-id/sample-q03/pv")
        self.assertIsNone(spawn["prompt_sha"])
        self.assertEqual((finish["role"], finish["sample_id"], finish["iteration"]),
                         ("probe_vision", "sample-q03", 1))
        self.assertEqual(self.run_cli("check", "--final").returncode, 0)

        # that folder is used now: it is not the material of another launch
        again = self.finish("agent-8", "--artifact", str(review))
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn('material "not found"', again.stderr)
        self.assertEqual(self.read_events()[-1]["material"], "not found")
        self.assertEqual(len(self.read_events()), 3)
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(ws.is_dir())

    def test_finish_asks_for_the_workspace_when_several_could_be_the_material(self):
        self.workspace("pt_a", "sample-q04", "probe_text")
        chosen = self.workspace("pt_b", "sample-q04", "probe_text")
        self.workspace("other_sample", "sample-q05", "probe_text")
        self.workspace("other_role", "sample-q04", "probe_vision")
        review = self.answer_file("sample-q04", "probe_text")

        unclear = self.finish("agent-9", "--artifact", str(review))
        self.assertEqual(unclear.returncode, 2)
        self.assertIn("add --workspace <folder> to this finish", unclear.stderr)
        self.assertIn(".review_ws/video-id/sample-q04/pt_a, .review_ws/video-id/sample-q04/pt_b",
                      unclear.stderr)

        named = self.finish("agent-9", "--artifact", str(review), "--workspace", str(chosen))
        self.assertEqual(named.returncode, 0, named.stderr)
        self.assertEqual(self.read_events()[0]["workspace"], ".review_ws/video-id/sample-q04/pt_b")

    def test_material_cut_after_the_answer_was_saved_restores_nothing(self):
        review = self.answer_file("sample-q05", "probe_text")
        before = review.stat().st_mtime - 600
        os.utime(review, (before, before))
        self.workspace("late", "sample-q05", "probe_text")

        result = self.finish("agent-10", "--artifact", str(review))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sets no flag and settles no rerun", result.stderr)
        event, = self.read_events()
        self.assertEqual((event["event"], event["material"], event["role"]),
                         ("finish", "not found", "probe_text"))
        self.assertTrue((self.log_root / event["artifact_copy"]).is_file())
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_a_probe_is_measured_again_once_and_with_a_reason(self):
        defect = "the basis quotes the title of the video: the answer came from recognition"
        self.assertEqual(self.spawn("pt_1", "sample-q01", "probe_text").returncode, 0)
        early = self.spawn("pt_2", "sample-q01", "probe_text")
        self.assertEqual(early.returncode, 2)
        self.assertIn("on the same material is still open: pt_1 (line 1)", early.stderr)
        self.assertEqual(self.finish("pt_1").returncode, 0)

        bare = self.spawn("pt_2", "sample-q01", "probe_text")
        self.assertEqual(bare.returncode, 2)
        self.assertIn("this is a repeat of pt_1 (line 1)", bare.stderr)
        self.assertIn("at most once per probe and version of the sample", bare.stderr)
        self.assertIn('--reason "<the defect, with the evidence>"', bare.stderr)
        self.assertEqual(self.spawn("pt_2", "sample-q01", "probe_text", "--reason", defect).returncode, 0)
        event = self.read_events()[-1]
        self.assertEqual((event["repeat_of"], event["reason"]), (1, defect))

        # an interrupted attempt measured nothing: the repeat is still owed its run
        self.assertEqual(self.finish("pt_2", status="interrupted").returncode, 0)
        self.assertEqual(self.spawn("pt_2", "sample-q01", "probe_text", "--reason", defect).returncode, 0)
        self.assertEqual(self.finish("pt_2").returncode, 0)

        for round_ in (1, 2):  # another round on the same material is the same probe
            third = self.spawn("pt_3", "sample-q01", "probe_text", "--reason", defect, iteration=round_)
            self.assertEqual(third.returncode, 2)
            self.assertIn("was measured again already: pt_2", third.stderr)
            self.assertIn("A second repeat sets no flag", third.stderr)

        # another sample, another probe and the reviewers are not repeats
        self.assertEqual(self.spawn("pt_q02", "sample-q02", "probe_text").returncode, 0)
        self.assertEqual(self.spawn("pv_1", "sample-q01", "probe_vision").returncode, 0)
        for agent in ("fs_1", "fs_2"):
            self.assertEqual(self.spawn(agent, "sample-q01", "full_sample").returncode, 0)

    def test_a_repeat_logged_before_the_field_existed_is_told_by_the_same_rule(self):
        note = json.loads(Path(str(self.workspace("x", "sample-q06", "probe_text"))
                               + ".inputs.json").read_text(encoding="utf-8"))
        launch = {"event": "spawn", "sample_id": "sample-q06", "role": "probe_text",
                  "iteration": 1, "inputs": note["inputs"], "record_sha": note["record_sha"],
                  "annotations": note["annotations"]}
        done = {"event": "finish", "status": "completed", "summary": "ok"}
        self.write_log({**launch, "agent": "pt_r1"}, {**done, "agent": "pt_r1"},
                       {**launch, "agent": "pt_r1b"}, {**done, "agent": "pt_r1b"})

        third = self.spawn("pt_r1c", "sample-q06", "probe_text", "--reason", "another look")

        self.assertEqual(third.returncode, 2)
        self.assertIn("was measured again already: pt_r1b (line 3)", third.stderr)

    def test_a_finish_keeps_a_copy_of_the_review_file(self):
        self.assertEqual(self.spawn("pt_1", "sample-q01", "probe_text").returncode, 0)
        review = self.probe_file("sample-q01", "probe_text.1.json")
        first = review.read_bytes()

        result = self.run_cli("finish", "--agent", "pt_1", "--status", "completed",
                              "--summary", "ok")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("artifact: data/reviews/video-id/sample-q01/probe_text.1.json", result.stdout)
        event = self.read_events()[-1]
        self.assertEqual(event["artifact_sha"], hashlib.sha256(first).hexdigest())
        self.assertEqual((self.log_root / event["artifact_copy"]).read_bytes(), first)

        # the repeat writes the same file name; the first attempt stays readable
        self.assertEqual(self.spawn("pt_2", "sample-q01", "probe_text", "--reason", "defect").returncode, 0)
        review.write_text(json.dumps({"role": "probe_text", "sample_id": "sample-q01",
                                      "iteration": 1, "answer": "another"}), encoding="utf-8")
        self.assertEqual(self.finish("pt_2", "--artifact", str(review)).returncode, 0)
        kept = sorted((review.parent / ".finished").iterdir())
        self.assertEqual(len(kept), 2)
        self.assertEqual((self.log_root / event["artifact_copy"]).read_bytes(), first)

        # a completed probe with no review file did not complete
        self.assertEqual(self.spawn("pv_1", "sample-q01", "probe_vision").returncode, 0)
        missing = self.run_cli("finish", "--agent", "pv_1", "--status", "completed", "--summary", "ok")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--status interrupted or failed", missing.stderr)

    def test_a_launch_keeps_the_review_file_of_an_attempt_finished_in_format_1(self):
        review = self.answer_file("sample-q02", "probe_text")
        note = json.loads(Path(str(self.workspace("pt_old", "sample-q02", "probe_text"))
                               + ".inputs.json").read_text(encoding="utf-8"))
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        self.write_log({"ts": now, "event": "spawn", "agent": "pt_old", "sample_id": "sample-q02",
                        "role": "probe_text", "iteration": 1, "inputs": note["inputs"],
                        "record_sha": note["record_sha"], "annotations": note["annotations"]},
                       {"ts": now, "event": "finish", "agent": "pt_old", "status": "completed",
                        "summary": "ok", "artifact": str(review)})

        result = self.spawn("pt_new", "sample-q02", "probe_text", "--reason", "defect")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("the review files of the earlier attempts are kept", result.stdout)
        kept, = self.read_events()[-1]["kept"]
        self.assertEqual(kept["finish_line"], 2)
        self.assertEqual((self.log_root / kept["copy"]).read_bytes(), review.read_bytes())

    def edit_file(self, sample_id):
        return self.log_root / "data" / "reviews" / "video-id" / sample_id / ".edit" / "record.json"

    def test_a_record_is_edited_through_a_file(self):
        before = self.annotations.read_text(encoding="utf-8").splitlines()
        got = self.run_cli("sample-get", "--sample-id", "sample-q02")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertIn("sample-edit --sample-id sample-q02 --source", got.stdout)
        file = self.edit_file("sample-q02")
        record = json.loads(file.read_text(encoding="utf-8"))
        record["question"] = "Что стоит во втором слагаемом?"
        record["triggers"][0]["t_end"] = 120.0
        file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        edited = self.run_cli("sample-edit", "--sample-id", "sample-q02", "--source", "full_sample.1.json")

        self.assertEqual(edited.returncode, 0, edited.stderr)
        self.assertIn("logged 2 sample_edit rows", edited.stdout)
        self.assertIn("next: wording", edited.stdout)
        self.assertIn("next: boundary, window 0 (triggers[0].t_end: 110.0 -> 120.0): run "
                      "full_window0 again", edited.stdout)
        wording, boundary = self.read_events()
        self.assertEqual((wording["kind"], boundary["kind"], boundary["window"]),
                         ("wording", "boundary", 0))
        self.assertEqual(wording["sha_before"], review_inputs.record_sha(json.loads(before[1])))
        self.assertEqual(wording["sha_after"], review_inputs.record_sha(record))
        self.assertEqual((boundary["sha_before"], boundary["sha_after"]),
                         (wording["sha_before"], wording["sha_after"]))
        self.assertEqual(wording["annotations"], "data/annotations/video-id.jsonl")
        self.assertEqual(wording["fields"]["question"], [None, "Что стоит во втором слагаемом?"])
        after = self.annotations.read_text(encoding="utf-8").splitlines()
        self.assertEqual(after[1], json.dumps(record, ensure_ascii=False))
        self.assertEqual(after[:1] + after[2:], before[:1] + before[2:])
        self.assertEqual(len(list((file.parent.parent / ".versions").iterdir())), 2)

        # the same command again writes nothing, and the file takes the next edit as it is
        again = self.run_cli("sample-edit", "--sample-id", "sample-q02", "--source", "x")
        self.assertEqual(again.returncode, 0)
        self.assertIn("already holds this edit (line 2)", again.stdout)
        record["validation"]["status"] = "rejected"
        file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        self.assertEqual(self.run_cli("sample-edit", "--sample-id", "sample-q02",
                                      "--source", "coordinator.1.md").returncode, 0)
        self.assertEqual([e["kind"] for e in self.read_events()], ["wording", "boundary", "metadata"])
        self.assertEqual(self.records()["sample-q02"]["validation"]["status"], "rejected")

    def test_an_edit_from_a_file_taken_before_another_edit_is_refused(self):
        self.assertEqual(self.run_cli("sample-get", "--sample-id", "sample-q02").returncode, 0)
        file = self.edit_file("sample-q02")
        record = json.loads(file.read_text(encoding="utf-8"))
        record["question"] = "A new question?"
        file.write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(self.edit("sample-q02", "triggers[0].t_start=90.0").returncode, 0)

        stale = self.run_cli("sample-edit", "--sample-id", "sample-q02", "--source", "x")

        self.assertEqual(stale.returncode, 2)
        self.assertIn("has changed since", stale.stderr)
        self.assertIn("would write the earlier version back over it", stale.stderr)
        self.assertIn("Run sample-get again", stale.stderr)
        self.assertEqual(self.records()["sample-q02"]["triggers"][0]["t_start"], 90.0)
        self.assertEqual(len(self.read_events()), 1)

    def test_an_edit_the_tool_cannot_take_changes_nothing(self):
        text = self.annotations.read_text(encoding="utf-8")
        self.assertEqual(self.run_cli("sample-get", "--sample-id", "sample-q02").returncode, 0)
        file = self.edit_file("sample-q02")
        file.write_text('{"id": "sample-q02", "question": ', encoding="utf-8")
        broken = self.run_cli("sample-edit", "--sample-id", "sample-q02", "--source", "x")
        self.assertEqual(broken.returncode, 2)
        self.assertIn("is not valid JSON", broken.stderr)
        file.write_text(json.dumps({"id": "sample-q03"}), encoding="utf-8")
        other = self.run_cli("sample-edit", "--sample-id", "sample-q02", "--source", "x")
        self.assertEqual(other.returncode, 2)
        self.assertIn("id is not edited", other.stderr)
        refusals = {
            "reasoning_level=L9": "the edit breaks the record",
            "id=another": "cannot be changed",
            "notes=x": "are not fields of a sample record",
            "triggers[0].note=x": "is not a field of a window",
            "triggers[9].t_start=1.0": "the record has no 9 on the way",
            "triggers[0].t_start=100.0": "nothing changed",
            "t_start": "write <field>=<value>",
        }
        for assignment, message in refusals.items():
            result = self.edit("sample-q02", assignment)
            self.assertEqual(result.returncode, 2, assignment)
            self.assertIn(message, result.stderr, assignment)
            self.assertIn("not logged: nothing was written", result.stderr)
        missing = self.run_cli("sample-edit", "--sample-id", "sample-q04", "--source", "x")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("sample-get --sample-id sample-q04", missing.stderr)
        self.assertEqual(self.annotations.read_text(encoding="utf-8"), text)
        self.assertFalse((self.log_root / "data" / "reviews" / "video-id" / "coordinator.log").exists())

    def test_an_edit_cut_off_before_the_record_was_written_is_finished_by_the_same_command(self):
        import contextlib
        import io
        from unittest import mock
        import coordinator_log
        self.to_partial()
        command = ["sample-edit", "--sample-id", "sample-q02", "--set", "triggers[0].t_start=90.0",
                   "--source", "full_window0.1.json"]
        stderr = io.StringIO()
        with mock.patch.object(coordinator_log.sample_edit, "write_record",
                               side_effect=OSError("no space left")), \
                mock.patch.object(coordinator_log, "ROOT", self.log_root), \
                contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = coordinator_log.main(["video-id", *command])
        self.assertEqual(code, 2)
        self.assertIn("the edit is logged (1 rows), but the record was not written", stderr.getvalue())
        self.assertEqual(self.records()["sample-q02"]["triggers"][0]["t_start"], 100.0)

        check = self.run_cli("check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("sample-q02: the edit of line 1 is in the log, but the record does not hold "
                      "it", check.stderr)
        self.assertIn("Run `sample-get --sample-id sample-q02` (or the same sample-edit command "
                      "again)", check.stderr)

        again = self.run_cli(*command)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("the record is written now", again.stdout)
        self.assertEqual(len(self.read_events()), 1)
        self.assertEqual(self.records()["sample-q02"]["triggers"][0]["t_start"], 90.0)
        self.assertEqual(self.run_cli("check").returncode, 0)

    def cut_off(self, sample_id, assignment):
        """A sample-edit that logs its row and fails before the record is written."""
        import contextlib
        import io
        from unittest import mock
        import coordinator_log
        with mock.patch.object(coordinator_log.sample_edit, "write_record",
                               side_effect=OSError("no space left")), \
                mock.patch.object(coordinator_log, "ROOT", self.log_root), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return coordinator_log.main(["video-id", "sample-edit", "--sample-id", sample_id,
                                         "--set", assignment, "--source", "full_window0.1.json"])

    def test_a_cut_off_edit_is_finished_before_any_other_edit(self):
        self.to_partial()
        self.assertEqual(self.cut_off("sample-q02", "triggers[0].t_start=90.0"), 2)
        self.assertEqual(self.records()["sample-q02"]["triggers"][0]["t_start"], 100.0)

        # a launch does not go on the record that lacks the logged edit
        early = self.spawn("fw", "sample-q02", "full_window0")
        self.assertEqual(early.returncode, 2)
        self.assertIn("the edit of line 1 is in the log, but the record does not hold it",
                      early.stderr)
        # another edit does not go over the logged one: the tool writes that one first
        other = self.edit("sample-q02", "triggers[0].t_end=120.0")
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertIn("the edit of line 1 was in the log and not in the record: the record is "
                      "written now", other.stdout)
        self.assertIn("logged 1 sample_edit row", other.stdout)
        window = self.records()["sample-q02"]["triggers"][0]
        self.assertEqual((window["t_start"], window["t_end"]), (90.0, 120.0))
        first, second = self.read_events()
        self.assertEqual(second["sha_before"], first["sha_after"])
        self.assertEqual(self.run_cli("check").returncode, 0)

        # sample-get finishes it too, and hands out the record with the edit in it
        self.assertEqual(self.cut_off("sample-q03", "triggers[0].t_start=90.0"), 2)
        got = self.run_cli("sample-get", "--sample-id", "sample-q03")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertIn("the record is written now", got.stdout)
        exported = json.loads(self.edit_file("sample-q03").read_text(encoding="utf-8"))
        self.assertEqual(exported["triggers"][0]["t_start"], 90.0)
        self.assertEqual(self.records()["sample-q03"]["triggers"][0]["t_start"], 90.0)

        # without the copy the tool kept, only the same edit again finishes it
        self.assertEqual(self.cut_off("sample-q04", "triggers[0].t_start=90.0"), 2)
        versions = self.log_root / "data" / "reviews" / "video-id" / "sample-q04" / ".versions"
        for copy in versions.iterdir():
            copy.unlink()
        refused = self.edit("sample-q04", "triggers[0].t_end=120.0")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("the copy the tool kept of the new version is gone", refused.stderr)
        adopt = self.run_cli("sample-edit", "--sample-id", "sample-q04", "--adopt", "--source", "x")
        self.assertEqual(adopt.returncode, 2)
        self.assertEqual(self.records()["sample-q04"]["triggers"][0], record("sample-q04")["triggers"][0])
        same = self.edit("sample-q04", "triggers[0].t_start=90.0", source="full_window0.1.json")
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertEqual(self.records()["sample-q04"]["triggers"][0]["t_start"], 90.0)
        self.assertEqual(len(self.read_events()), 4)
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_a_record_changed_without_the_tool_is_named_by_check_and_adopted(self):
        self.to_partial()
        self.assertEqual(self.spawn("fs", "sample-q03", "full_sample").returncode, 0)
        self.assertEqual(self.finish("fs").returncode, 0)
        # a launch of format 1 says no version the check could hold a record to
        self.write_log({"event": "spawn", "agent": "old", "sample_id": "sample-q04",
                        "role": "full_sample", "iteration": 1, "record_sha": "0" * 64},
                       {"event": "finish", "agent": "old", "status": "completed", "summary": "ok"})
        self.assertEqual(self.run_cli("check").returncode, 0)

        records = self.records()
        records["sample-q03"]["triggers"][0]["t_start"] = 90.0
        self.write_records(*records.values())
        check = self.run_cli("check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("sample-q03: the record is not the version the log last knew (line 1)",
                      check.stderr)
        self.assertIn("sample-edit --sample-id sample-q03 --adopt --source", check.stderr)
        # a launch on the changed record would make it the version the log knows
        unseen = self.spawn("fs2", "sample-q03", "full_sample")
        self.assertEqual(unseen.returncode, 2)
        self.assertIn("it was changed without sample-edit", unseen.stderr)
        self.assertIn("Then prepare the workspace again and launch", unseen.stderr)

        adopted = self.run_cli("sample-edit", "--sample-id", "sample-q03", "--adopt", "--source",
                               "moved by hand after full_window0.1.json")
        self.assertEqual(adopted.returncode, 0, adopted.stderr)
        self.assertIn("run full_window0 again", adopted.stdout)
        event = self.read_events()[-1]
        self.assertEqual((event["kind"], event["window"], event["adopted"]), ("boundary", 0, True))
        self.assertEqual(event["sha_before"], self.read_events()[0]["record_sha"])
        self.assertEqual(event["sha_after"], review_inputs.record_sha(self.records()["sample-q03"]))
        check = self.run_cli("check")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("adopted: line 5: sample-q03 was changed without sample-edit (boundary, "
                      "window 0)", check.stdout)
        self.assertIn("pending rerun: line 5: edit of sample-q03 not followed by full_window0",
                      check.stderr)
        nothing = self.run_cli("sample-edit", "--sample-id", "sample-q03", "--adopt", "--source", "x")
        self.assertEqual(nothing.returncode, 2)
        self.assertIn("nothing to adopt", nothing.stderr)
        # a sample the log holds no version of — only rows of format 1, or none — has nothing
        # to be compared with: an adopt row would owe every review of an untouched record
        for sample in ("sample-q04", "sample-q05"):
            unknown = self.run_cli("sample-edit", "--sample-id", sample, "--adopt", "--source", "x")
            self.assertEqual(unknown.returncode, 2)
            self.assertIn("holds no version of", unknown.stderr)
            self.assertIn("nothing is owed", unknown.stderr)
        self.assertEqual(len(self.read_events()), 5)

        # with the version before the change not kept, everything runs again
        records["sample-q03"]["triggers"][0]["t_start"] = 80.0
        self.write_records(*records.values())
        versions = self.log_root / "data" / "reviews" / "video-id" / "sample-q03" / ".versions"
        for copy in versions.iterdir():
            copy.unlink()
        blind = self.run_cli("sample-edit", "--sample-id", "sample-q03", "--adopt", "--source", "x")
        self.assertEqual(blind.returncode, 0, blind.stderr)
        self.assertEqual(self.read_events()[-1]["kind"], "wording")
        self.assertIn("every role runs again", blind.stdout)

    def test_an_edit_does_not_go_over_a_change_made_without_the_tool(self):
        self.to_partial()
        self.assertEqual(self.edit("sample-q02", "triggers[0].t_end=111.0").returncode, 0)
        records = self.records()
        records["sample-q02"]["question"] = "A question written into the file by hand?"
        self.write_records(*records.values())

        over = self.edit("sample-q02", "triggers[1].t_end=211.0")

        self.assertEqual(over.returncode, 2)
        self.assertIn("it was changed without sample-edit", over.stderr)
        self.assertIn("--adopt", over.stderr)
        self.assertIn("Then run this command again", over.stderr)
        self.assertEqual(len(self.read_events()), 1)
        self.assertEqual(self.records()["sample-q02"]["triggers"][1]["t_end"], 210.0)
        # the same for an edit from a file
        self.assertEqual(self.run_cli("sample-get", "--sample-id", "sample-q02").returncode, 0)
        file = self.edit_file("sample-q02")
        exported = json.loads(file.read_text(encoding="utf-8"))
        exported["triggers"][1]["t_end"] = 211.0
        file.write_text(json.dumps(exported), encoding="utf-8")
        self.assertEqual(self.run_cli("sample-edit", "--sample-id", "sample-q02",
                                      "--source", "x").returncode, 2)

        adopted = self.run_cli("sample-edit", "--sample-id", "sample-q02", "--adopt",
                               "--source", "the question was reworded by hand")
        self.assertEqual(adopted.returncode, 0, adopted.stderr)
        self.assertEqual(self.edit("sample-q02", "triggers[1].t_end=211.0").returncode, 0)
        first, wording, last = self.read_events()
        self.assertEqual((wording["kind"], wording["adopted"]), ("wording", True))
        self.assertEqual((wording["sha_before"], last["sha_before"]),
                         (first["sha_after"], wording["sha_after"]))

    def test_the_same_values_written_differently_are_no_edit(self):
        self.to_partial()
        text = self.annotations.read_text(encoding="utf-8")
        for assignment in ("triggers[0].t_start=100", "triggers[0].idx=0.0"):
            same = self.edit("sample-q02", assignment)
            self.assertEqual(same.returncode, 2, assignment)
            self.assertIn("written differently", same.stderr)
            self.assertIn("not logged: nothing was written", same.stderr)
        self.assertEqual(self.annotations.read_text(encoding="utf-8"), text)
        self.assertFalse((self.log_root / "data" / "reviews" / "video-id" / "coordinator.log").exists())

        # written into the file by hand, it is adopted as a change that owes nothing
        self.assertEqual(self.edit("sample-q02", "triggers[0].t_end=111.0").returncode, 0)
        records = self.records()
        records["sample-q02"]["triggers"][0]["t_end"] = 111
        self.write_records(*records.values())
        self.assertEqual(self.run_cli("check").returncode, 1)
        adopted = self.run_cli("sample-edit", "--sample-id", "sample-q02", "--adopt", "--source", "x")
        self.assertEqual(adopted.returncode, 0, adopted.stderr)
        self.assertEqual(self.read_events()[-1]["kind"], "metadata")
        self.assertIn("no rerun is owed", adopted.stdout)
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_a_file_with_a_line_that_is_no_record_is_named_and_left_alone(self):
        self.to_partial()
        with self.annotations.open("a", encoding="utf-8") as stream:
            stream.write("not json\n")
        text = self.annotations.read_text(encoding="utf-8")

        refused = self.edit("sample-q02", "triggers[0].t_end=111.0")

        self.assertEqual(refused.returncode, 2)
        self.assertIn("has a line that is not a record", refused.stderr)
        self.assertIn("validate_samples.py", refused.stderr)
        self.assertNotIn("To add a new sample", refused.stderr)
        self.assertEqual(self.annotations.read_text(encoding="utf-8"), text)

    def test_a_broken_copy_of_a_version_is_written_again(self):
        self.to_partial()
        self.assertEqual(self.run_cli("sample-get", "--sample-id", "sample-q02").returncode, 0)
        versions = self.log_root / "data" / "reviews" / "video-id" / "sample-q02" / ".versions"
        copy, = versions.iterdir()
        copy.write_text('{"id": "sample-q02", "trig', encoding="utf-8")
        self.assertEqual(self.run_cli("sample-get", "--sample-id", "sample-q02").returncode, 0)
        self.assertEqual(review_inputs.record_sha(json.loads(copy.read_text(encoding="utf-8")))[:12],
                         copy.stem)
        self.assertEqual([f.name for f in versions.iterdir()], [copy.name])

    def test_a_new_sample_is_added_through_the_tool(self):
        self.to_partial()
        example = json.loads((ROOT / "docs" / "sample_examples.jsonl").read_text(
            encoding="utf-8").splitlines()[0])
        file = self.log_root / "new.json"
        file.write_text(json.dumps(example), encoding="utf-8")
        command = ["sample-edit", "--sample-id", example["id"], "--from", str(file),
                   "--source", "rebuilt from the proposal of full_sample.1.json"]

        nowhere = self.run_cli(*command)
        self.assertEqual(nowhere.returncode, 2)
        self.assertIn("To add a new sample", nowhere.stderr)
        added = self.run_cli(*command, "--annotations", str(self.annotations))
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertEqual(list(self.records())[-1], example["id"])
        self.assertEqual(len(self.records()), 18)
        event, = self.read_events()
        self.assertEqual((event["kind"], event["added"], event["sha_before"]), ("wording", True, None))
        final = self.run_cli("check", "--final")
        self.assertEqual(final.returncode, 1)
        self.assertIn("not followed by full_sample, full_window, probe_frame", final.stderr)
        twice = self.run_cli(*command, "--annotations", str(self.annotations))
        self.assertEqual(twice.returncode, 0)
        self.assertIn("and in the log already: nothing was written", twice.stdout)
        self.assertEqual(len(self.read_events()), 1)
        example["question"] = "Another question under the same id?"
        file.write_text(json.dumps(example), encoding="utf-8")
        other = self.run_cli(*command, "--annotations", str(self.annotations))
        self.assertEqual(other.returncode, 2)
        self.assertIn("is already in data/annotations/partial/video-id.full.jsonl", other.stderr)

    def test_a_record_in_several_files_is_named_with_annotations(self):
        self.to_partial()
        copy = self.annotations.with_name("video-id.a.jsonl")
        copy.write_text(json.dumps(record("sample-q02")) + "\n", encoding="utf-8")
        unclear = self.run_cli("sample-get", "--sample-id", "sample-q02")
        self.assertEqual(unclear.returncode, 2)
        self.assertIn("is in several files", unclear.stderr)
        self.assertIn("--annotations <file>", unclear.stderr)
        named = self.run_cli("sample-get", "--sample-id", "sample-q02", "--annotations", str(copy))
        self.assertEqual(named.returncode, 0, named.stderr)
        note = json.loads(Path(str(self.edit_file("sample-q02")) + ".base.json").read_text())
        self.assertEqual(note["annotations"], "data/annotations/partial/video-id.a.jsonl")

    def test_a_restored_launch_settles_an_edit_only_on_the_version_after_it(self):
        self.workspace("fs_early", "sample-q03", "full_sample")  # cut before the edit
        self.assertEqual(self.edit("sample-q03", 'triggers[0].rubric=["an item"]').returncode, 0)
        self.workspace("fw_late", "sample-q03", "full_window0")  # cut after it
        sighted = self.answer_file("sample-q03", "full_sample")
        window = self.answer_file("sample-q03", "full_window0", window_idx=0)
        for agent, review in (("agent-fs", sighted), ("agent-fw", window)):
            restored = self.finish(agent, "--artifact", str(review))
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertIn("logged spawn and finish", restored.stdout)

        final = self.run_cli("check", "--final")

        self.assertEqual(final.returncode, 1)
        self.assertIn("line 1: edit of sample-q03 not followed by full_sample", final.stderr)
        self.assertNotIn("full_window0", final.stderr)

    def test_the_first_row_of_a_stretch_is_read_from_the_trajectory(self):
        self.trajectory([573.2, 582.9], [590.0])

        def row(*args, source="semiblind.1.json", iteration="1"):
            return self.run_cli("adjudicate", "--sample-id", "sample-q10", "--iteration",
                                iteration, "--source", source, "--verified", "na", *args)

        sighted = row("--window", "0", "--t-val-a", "582.9", source="full_sample.1.json")
        self.assertEqual(sighted.returncode, 2)
        self.assertIn("cites the semi-blind review whose trajectory it was read from", sighted.stderr)
        placed = row("--window", "0", "--t-val-a", "576.0")
        self.assertEqual(placed.returncode, 2)
        self.assertIn("t_val_a 576.0 is the moment of no answer in the stretch of window 0 of "
                      "semiblind.1.json (its answers: 573.2, 582.9)", placed.stderr)
        self.assertIn("--t-s 576.0 --t-s-source <full_sample", placed.stderr)
        self.assertEqual(row("--window", "0", "--t-val-a", "590.0").returncode, 2)  # window 1's
        unwalked = row("--window", "2")
        self.assertEqual(unwalked.returncode, 2)
        self.assertIn("has no stretch of window 2 (its stretches: 0, 1)", unwalked.stderr)
        self.assertFalse((self.log_root / "data" / "reviews" / "video-id" / "coordinator.log").exists())

        self.assertEqual(row("--window", "0", "--t-val-a", "582.9").returncode, 0)
        self.assertEqual(row("--window", "1").returncode, 0)  # walked, and no answer passed
        # the rows after the first cite what they rest on
        later = self.run_cli("adjudicate", "--sample-id", "sample-q10", "--iteration", "1",
                             "--window", "0", "--t-s", "590.0", "--t-s-source", "full_sample",
                             "--verified", "na", "--source", "full_sample.1.json")
        self.assertEqual(later.returncode, 0, later.stderr)

        # a round with no launch has no stage A of its own
        ahead = row("--window", "0", "--t-val-a", "582.9", iteration="2")
        self.assertEqual(ahead.returncode, 2)
        self.assertIn("round 2 of sample-q10 has no launch yet", ahead.stderr)
        self.assertIn("--iteration 1", ahead.stderr)
        self.assertEqual(self.spawn("fw0_r2", "sample-q10", "full_window0", iteration=2).returncode, 0)
        self.assertEqual(row("--window", "0", "--t-val-a", "582.9", iteration="2").returncode, 0)
        self.assertEqual(self.finish("fw0_r2").returncode, 0)
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_an_edit_of_the_rubric_reopens_stage_a(self):
        self.trajectory([573.2, 582.9], [590.0])
        stage_a = ["--window", "0", "--verified", "na", "--t-val-a"]
        self.assertEqual(self.adjudicate(*stage_a, "573.2").returncode, 0)
        self.assertEqual(self.adjudicate(*stage_a, "582.9").returncode, 2)
        # the rubric of another window leaves this stretch as it is
        self.assertEqual(self.edit("sample-q10", 'triggers[1].rubric=["an item"]').returncode, 0)
        self.assertIn("disagrees with 573.2", self.adjudicate(*stage_a, "582.9").stderr)

        self.assertEqual(self.edit("sample-q10", 'triggers[0].rubric=["a stricter item"]').returncode, 0)
        corrected = self.adjudicate(*stage_a, "582.9", "--correction", "the rubric changed")
        self.assertEqual(corrected.returncode, 2)
        self.assertIn("Log it without --correction", corrected.stderr)
        reread = self.adjudicate(*stage_a, "582.9")
        self.assertEqual(reread.returncode, 0, reread.stderr)
        self.assertIn("re-adjudicates stage A after the edit of line 3: t_val_a 573.2 -> 582.9",
                      reread.stdout)
        # the new part is a stretch like any other
        self.assertIn("disagrees with 582.9", self.adjudicate(*stage_a, "573.2").stderr)
        check = self.run_cli("check")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("re-adjudication: line 4: sample-q10, round 1, window 0 re-adjudicated after "
                      "the edit of line 3: t_val_a 573.2 -> 582.9, t_val 573.2 -> 582.9", check.stdout)

    def test_an_edit_taken_back_and_an_edit_of_format_1_reopen_nothing(self):
        self.trajectory([573.2, 582.9])
        stage_a = ["--window", "0", "--verified", "na", "--t-val-a"]
        self.assertEqual(self.edit("sample-q10", "reasoning_level=L2").returncode, 0)
        self.assertEqual(self.adjudicate(*stage_a, "573.2").returncode, 0)
        self.assertEqual(self.edit("sample-q10", "reasoning_level=L1").returncode, 0)
        self.assertEqual(self.edit("sample-q10", "reasoning_level=L2").returncode, 0)
        self.assertIn("disagrees with 573.2", self.adjudicate(*stage_a, "582.9").stderr)
        self.write_log({"event": "sample_edit", "sample_id": "sample-q10", "kind": "rubric",
                        "window": 0, "changes": "an item reworded", "source": "y"})
        self.assertIn("disagrees with 573.2", self.adjudicate(*stage_a, "582.9").stderr)
        # the level changed and stayed changed: stage A is read again by the new route
        self.assertEqual(self.edit("sample-q10", "reasoning_level=L1").returncode, 0)
        self.assertEqual(self.adjudicate(*stage_a, "582.9").returncode, 0)

    def stretches(self, *walked):
        """A semi-blind review of sample-q10 as the reviewer leaves it stretch by stretch:
        (the number of the window then, the end of the stretch, the moments of its answers)."""
        path = self.log_root / "data" / "reviews" / "video-id" / "sample-q10" / "semiblind.1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scans": [
            {"idx": idx, "t_to": t_to, "candidates": [{"t": t} for t in moments]}
            for idx, t_to, moments in walked]}), encoding="utf-8")

    def walked_stretch(self, window, until):
        """The launch of the semi-blind reviewer over one stretch, and its finish."""
        self.write_log({"v": 2, "event": "spawn", "agent": "sb", "sample_id": "sample-q10",
                        "role": "semiblind", "iteration": 1, "window": window,
                        "inputs": {"until": until}},
                       {"v": 2, "event": "finish", "agent": "sb", "status": "completed",
                        "summary": "ok"})

    def restructure(self, sample_id, change):
        """An edit of the list of windows through sample-get and the file."""
        self.assertEqual(self.run_cli("sample-get", "--sample-id", sample_id).returncode, 0)
        file = self.edit_file(sample_id)
        new = json.loads(file.read_text(encoding="utf-8"))
        change(new["triggers"])
        for idx, trigger in enumerate(new["triggers"]):
            trigger["idx"] = idx
        file.write_text(json.dumps(new), encoding="utf-8")
        return self.run_cli("sample-edit", "--sample-id", sample_id, "--source", "coordinator.1.md")

    def edits(self):
        return [e for e in self.read_events() if e["event"] == "sample_edit"]

    def test_a_stretch_follows_its_window_when_the_windows_are_renumbered(self):
        self.stretches((0, 110.0, [105.0]), (1, 210.0, [203.0, 206.0]))
        self.walked_stretch(0, 110.0)
        self.walked_stretch(1, 210.0)
        stage_a = ["--verified", "na", "--t-val-a"]
        self.assertEqual(self.adjudicate("--window", "0", *stage_a, "105.0").returncode, 0)
        self.assertEqual(self.adjudicate("--window", "1", *stage_a, "203.0").returncode, 0)

        # an optional window put before window 1: 1 -> 2, 2 -> 3, 3 -> 4
        inserted = self.restructure("sample-q10", lambda windows: windows.insert(
            1, {"required": False, "t_start": 150.0, "t_end": 160.0, "t_ideal": 151.0,
                "response": "the early form of the answer", "rubric": ["the early form"],
                "trigger_modality": ["visual"], "evidence_span": [150.0, 155.0]}))
        self.assertEqual(inserted.returncode, 0, inserted.stderr)
        self.assertIn("next: boundary, window 2 (triggers[2].idx: 1 -> 2): run full_window2 again",
                      inserted.stdout)
        self.assertIn("Nothing is re-adjudicated", inserted.stdout)
        rows = self.edits()
        self.assertEqual([(e["kind"], e["window"]) for e in rows],
                         [("boundary", 1), ("boundary", 2), ("boundary", 3), ("boundary", 4)])
        self.assertEqual(rows[0]["renumbered"], {"1": 2, "2": 3, "3": 4})

        # the rows logged under 1 are the stretch of window 2 now, and it is still open
        moved = self.adjudicate("--window", "2", *stage_a, "206.0")
        self.assertEqual(moved.returncode, 2)
        self.assertIn("disagrees with 203.0", moved.stderr)
        # the new window 1 has not been walked: the stretch saved under 1 is not its own
        unwalked = self.adjudicate("--window", "1", *stage_a, "203.0")
        self.assertEqual(unwalked.returncode, 2)
        self.assertIn("has no stretch of window 1 (its stretches: 0, 2)", unwalked.stderr)
        check = self.run_cli("check")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertNotIn("re-adjudication", check.stdout)

        # an edit of its boundary closes the stretch, and stage A is read again from the
        # stretch the reviewer walked under the old number
        self.assertEqual(self.edit("sample-q10", "triggers[2].t_start=195.0").returncode, 0)
        reread = self.adjudicate("--window", "2", *stage_a, "206.0")
        self.assertEqual(reread.returncode, 0, reread.stderr)
        self.assertIn("t_val_a 203.0 -> 206.0", reread.stdout)

        # the reviewer goes on in the same file, under the new numbers
        self.stretches((0, 110.0, [105.0]), (1, 210.0, [203.0, 206.0]),
                       (1, 160.0, [155.0]), (3, 310.0, [305.0]))
        self.walked_stretch(1, 160.0)
        self.walked_stretch(3, 310.0)
        self.assertEqual(self.adjudicate("--window", "1", *stage_a, "206.0").returncode, 2)
        self.assertEqual(self.adjudicate("--window", "1", *stage_a, "155.0").returncode, 0)
        self.assertEqual(self.adjudicate("--window", "3", *stage_a, "305.0").returncode, 0)
        check = self.run_cli("check")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("sample-q10, round 1, window 2 re-adjudicated after the edit of line",
                      check.stdout)
        self.assertEqual(check.stdout.count("re-adjudication:"), 1)

    def test_the_rows_of_a_removed_window_are_history(self):
        self.stretches((0, 110.0, [105.0]), (1, 210.0, [203.0]))
        self.walked_stretch(0, 110.0)
        self.walked_stretch(1, 210.0)
        stage_a = ["--verified", "na", "--t-val-a"]
        self.assertEqual(self.adjudicate("--window", "0", *stage_a, "105.0").returncode, 0)
        self.assertEqual(self.adjudicate("--window", "1", *stage_a, "203.0").returncode, 0)

        removed = self.restructure("sample-q10", lambda windows: windows.pop(0))

        self.assertEqual(removed.returncode, 0, removed.stderr)
        rows = self.edits()
        self.assertEqual([(e["kind"], e.get("window")) for e in rows],
                         [("boundary", 0), ("boundary", 1), ("boundary", 2), ("boundary", None)])
        self.assertEqual((rows[0]["renumbered"], rows[0]["removed"]),
                         ({"1": 0, "2": 1, "3": 2}, [0]))
        self.assertIn("run a full_window of a window that remains", removed.stdout)
        # the stretch logged under 1 is window 0's now; the row of the removed window is out
        again = self.adjudicate("--window", "0", *stage_a, "105.0")
        self.assertEqual(again.returncode, 2)
        self.assertIn("disagrees with 203.0", again.stderr)
        check = self.run_cli("check")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertNotIn("re-adjudication", check.stdout)
        self.assertIn("not followed by full_window\n", check.stderr)

        # one window review settles its own row and the row of the removal
        self.assertEqual(self.spawn("fw0", "sample-q10", "full_window0").returncode, 0)
        self.assertEqual(self.finish("fw0").returncode, 0)
        check = self.run_cli("check")
        self.assertNotIn("not followed by full_window\n", check.stderr)
        self.assertNotIn("not followed by full_window0", check.stderr)
        self.assertIn("not followed by full_window1", check.stderr)

    def test_a_review_an_edit_owes_follows_its_window(self):
        self.assertEqual(self.edit("sample-q10", "triggers[1].t_start=195.0").returncode, 0)
        self.assertEqual(self.edit("sample-q11", "triggers[3].t_start=395.0").returncode, 0)
        self.assertIn("line 1: edit of sample-q10 not followed by full_window1",
                      self.run_cli("check").stderr)

        # a window put before it: the review is owed under the new number
        self.assertEqual(self.restructure("sample-q10", lambda windows: windows.insert(
            0, {"required": False, "t_start": 50.0, "t_end": 60.0, "t_ideal": 51.0,
                "response": "the early form of the answer", "rubric": ["the early form"],
                "trigger_modality": ["visual"], "evidence_span": [50.0, 55.0]})).returncode, 0)
        # the window itself removed: its review is owed no more
        self.assertEqual(self.restructure("sample-q11", lambda windows: windows.pop(3)).returncode, 0)

        check = self.run_cli("check")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("line 1: edit of sample-q10 not followed by full_window2\n", check.stderr)
        self.assertNotIn("line 2: edit of sample-q11", check.stderr)
        removal = len(self.read_events())
        self.assertIn(f"line {removal}: edit of sample-q11 not followed by full_window\n",
                      check.stderr)

    def judge_server(self, credit):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeJudge)
        server.credit = credit
        server.lock, server.calls = threading.Lock(), 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def blind_sample(self, sample_id="sample-q05", flag=False, rubric=("item a", "item b")):
        records = self.records()
        records[sample_id]["validation"] = {"status": "validated", "blind_solved": flag}
        records[sample_id]["question"] = "What is it?"
        records[sample_id]["question_time"] = 100.0
        records[sample_id]["triggers"] = [{"idx": 0, "required": True, "t_start": 100.0,
                                           "t_end": 110.0, "rubric": list(rubric)}]
        self.write_records(*records.values())

    def semiblind(self, agent, sample_id, iteration, answer):
        ws = self.workspace(agent, sample_id, "semiblind")
        launched = self.run_cli("spawn", "--agent", agent, "--sample-id", sample_id, "--role",
                                "semiblind", "--iteration", str(iteration), "--model", "local",
                                "--reasoning-effort", "default", "--workspace", str(ws))
        self.assertEqual(launched.returncode, 0, launched.stderr)
        review = self.log_root / "data" / "reviews" / "video-id" / sample_id / f"semiblind.{iteration}.json"
        review.parent.mkdir(parents=True, exist_ok=True)
        review.write_text(json.dumps({"role": "semiblind", "sample_id": sample_id,
                                      "iteration": iteration, "prior_answer": answer}))
        finished = self.finish(agent, "--artifact", str(review))
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("blind-judge", finished.stdout)
        return review

    def blind_judge(self, server, sample_id, review):
        return self.run_cli("blind-judge", "--sample-id", sample_id, "--review", str(review),
                            "--base-url", f"http://127.0.0.1:{server.server_address[1]}/v1")

    def set_flag(self, sample_id, flag):
        records = self.records()
        records[sample_id]["validation"]["blind_solved"] = flag
        self.write_records(*records.values())

    def test_a_blind_answer_the_judge_credits_sets_the_flag_unless_a_ruling_says_why(self):
        self.blind_sample()
        review = self.semiblind("sb_r1", "sample-q05", 1, "It is a and b.")
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no judge verdict on the current rubric", result.stderr)

        judged = self.blind_judge(self.judge_server(True), "sample-q05", review)
        self.assertEqual(judged.returncode, 0, judged.stderr)
        self.assertIn("credited every required item", judged.stdout)
        self.assertIn("prior_answer_assumptions", judged.stdout)
        event = self.read_events()[-1]
        self.assertEqual((event["event"], event["met"], event["items_met"]),
                         ("blind_judge", True, ["w0.1", "w0.2"]))
        self.assertTrue((self.log_root / event["result"]).is_file())
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("but blind_solved is false and no blind-ruling explains it", result.stderr)

        refused = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--basis",
                               "screen-guess", "--items", "w0.3", "--text",
                               "the screen may show 4 kΩ instead of 1 kΩ, then 4 ms")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("w0.1, w0.2", refused.stderr)
        ruled = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--basis",
                             "screen-guess", "--items", "w0.2", "--text",
                             "the screen may show 4 kΩ instead of 1 kΩ, then 4 ms")
        self.assertEqual(ruled.returncode, 0, ruled.stderr)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_item_is_met_when_most_judge_runs_credit_it(self):
        self.blind_sample(flag=True)
        review = self.semiblind("sb_r1", "sample-q05", 1, "It is a and b.")
        server = self.judge_server([True, {"i1"}, True])
        self.assertEqual(self.blind_judge(server, "sample-q05", review).returncode, 0)
        event = self.read_events()[-1]
        self.assertEqual(server.calls, 3)
        self.assertEqual(event["votes"], {"w0.1": "3/3", "w0.2": "2/3"})
        self.assertTrue(event["met"])

        # the same answer is not judged again by the same judge on the same rubric
        again = self.blind_judge(server, "sample-q05", review)
        self.assertEqual(again.returncode, 2)
        self.assertIn("judged already on this rubric by this judge", again.stderr)
        self.assertEqual(server.calls, 3)

        # another round, two of three runs against the second item: it is unmet
        second = self.semiblind("sb_r2", "sample-q05", 2, "It is a, and b perhaps.")
        server.credit, server.calls = [{"i1"}, {"i1"}, True], 0
        self.assertEqual(self.blind_judge(server, "sample-q05", second).returncode, 0)
        self.assertEqual(self.read_events()[-1]["items_unmet"], ["w0.2"])
        self.assertEqual(self.run_cli("check", "--final").returncode, 0)

    def test_a_verdict_of_a_single_judge_run_does_not_count(self):
        self.blind_sample(flag=True)
        review = self.semiblind("sb_r1", "sample-q05", 1, "It is a and b.")
        judge = self.judge_server(True)
        self.assertEqual(self.blind_judge(judge, "sample-q05", review).returncode, 0)
        # as the first verdicts were logged: one run, no runs or votes field
        path = self.log_root / "data" / "reviews" / "video-id" / "coordinator.log"
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        for event in lines:
            if event.get("event") == "blind_judge":
                del event["runs"], event["votes"]
        path.write_text("".join(json.dumps(e) + "\n" for e in lines))
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no judge verdict on the current rubric", result.stderr)
        refused = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--basis",
                               "look-only", "--items", "w0.1", "--text",
                               "item a names the colour of the curve only")
        self.assertIn("run blind-judge first", refused.stderr)
        self.assertEqual(self.blind_judge(judge, "sample-q05", review).returncode, 0)
        self.assertEqual(self.run_cli("check", "--final").returncode, 0)

    def test_blind_judge_refuses_an_empty_answer(self):
        self.blind_sample()
        review = self.semiblind("sb_r1", "sample-q05", 1, "  ")
        judge = self.judge_server(True)
        result = self.blind_judge(judge, "sample-q05", review)
        self.assertEqual(result.returncode, 2)
        self.assertIn("has no prior_answer: send the semi-blind reviewer back", result.stderr)
        self.assertEqual(judge.calls, 0)

    def test_a_credited_blind_answer_needs_no_ruling_when_the_flag_is_true(self):
        self.blind_sample(flag=True)
        review = self.semiblind("sb_r1", "sample-q05", 1, "It is a and b.")
        self.assertEqual(self.blind_judge(self.judge_server(True), "sample-q05", review).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_rewrite_that_keeps_the_rubric_keeps_the_flag(self):
        self.blind_sample(flag=True)
        first = self.semiblind("sb_r1", "sample-q05", 1, "It is a and b.")
        self.assertEqual(self.blind_judge(self.judge_server(True), "sample-q05", first).returncode, 0)
        # the when-clause is rewritten; the next run refuses to answer
        self.set_flag("sample-q05", False)
        second = self.semiblind("sb_r2", "sample-q05", 2, "I cannot know without the video.")
        self.assertEqual(self.blind_judge(self.judge_server(False), "sample-q05", second).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not clear the flag", result.stderr)
        self.assertIn("semiblind.1.json", result.stderr)

        # a repair that changes what the answer has to contain: the old verdicts do not apply
        self.blind_sample(flag=False, rubric=("item c read off the screen",))
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("round 2 has no judge verdict", result.stderr)
        judge = self.judge_server(False)
        self.assertEqual(self.blind_judge(judge, "sample-q05", second).returncode, 0)
        # the first answer is judged again too: it may meet the new rubric as well
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("semiblind.1.json was judged (line", result.stderr)
        self.assertEqual(self.blind_judge(judge, "sample-q05", first).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_cosmetic_rubric_edit_keeps_the_flag_once_the_answers_are_judged_again(self):
        self.blind_sample(flag=True)
        first = self.semiblind("sb_r1", "sample-q05", 1, "It is a and b.")
        judge = self.judge_server(True)
        self.assertEqual(self.blind_judge(judge, "sample-q05", first).returncode, 0)
        self.set_flag("sample-q05", False)
        second = self.semiblind("sb_r2", "sample-q05", 2, "I cannot know without the video.")
        judge.credit = False
        self.assertEqual(self.blind_judge(judge, "sample-q05", second).returncode, 0)
        # a comma in the rubric: the hash changes, what the answer has to contain does not
        self.blind_sample(flag=False, rubric=("item a,", "item b"))
        self.assertEqual(self.blind_judge(judge, "sample-q05", second).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("semiblind.1.json was judged (line", result.stderr)
        judge.credit = True
        self.assertEqual(self.blind_judge(judge, "sample-q05", first).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not clear the flag", result.stderr)
        # the rounds keep their order however late the first one was judged again
        ruled = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--review", str(first),
                             "--basis", "repaired", "--items", "w0.1,w0.2", "--text",
                             "the old wording named the resistance, the new one does not")
        self.assertEqual(ruled.returncode, 0, ruled.stderr)
        self.assertEqual(self.run_cli("check", "--final").returncode, 0)

    def test_a_rewrite_that_withholds_what_the_old_wording_gave_is_ruled_repaired(self):
        self.blind_sample(flag=True)
        first = self.semiblind("sb_r1", "sample-q05", 1, "With the 4 kΩ the question names: 12 ms.")
        judge = self.judge_server(True)
        self.assertEqual(self.blind_judge(judge, "sample-q05", first).returncode, 0)
        refused = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--review",
                               str(first), "--basis", "repaired", "--items", "w0.1", "--text",
                               "the old wording named the resistance, the new one does not")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("once the new wording has its own judged round", refused.stderr)

        self.set_flag("sample-q05", False)
        second = self.semiblind("sb_r2", "sample-q05", 2, "The resistance is on screen; I cannot say.")
        judge.credit = False
        self.assertEqual(self.blind_judge(judge, "sample-q05", second).returncode, 0)
        self.assertIn("--basis repaired", self.run_cli("check", "--final").stderr)
        missing = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--review",
                               "semiblind.9.json", "--basis", "repaired", "--items", "w0.1",
                               "--text", "the old wording named the resistance, the new one does not")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("the judged rounds are", missing.stderr)
        ruled = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--review", str(first),
                             "--basis", "repaired", "--items", "w0.1,w0.2", "--text",
                             "the old wording named the resistance, the new one does not")
        self.assertEqual(ruled.returncode, 0, ruled.stderr)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_true_flag_the_judge_does_not_support_needs_a_look_only_ruling(self):
        self.blind_sample(flag=True)
        review = self.semiblind("sb_r1", "sample-q05", 1, "It is a; the colour I cannot tell.")
        self.assertEqual(self.blind_judge(self.judge_server({"i1"}), "sample-q05", review).returncode, 0)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unmet: w0.2", result.stderr)

        refused = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--basis",
                               "video-content", "--items", "w0.1", "--text",
                               "the example is the video's own construction")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("did not credit", self.run_cli(
            "blind-ruling", "--sample-id", "sample-q05", "--basis", "look-only", "--items",
            "w0.1", "--text", "item b names the colour of the curve only").stderr)
        ruled = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--basis", "look-only",
                             "--items", "w0.2", "--text", "item b names the colour of the curve only")
        self.assertEqual(ruled.returncode, 0, ruled.stderr)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_look_only_names_every_item_the_judge_did_not_credit(self):
        self.blind_sample(flag=True, rubric=("item a", "item b", "item c"))
        review = self.semiblind("sb_r1", "sample-q05", 1, "It is a; I cannot tell the rest.")
        self.assertEqual(self.blind_judge(self.judge_server({"i1"}), "sample-q05", review).returncode, 0)
        refused = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--basis", "look-only",
                               "--items", "w0.2", "--text", "item b names the colour of the curve only")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("look-only names every item the judge did not credit", refused.stderr)
        ruled = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--basis", "look-only",
                             "--items", "w0.2,w0.3", "--text",
                             "items b and c name the colours of the curves only")
        self.assertEqual(ruled.returncode, 0, ruled.stderr)
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blind_judge_refuses_another_samples_review_and_a_ruling_without_a_verdict(self):
        self.blind_sample()
        review = self.semiblind("sb_r1", "sample-q05", 1, "It is a and b.")
        result = self.blind_judge(self.judge_server(True), "sample-q06", review)
        self.assertEqual(result.returncode, 2)
        self.assertIn("give the semiblind.<round>.json of sample-q06", result.stderr)
        result = self.run_cli("blind-ruling", "--sample-id", "sample-q05", "--basis",
                              "screen-guess", "--items", "w0.1", "--text",
                              "the screen may show another circuit entirely")
        self.assertEqual(result.returncode, 2)
        self.assertIn("run blind-judge first", result.stderr)

    def test_a_semiblind_launch_before_the_judge_existed_owes_no_verdict(self):
        self.blind_sample()
        self.semiblind("sb_r1", "sample-q05", 1, "It is a and b.")
        path = self.log_root / "data" / "reviews" / "video-id" / "coordinator.log"
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        for event in lines:
            event["ts"] = "2026-10-15T07:57:04+03:00"
        path.write_text("".join(json.dumps(e) + "\n" for e in lines))
        result = self.run_cli("check", "--final")
        self.assertEqual(result.returncode, 0, result.stderr)

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
