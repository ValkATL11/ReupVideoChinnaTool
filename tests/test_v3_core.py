"""
tests/test_v3_core.py
======================
Unit tests for ReupTool V3 Core Modules.
"""

import unittest
from pathlib import Path
import tempfile
import shutil

from app.core.config import ConfigManager, CONFIG_SCHEMA_VERSION
from app.core.project import generate_project_id, validate_project_id, Project, ProjectManager
from app.core.key_manager import ApiKeyPool, mask_key
from app.core.prompt_engine import PromptGenerator, PromptLibrary, MANDATORY_FILLER_WORDS
from app.editor.editor_config import EditorOverlayConfig


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cfg_path = Path(self.temp_dir) / "test_config.json"
        self.mgr = ConfigManager(self.cfg_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_schema_version(self):
        self.assertEqual(self.mgr.get("schema_version"), CONFIG_SCHEMA_VERSION)

    def test_get_set_dot_notation(self):
        self.mgr.set("modules.dubber.speed", 1.25)
        self.assertEqual(self.mgr.get("modules.dubber.speed"), 1.25)


class TestProjectManager(unittest.TestCase):
    def test_generate_and_validate_project_id(self):
        pid = generate_project_id()
        self.assertTrue(validate_project_id(pid))
        self.assertTrue(pid.startswith("PRJ-"))

    def test_invalid_project_ids(self):
        self.assertFalse(validate_project_id(""))
        self.assertFalse(validate_project_id("PRJ/123"))
        self.assertFalse(validate_project_id("PRJ*123"))
        self.assertFalse(validate_project_id(".."))


class TestKeyManager(unittest.TestCase):
    def test_mask_key(self):
        self.assertEqual(mask_key("gsk_1234567890abcdef"), "gsk_************cdef")

    def test_key_pool_rotation(self):
        pool = ApiKeyPool("test_provider")
        pool.keys = [
            {"id": "k1", "key": "KEY_1", "enabled": True, "error_count": 0, "cooldown_until": 0},
            {"id": "k2", "key": "KEY_2", "enabled": True, "error_count": 0, "cooldown_until": 0}
        ]
        pool.current_index = 0

        self.assertEqual(pool.get_active_key(), "KEY_1")
        next_key = pool.mark_error("KEY_1", cooldown_sec=100)
        self.assertEqual(next_key, "KEY_2")


class TestPromptEngine(unittest.TestCase):
    def test_prompt_generator_core_rules(self):
        prompt = PromptGenerator.generate("Dịch phim tự nhiên")
        # Check Core Rule 1
        self.assertIn("CORE RULE 1", prompt)
        self.assertIn("Duration (giây) × 3.5", prompt)

        # Check Core Rule 2
        self.assertIn("CORE RULE 2", prompt)
        for word in ["thì", "là", "mà", "rằng"]:
            self.assertIn(word, prompt)


class TestEditorConfig(unittest.TestCase):
    def test_overlay_config_percentage(self):
        cfg = EditorOverlayConfig("PRJ-TEST")
        cfg.add_subtitle(y_pct=88.5, text="Hello")
        cfg.add_blur(enabled=True)

        d = cfg.to_dict()
        self.assertEqual(d["subtitles"][0]["y_pct"], 88.5)
        self.assertTrue(d["blur_regions"][0]["enabled"])

    def test_crud_and_multi_item(self):
        cfg = EditorOverlayConfig("PRJ-TEST")
        s1 = cfg.add_subtitle(text="A")
        s2 = cfg.add_subtitle(text="B")
        self.assertEqual(len(cfg.subtitles), 2)

        cfg.update_subtitle(s1["id"], text="A-edited")
        self.assertEqual(cfg.get_subtitle(s1["id"])["text"], "A-edited")

        cfg.remove_subtitle(s2["id"])
        self.assertEqual(len(cfg.subtitles), 1)

    def test_legacy_v1_migration(self):
        cfg = EditorOverlayConfig("PRJ-TEST")
        legacy_data = {
            "project_id": "PRJ-TEST",
            "subtitle": {"enabled": True, "font_name": "Arial", "font_size": 22,
                         "outline_width": 2, "pos_x_pct": 50.0, "pos_y_pct": 90.0},
            "blur_region": {"enabled": True, "blur_strength": 15, "x_pct": 5.0,
                             "y_pct": 5.0, "width_pct": 20.0, "height_pct": 10.0},
            "logo": {"enabled": True, "image_path": "logo.png", "x_pct": 1.0,
                     "y_pct": 1.0, "width_pct": 10.0, "height_pct": 10.0, "opacity": 0.5},
        }
        cfg.load_dict(legacy_data)
        self.assertEqual(len(cfg.subtitles), 1)
        self.assertEqual(len(cfg.blur_regions), 1)
        self.assertEqual(len(cfg.logos), 1)
        self.assertEqual(cfg.subtitles[0]["y_pct"], 90.0)
        self.assertEqual(cfg.logos[0]["image_path"], "logo.png")


if __name__ == "__main__":
    unittest.main()
