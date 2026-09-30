import tempfile
import unittest
from pathlib import Path

from tools import prepare_review_workspace as workspace


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

    def test_refuses_a_workspace_owned_by_another_video(self):
        out = workspace.ROOT / ".review_ws" / "other-video" / "question" / "full_sample"
        out.mkdir(parents=True)

        with self.assertRaisesRegex(ValueError, "video id"):
            workspace.cleanup_workspace("video", out)

        self.assertTrue(out.exists())


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

            self.assertEqual(sheet.name, "sheet_t000499-t000504.jpg")
            with Image.open(sheet) as img:
                self.assertEqual(img.size, (4 * 320, 2 * 180))


if __name__ == "__main__":
    unittest.main()
