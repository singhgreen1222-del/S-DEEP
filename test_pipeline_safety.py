import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline


class PipelineSafetyTests(unittest.TestCase):
    def test_load_recovers_from_corrupt_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text("{broken", encoding="utf-8")
            with patch.object(pipeline, "STATE_F", state_file):
                state = pipeline.load()
            self.assertEqual(state["jobs"], {})
            self.assertEqual(state["recent_looks"], [])

    def test_save_is_valid_json_and_excludes_runtime_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            with patch.object(pipeline, "STATE_F", state_file):
                pipeline.save({"jobs": {"a": {"id": "a"}}, "settings": {"secret": "not-persisted"}})
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertIn("jobs", saved)
            self.assertNotIn("settings", saved)
            self.assertFalse(state_file.with_suffix(".json.tmp").exists())

    def test_script_validator_rejects_bad_scene_count_and_empty_text(self):
        good = {"title": "Market update", "description": "Description",
                "scenes": [{"text": "Scene one"}, {"text": "Scene two"},
                           {"text": "Scene three"}, {"text": "Scene four"}]}
        self.assertIs(pipeline.validate_script(good, "short"), good)
        with self.assertRaises(ValueError):
            pipeline.validate_script({"title": "Bad", "scenes": [{"text": "Only one"}]}, "short")
        bad_text = {"title": "Bad", "scenes": [{"text": " "}] * 4}
        with self.assertRaises(ValueError):
            pipeline.validate_script(bad_text, "short")

    def test_dryrun_does_not_mutate_real_schedule_or_persist_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out, work, looks = root / "out", root / "work", root / "looks"
            out.mkdir(); work.mkdir(); looks.mkdir()
            (looks / "look.jpg").write_bytes(b"image")
            state = {"jobs": {"real_job": {"id": "real_job", "kind": "short"}},
                     "recent_looks": [], "settings": {"ref": "", "voice": "hi-IN-MadhurNeural", "intro": False}}
            original = json.dumps(state, sort_keys=True)
            with patch.object(pipeline, "OUT", out), patch.object(pipeline, "WORK", work), \
                 patch.object(pipeline, "LOOKS", looks), patch.object(pipeline, "SCRIPTS", work / "scripts"), \
                 patch.object(pipeline, "fetch_news", return_value=[{"title": "Test", "link": "https://example.com"}]), \
                 patch.object(pipeline, "_short", return_value={"title": "Test", "scenes": [], "mode": "short"}), \
                 patch.object(pipeline, "ensure_looks"), patch.object(pipeline, "IST", pipeline.IST), \
                 patch.object(pipeline, "STATE_F", root / "state.json"):
                import make_video
                with patch.object(make_video, "render_video", return_value=out / "dryrun.mp4"), \
                     patch.object(make_video, "make_thumb"):
                    pipeline.dryrun(state, log=lambda *_: None)
            self.assertEqual(json.dumps(state, sort_keys=True), original)
            self.assertFalse((root / "state.json").exists())
            self.assertTrue((work / "dryrun_scripts").is_dir())


if __name__ == "__main__":
    unittest.main()
