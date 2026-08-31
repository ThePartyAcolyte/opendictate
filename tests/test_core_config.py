"""
Unit tests for ConfigManager SQLite schema, migrations, CRUD, and history.
"""

import os
import shutil
import tempfile
import unittest
import sqlite3
from core.config import ConfigManager, DEFAULT_CONFIG


class TestConfigManager(unittest.TestCase):
    """Test suite for ConfigManager database initialization and persistence operations."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="opendictate_test_cfg_")
        self.config_manager = ConfigManager(base_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_database_initialization_schema_version(self):
        """Test that fresh database initializes with user_version = 2 and required tables."""
        self.assertTrue(os.path.exists(self.config_manager.db_path))
        with sqlite3.connect(self.config_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            self.assertEqual(version, 2)

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]
            self.assertIn("app_profiles", tables)
            self.assertIn("history", tables)
            self.assertIn("global_settings", tables)

    def test_save_and_load_config_roundtrip(self):
        """Test saving configuration dictionary and loading values back accurately."""
        custom_config = DEFAULT_CONFIG.copy()
        custom_config["model"] = "gemini-2.5-flash"
        custom_config["ai_enabled"] = True
        custom_config["auto_send"] = True
        custom_config["whisper_device"] = "cuda"

        self.config_manager.save_config(custom_config)
        loaded = self.config_manager.load_config()

        self.assertEqual(loaded["model"], "gemini-2.5-flash")
        self.assertTrue(loaded["ai_enabled"])
        self.assertTrue(loaded["auto_send"])
        self.assertEqual(loaded["whisper_device"], "cuda")

    def test_app_profiles_crud(self):
        """Test creating, reading, and deleting per-application profile settings."""
        # Initial query for non-existent app returns defaults
        prompt, vision = self.config_manager.get_app_profile("org.gnome.Terminal")
        self.assertIsNone(prompt)
        self.assertFalse(vision)

        # Insert profile
        with sqlite3.connect(self.config_manager.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO app_profiles (app_class, system_prompt, enable_vision) VALUES (?, ?, ?)",
                ("org.gnome.Terminal", "Format bash commands concisely", 1)
            )
            conn.commit()

        prompt, vision = self.config_manager.get_app_profile("org.gnome.Terminal")
        self.assertEqual(prompt, "Format bash commands concisely")
        self.assertTrue(vision)

    def test_history_record_persistence(self):
        """Test saving and retrieving recent dictation history records."""
        self.config_manager.save_history_record("code", "main.py - VSCode", "def hello world", "def hello_world():")
        self.config_manager.save_history_record("code", "main.py - VSCode", "print hi", "print('hi')")

        history = self.config_manager.get_recent_history("code", limit=5)
        self.assertEqual(len(history), 2)
        # Returns list of tuples (llm_text, original_text) ordered by timestamp descending
        self.assertEqual(history[0], ("print('hi')", "print hi"))
        self.assertEqual(history[1], ("def hello_world():", "def hello world"))


if __name__ == "__main__":
    unittest.main()
