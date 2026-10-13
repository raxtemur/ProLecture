import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import prepare_review_workspace as workspace
from tools import review_inputs


class CleanupWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.original_root = workspace.ROOT
        workspace.ROOT = Path(self.tmp.name)
        self.addCleanup(setattr, workspace, "ROOT", self.original_root)

    def test_removes_one_reviewer_workspace_and_prunes_empty_parents(self):
        out = (workspace.ROOT / ".review_ws" / "video" / "question" / "full_sample")
        out.mkdir(parents=True)
        (out / "frames").mkdir()
        (out / "frames" / "t000001.jpg").write_bytes(b"frame")

        workspace.cleanup_workspace("video", out)

        self.assertFalse(out.exists())
        self.assertFalse((workspace.ROOT / ".review_ws" / "video").exists())
        self.assertTrue((workspace.ROOT / ".review_ws").exists())

    def test_refuses_to_remove_a_path_outside_review_root(self):
        out = workspace.ROOT / "tmp" / "question" / "full_sample"
        out.mkdir(parents=True)

        with self.assertRaisesRegex(ValueError, "inside .*\\.review_ws"):
            workspace.cleanup_workspace("video", out)

        self.assertTrue(out.exists())

    def test_refuses_to_remove_a_video_or_question_directory(self):
        question = workspace.ROOT / ".review_ws" / "video" / "question"
        question.mkdir(parents=True)

        with self.assertRaisesRegex(ValueError, "reviewer workspace"):
            workspace.cleanup_workspace("video", question)

        self.assertTrue(question.exists())

    def test_removes_the_inputs_note_with_the_workspace(self):
        out = (workspace.ROOT / ".review_ws" / "video" / "question" / "probe_frame1")
        out.mkdir(parents=True)
        note = review_inputs.write_sidecar(out, {"sample_id": "q"})

        workspace.cleanup_workspace("video", out)

        self.assertFalse(note.exists())
        self.assertFalse((workspace.ROOT / ".review_ws" / "video").exists())

    def test_refuses_a_workspace_owned_by_another_video(self):
        out = workspace.ROOT / ".review_ws" / "other-video" / "question" / "full_sample"
        out.mkdir(parents=True)

        with self.assertRaisesRegex(ValueError, "video id"):
            workspace.cleanup_workspace("video", out)

        self.assertTrue(out.exists())


class ReviewInputsTest(unittest.TestCase):
    RECORD = {"id": "q01", "triggers": [
        {"idx": 0, "required": True, "t_start": 100.0, "t_end": 110.0},
        {"idx": 1, "required": False, "t_start": 150.0, "t_end": 160.0},
        {"idx": 2, "required": True, "t_start": 200.0, "t_end": 215.0}]}

    def test_derives_each_role_from_the_record(self):
        derive = review_inputs.derive_inputs
        for role in ("probe_text", "probe_vision", "probe_full"):
            self.assertEqual(derive(role, self.RECORD), {"until": 215.0}, role)
        self.assertEqual(derive("probe_frame", self.RECORD, 2), {"frame": 207.5})
        self.assertEqual(derive("semiblind", self.RECORD, 0), {"until": 110.0})
        self.assertEqual(derive("semiblind", self.RECORD, 1), {"until": 160.0},
                         "a semi-blind stretch ends at an optional window too")
        self.assertEqual(derive("probe_verify", self.RECORD, until=96.0), {"until": 96.0})
        self.assertEqual(derive("full_window", self.RECORD, duration=900.0), {"until": 900.0})
        with self.assertRaisesRegex(review_inputs.InputsError, "optional"):
            derive("probe_frame", self.RECORD, 1)
        with self.assertRaisesRegex(review_inputs.InputsError, "needs --window"):
            derive("semiblind", self.RECORD)
        with self.assertRaisesRegex(review_inputs.InputsError, "needs --until"):
            derive("probe_verify", self.RECORD)

    def test_a_record_in_several_files_needs_the_file_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "annotations" / "partial").mkdir(parents=True)
            line = json.dumps(self.RECORD) + "\n"
            (root / "data" / "annotations" / "v.jsonl").write_text(line, encoding="utf-8")
            (root / "data" / "annotations" / "partial" / "v.full.jsonl").write_text(
                line, encoding="utf-8")
            with self.assertRaisesRegex(review_inputs.InputsError, "several files"):
                review_inputs.find_record(root, "q01")
            path, found = review_inputs.find_record(
                root, "q01", root / "data" / "annotations" / "v.jsonl")
            self.assertEqual(found["id"], "q01")
            with self.assertRaisesRegex(review_inputs.InputsError, "no record"):
                review_inputs.find_record(root, "q02")

    def test_record_sha_changes_with_any_edit(self):
        edited = json.loads(json.dumps(self.RECORD))
        edited["triggers"][0]["t_start"] = 99.0
        self.assertNotEqual(review_inputs.record_sha(self.RECORD),
                            review_inputs.record_sha(edited))

    def test_out_with_a_space_is_refused(self):
        script = Path(workspace.__file__)
        result = subprocess.run([sys.executable, str(script), "vid", "--out", "ws/q06 full_sample",
                                 "--until", "5"], capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains a space", result.stderr)


class SheetTest(unittest.TestCase):
    def test_tiles_the_frames_into_one_image_and_skips_missing_seconds(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            frames = Path(tmp)
            times = workspace.dense_times(499, 505, 1)
            for t in times:
                if t != 502:
                    Image.new("RGB", (640, 360), "teal").save(frames / workspace.frame_name(t))

            sheet = workspace.build_sheet(frames, times, cols=4, cell_w=320)

            self.assertEqual(sheet.name, "sheet_t000499-t000505.jpg")
            with Image.open(sheet) as img:
                self.assertEqual(img.size, (4 * 320, 2 * 180))


class EdgeFramesTest(unittest.TestCase):
    """The frames at both edges of a stretch are always in the folder, and none past it."""

    BUNDLE_FRAMES = (0.0, 10.4, 20.0, 84.6, 90.0)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in (("ROOT", root), ("grab_frame", self.fake_grab)):
            self.addCleanup(setattr, workspace, name, getattr(workspace, name))
            setattr(workspace, name, value)
        frames = root / "data" / "bundles" / "vid" / "frames"
        frames.mkdir(parents=True)
        listed = []
        for t in self.BUNDLE_FRAMES:
            path = frames / workspace.frame_name(t)
            path.write_text(f"bundle {t}", encoding="utf-8")
            listed.append({"t": t, "path": str(path.relative_to(root))})
        self.bundle = {"video_id": "vid", "frames": listed, "transcript": [], "duration": 120.0}
        (frames.parent / "bundle.json").write_text(json.dumps(self.bundle), encoding="utf-8")
        (root / "data" / "videos" / "vid").mkdir(parents=True)
        (root / "data" / "videos" / "vid" / "vid.mp4").write_bytes(b"")
        self.out = root / "ws"

    @staticmethod
    def fake_grab(mp4, t, target):
        target.write_text(f"video {t}", encoding="utf-8")
        return True

    def seconds(self):
        return {int(p.stem[1:]): p.read_text(encoding="utf-8")
                for p in (self.out / "frames").glob("t*.jpg")}

    def run_main(self, *argv):
        original = sys.argv
        sys.argv = ["prepare_review_workspace.py", "vid", "--out", str(self.out), *argv]
        try:
            workspace.main()
        finally:
            sys.argv = original

    def test_the_grid_ends_on_its_edge(self):
        self.assertEqual(workspace.dense_times(84, 85.2, 1), [84.0, 85.2])
        self.assertEqual(workspace.dense_times(499, 502, 1), [499.0, 500.0, 501.0, 502.0])
        self.assertEqual(workspace.dense_times(946, 946, 1), [946.0])

    def test_until_holds_both_edges_and_nothing_later(self):
        self.run_main("--until", "85.2")
        seen = self.seconds()
        self.assertEqual(seen[0], "bundle 0.0")
        self.assertEqual(seen[85], "video 85.2", "the edge replaces the scene frame of its second")
        self.assertLessEqual(max(seen), 85)

    def test_thinning_keeps_the_edges(self):
        self.out.mkdir()
        workspace.copy_sparse(self.bundle, self.out, 5.0, 50.0, 1)
        seen = self.seconds()
        self.assertEqual(seen[5], "video 5.0")
        self.assertEqual(seen[50], "video 50.0")
        self.assertEqual(len(seen), 3)

    def test_dense_is_clamped_to_until_and_ends_on_it(self):
        self.run_main("--until", "85.2")
        self.run_main("--dense", "80", "100", "--step", "1")
        seen = self.seconds()
        self.assertEqual(seen[85], "video 85.2")
        self.assertLessEqual(max(seen), 85)
        self.assertTrue(all(seen[t] == f"video {float(t)}" for t in range(80, 85)))

    def test_the_index_names_the_edges_cut_into_the_folder(self):
        self.run_main("--until", "85.2", "--index-only")
        index = (self.out / "frames.md").read_text(encoding="utf-8")
        self.assertIn("in this folder: frames/t000085.jpg", index)
        self.assertNotIn("84.6", index)
        self.assertEqual(index.count("t000000.jpg"), 1)

    def test_a_frame_folder_rebuilt_holds_only_the_new_frame(self):
        self.run_main("--frame", "20")
        self.run_main("--frame", "10.4")
        self.assertEqual(self.seconds(), {10: "video 10.4"})


if __name__ == "__main__":
    unittest.main()
