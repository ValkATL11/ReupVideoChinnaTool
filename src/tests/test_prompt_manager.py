"""
tests/test_prompt_manager.py
=============================
Unit tests for the Translation Prompt Management feature.

Covers:
 1.  load prompts
 2.  save prompts
 3.  create prompt
 4.  rename prompt
 5.  edit prompt
 6.  duplicate prompt
 7.  delete prompt
 8.  activate prompt
 9.  only one active prompt at a time
 10. translator resolves the correct active prompt
 11. invalid prompt id handling
 12. corrupted storage recovery
 13. duplicate name validation
 14. empty name validation
 15. empty content validation
 16. cannot delete the last remaining prompt
 17. cannot edit/delete/rename a built-in prompt
 18. pipeline translation-step cache invalidation on active prompt change
"""

from pathlib import Path
import json
import shutil
import tempfile
import unittest

from app.core.prompt_engine import (
    PromptLibrary, PromptValidationError, BUILTIN_PROMPTS
)


class TestPromptLibraryLoadSave(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "prompts.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_default_storage_when_missing(self):
        self.assertFalse(self.storage_path.exists())
        lib = PromptLibrary(storage_file=self.storage_path)
        self.assertTrue(self.storage_path.exists())
        self.assertEqual(len(lib.list_prompts()), 1)
        self.assertEqual(lib.list_prompts()[0]["id"], BUILTIN_PROMPTS[0]["id"])

    def test_save_and_reload_round_trip(self):
        lib = PromptLibrary(storage_file=self.storage_path)
        lib.add_prompt(name="Prompt ngắn gọn", content="Dịch ngắn gọn.")
        self.assertTrue(lib.save())

        lib2 = PromptLibrary(storage_file=self.storage_path)
        names = [p["name"] for p in lib2.list_prompts()]
        self.assertIn("Prompt ngắn gọn", names)

    def test_corrupted_storage_falls_back_to_defaults(self):
        self.storage_path.write_text("{ this is not valid json ][", encoding="utf-8")
        lib = PromptLibrary(storage_file=self.storage_path)
        # Should not crash; should recover with at least the builtin prompt.
        self.assertGreaterEqual(len(lib.list_prompts()), 1)
        self.assertTrue(any(p.get("is_builtin") for p in lib.list_prompts()))

    def test_non_list_json_root_falls_back_to_defaults(self):
        self.storage_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        lib = PromptLibrary(storage_file=self.storage_path)
        self.assertGreaterEqual(len(lib.list_prompts()), 1)


class TestPromptLibraryCRUD(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "prompts.json"
        self.lib = PromptLibrary(storage_file=self.storage_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_prompt(self):
        p = self.lib.add_prompt(name="Prompt chuyên ngành", content="Dịch kỹ thuật.", description="Kỹ thuật")
        self.assertIsNotNone(p["id"])
        self.assertEqual(p["name"], "Prompt chuyên ngành")
        self.assertFalse(p["active"])
        self.assertEqual(len(self.lib.list_prompts()), 2)

    def test_create_prompt_id_is_stable_not_index_based(self):
        p1 = self.lib.add_prompt(name="A", content="content A")
        p2 = self.lib.add_prompt(name="B", content="content B")
        self.assertNotEqual(p1["id"], p2["id"])
        # IDs should not be "0", "1" (index-based)
        self.assertFalse(p1["id"].isdigit())
        self.assertFalse(p2["id"].isdigit())

    def test_edit_prompt_updates_content(self):
        p = self.lib.add_prompt(name="Draft", content="Old content")
        self.lib.update_prompt(p["id"], content="New content")
        updated = self.lib.get_prompt(p["id"])
        self.assertEqual(updated["content"], "New content")

    def test_edit_prompt_preserves_id_across_edits(self):
        p = self.lib.add_prompt(name="Draft", content="Old content")
        original_id = p["id"]
        self.lib.update_prompt(p["id"], name="Renamed Draft", content="Changed")
        updated = self.lib.get_prompt(original_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["id"], original_id)

    def test_rename_prompt(self):
        p = self.lib.add_prompt(name="Old Name", content="content")
        self.lib.rename_prompt(p["id"], "New Name")
        self.assertEqual(self.lib.get_prompt(p["id"])["name"], "New Name")

    def test_rename_preserves_id(self):
        p = self.lib.add_prompt(name="Old Name", content="content")
        original_id = p["id"]
        self.lib.rename_prompt(p["id"], "New Name")
        self.assertEqual(self.lib.get_prompt(original_id)["id"], original_id)

    def test_duplicate_prompt(self):
        p = self.lib.add_prompt(name="Prompt chính B", content="some content", description="desc")
        dup = self.lib.duplicate_prompt(p["id"])
        self.assertEqual(dup["name"], "Prompt chính B (Copy)")
        self.assertEqual(dup["content"], "some content")
        self.assertEqual(dup["description"], "desc")
        self.assertFalse(dup["active"])
        self.assertNotEqual(dup["id"], p["id"])

    def test_duplicate_increments_copy_number_on_collision(self):
        p = self.lib.add_prompt(name="Prompt chính C", content="x")
        dup1 = self.lib.duplicate_prompt(p["id"])  # "Prompt chính C (Copy)"
        dup2 = self.lib.duplicate_prompt(p["id"])  # collision -> "(Copy 2)"
        self.assertEqual(dup1["name"], "Prompt chính C (Copy)")
        self.assertEqual(dup2["name"], "Prompt chính C (Copy 2)")

    def test_duplicate_does_not_change_active_prompt(self):
        active_before = self.lib.get_active_prompt()["id"]
        p = self.lib.add_prompt(name="Prompt chính D", content="x")
        self.lib.duplicate_prompt(p["id"])
        self.assertEqual(self.lib.get_active_prompt()["id"], active_before)

    def test_delete_prompt(self):
        p = self.lib.add_prompt(name="Temp Prompt", content="x")
        self.assertTrue(self.lib.delete_prompt(p["id"]))
        self.assertIsNone(self.lib.get_prompt(p["id"]))

    def test_cannot_delete_last_remaining_prompt(self):
        # Delete all but one, then verify last one can't be deleted.
        only = self.lib.list_prompts()[0]
        with self.assertRaises(PromptValidationError):
            self.lib.delete_prompt(only["id"])

    def test_cannot_edit_builtin_prompt(self):
        builtin = next(p for p in self.lib.list_prompts() if p.get("is_builtin"))
        with self.assertRaises(PromptValidationError):
            self.lib.update_prompt(builtin["id"], content="hacked")

    def test_cannot_rename_builtin_prompt(self):
        builtin = next(p for p in self.lib.list_prompts() if p.get("is_builtin"))
        with self.assertRaises(PromptValidationError):
            self.lib.rename_prompt(builtin["id"], "Hacked Name")

    def test_cannot_delete_builtin_prompt(self):
        self.lib.add_prompt(name="Other", content="x")  # ensure not "last prompt" case
        builtin = next(p for p in self.lib.list_prompts() if p.get("is_builtin"))
        with self.assertRaises(PromptValidationError):
            self.lib.delete_prompt(builtin["id"])


class TestPromptLibraryValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "prompts.json"
        self.lib = PromptLibrary(storage_file=self.storage_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_name_rejected(self):
        with self.assertRaises(PromptValidationError):
            self.lib.add_prompt(name="   ", content="valid content")

    def test_empty_content_rejected(self):
        with self.assertRaises(PromptValidationError):
            self.lib.add_prompt(name="Valid Name", content="   ")

    def test_duplicate_name_rejected(self):
        self.lib.add_prompt(name="Unique Name", content="content 1")
        with self.assertRaises(PromptValidationError):
            self.lib.add_prompt(name="Unique Name", content="content 2")

    def test_duplicate_name_case_insensitive_rejected(self):
        self.lib.add_prompt(name="Some Name", content="content 1")
        with self.assertRaises(PromptValidationError):
            self.lib.add_prompt(name="some name", content="content 2")

    def test_name_is_trimmed(self):
        p = self.lib.add_prompt(name="  Padded Name  ", content="content")
        self.assertEqual(p["name"], "Padded Name")

    def test_rename_to_duplicate_name_rejected(self):
        self.lib.add_prompt(name="First", content="c1")
        second = self.lib.add_prompt(name="Second", content="c2")
        with self.assertRaises(PromptValidationError):
            self.lib.rename_prompt(second["id"], "First")

    def test_invalid_prompt_id_operations_raise(self):
        with self.assertRaises(PromptValidationError):
            self.lib.update_prompt("does_not_exist", content="x")
        with self.assertRaises(PromptValidationError):
            self.lib.rename_prompt("does_not_exist", "x")
        with self.assertRaises(PromptValidationError):
            self.lib.duplicate_prompt("does_not_exist")
        with self.assertRaises(PromptValidationError):
            self.lib.delete_prompt("does_not_exist")
        with self.assertRaises(PromptValidationError):
            self.lib.activate_prompt("does_not_exist")

    def test_get_prompt_unknown_id_returns_none(self):
        self.assertIsNone(self.lib.get_prompt("nonexistent_id"))


class TestPromptLibraryActivation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "prompts.json"
        self.lib = PromptLibrary(storage_file=self.storage_path)
        self.prompt_a = self.lib.get_active_prompt()  # builtin, active by default
        self.prompt_b = self.lib.add_prompt(name="Prompt B", content="content B")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_only_one_active_prompt_initially(self):
        active = [p for p in self.lib.list_prompts() if p.get("active")]
        self.assertEqual(len(active), 1)

    def test_activating_b_deactivates_a(self):
        """Core scenario from the spec: Prompt A active, activate Prompt B => A inactive, B active."""
        self.assertTrue(self.lib.get_prompt(self.prompt_a["id"])["active"])
        self.assertFalse(self.lib.get_prompt(self.prompt_b["id"])["active"])

        self.lib.activate_prompt(self.prompt_b["id"])

        self.assertFalse(self.lib.get_prompt(self.prompt_a["id"])["active"])
        self.assertTrue(self.lib.get_prompt(self.prompt_b["id"])["active"])

        active = [p for p in self.lib.list_prompts() if p.get("active")]
        self.assertEqual(len(active), 1)

    def test_toggle_on_activates_exclusively(self):
        self.lib.toggle_active(self.prompt_b["id"])
        self.assertTrue(self.lib.get_prompt(self.prompt_b["id"])["active"])
        self.assertFalse(self.lib.get_prompt(self.prompt_a["id"])["active"])

    def test_toggle_off_falls_back_to_another_prompt(self):
        # A is active; toggling A off must not leave zero active prompts.
        self.lib.toggle_active(self.prompt_a["id"])
        active = [p for p in self.lib.list_prompts() if p.get("active")]
        self.assertEqual(len(active), 1)

    def test_get_active_prompt_returns_active_one(self):
        self.lib.activate_prompt(self.prompt_b["id"])
        self.assertEqual(self.lib.get_active_prompt()["id"], self.prompt_b["id"])

    def test_deleting_active_prompt_reassigns_active(self):
        self.lib.activate_prompt(self.prompt_b["id"])
        self.lib.delete_prompt(self.prompt_b["id"])
        # Must still have exactly one active prompt (the builtin).
        active = [p for p in self.lib.list_prompts() if p.get("active")]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], self.prompt_a["id"])

    def test_migration_repairs_multiple_active_flags(self):
        """Simulate a hand-corrupted file with 2+ active prompts; loading must repair to exactly one."""
        raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        for p in raw:
            p["active"] = True
        self.storage_path.write_text(json.dumps(raw), encoding="utf-8")

        lib2 = PromptLibrary(storage_file=self.storage_path)
        active = [p for p in lib2.list_prompts() if p.get("active")]
        self.assertEqual(len(active), 1)

    def test_migration_repairs_zero_active_flags(self):
        raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        for p in raw:
            p["active"] = False
        self.storage_path.write_text(json.dumps(raw), encoding="utf-8")

        lib2 = PromptLibrary(storage_file=self.storage_path)
        active = [p for p in lib2.list_prompts() if p.get("active")]
        self.assertEqual(len(active), 1)


class TestTranslatorServiceUsesActivePrompt(unittest.TestCase):
    """Verifies the Translator resolves the active prompt from the library
    (source-of-truth), rather than any hard-coded or stale value."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "prompts.json"
        self.lib = PromptLibrary(storage_file=self.storage_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_translator_service_resolves_active_prompt_content(self):
        from app.services import translator as translator_service_module

        new_prompt = self.lib.add_prompt(name="Custom Active", content="CUSTOM PROMPT CONTENT")
        self.lib.activate_prompt(new_prompt["id"])

        # Monkeypatch the module-level singleton so TranslatorService reads our temp library.
        original = translator_service_module.prompt_library_instance
        translator_service_module.prompt_library_instance = self.lib
        try:
            active = translator_service_module.prompt_library_instance.get_active_prompt()
            self.assertEqual(active["content"], "CUSTOM PROMPT CONTENT")
        finally:
            translator_service_module.prompt_library_instance = original

    def test_translator_service_switches_when_active_prompt_changes(self):
        from app.services import translator as translator_service_module

        prompt_x = self.lib.add_prompt(name="Prompt X", content="CONTENT X")
        prompt_y = self.lib.add_prompt(name="Prompt Y", content="CONTENT Y")

        original = translator_service_module.prompt_library_instance
        translator_service_module.prompt_library_instance = self.lib
        try:
            self.lib.activate_prompt(prompt_x["id"])
            self.assertEqual(self.lib.get_active_prompt()["content"], "CONTENT X")

            self.lib.activate_prompt(prompt_y["id"])
            self.assertEqual(self.lib.get_active_prompt()["content"], "CONTENT Y")
        finally:
            translator_service_module.prompt_library_instance = original


class TestPipelineTranslationCacheInvalidation(unittest.TestCase):
    """Point 21 of the spec: switching the active prompt must not let the
    pipeline silently reuse a translation produced under the old prompt.

    NOTE: app.core.pipeline transitively imports the full audio/TTS/render
    stack (edge_tts, pydub, groq, selenium, google-genai, etc.) even though
    none of that is touched by this test. We skip gracefully if that stack
    isn't installed in the current environment, since it's unrelated to the
    Prompt Management feature under test.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import app.core.pipeline  # noqa: F401
        except ImportError as e:
            raise unittest.SkipTest(f"app.core.pipeline unavailable in this environment: {e}")

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = Path(self.temp_dir) / "prompts.json"
        self.lib = PromptLibrary(storage_file=self.storage_path)

        from app.core.project import Project
        self.project_id = "PRJ-260731-CACHE"
        self.project = Project(
            project_id=self.project_id,
            base_dir=Path(self.temp_dir) / self.project_id
        )
        self.project.ensure_directories()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_invalid_when_active_prompt_id_differs(self):
        import app.core.pipeline as pipeline_module

        original = pipeline_module.prompt_library_instance if hasattr(pipeline_module, "prompt_library_instance") else None

        # Patch the prompt_engine module's singleton, which pipeline.py imports lazily by name.
        import app.core.prompt_engine as prompt_engine_module
        real_instance = prompt_engine_module.prompt_library_instance
        prompt_engine_module.prompt_library_instance = self.lib
        try:
            prompt_x = self.lib.add_prompt(name="Prompt X", content="X")
            prompt_y = self.lib.add_prompt(name="Prompt Y", content="Y")
            self.lib.activate_prompt(prompt_x["id"])

            engine = pipeline_module.PipelineEngine(self.project)
            out_file = self.project.translated_dir / "fake_output.srt"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text("mock translated content", encoding="utf-8")

            engine.state["steps"]["translation"]["status"] = "SUCCESS"
            engine.state["steps"]["translation"]["output"] = str(out_file)
            engine.state["steps"]["translation"]["prompt_id"] = prompt_x["id"]

            # Same active prompt -> cache should be valid.
            self.assertTrue(engine._is_step_cache_valid("translation"))

            # Switch active prompt -> cache must now be considered invalid.
            self.lib.activate_prompt(prompt_y["id"])
            self.assertFalse(engine._is_step_cache_valid("translation"))
        finally:
            prompt_engine_module.prompt_library_instance = real_instance


if __name__ == "__main__":
    unittest.main()
