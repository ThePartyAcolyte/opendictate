"""
Unit tests for updater version comparison, installation detection, and persistence logic.
"""

import os
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from core.updater import _parse_version, is_version_newer, is_user_installation, check_for_updates
from core.config import ConfigManager
from core.__version__ import __version__


class TestUpdater(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_manager = ConfigManager(base_dir=self.test_dir)
        self.config = self.config_manager.load_config()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_version_parsing(self):
        self.assertEqual(_parse_version("1.1.0"), [1, 1, 0])
        self.assertEqual(_parse_version("v1.1.0"), [1, 1, 0])
        self.assertEqual(_parse_version("1.0.0"), [1, 0, 0])
        self.assertEqual(_parse_version("2.0"), [2, 0, 0])
        self.assertEqual(_parse_version("v1.2.3.4"), [1, 2, 3, 4])

    def test_is_version_newer(self):
        self.assertTrue(is_version_newer("1.2.0", "1.1.0"))
        self.assertTrue(is_version_newer("1.2.0-rc1", "1.1.0"))
        self.assertTrue(is_version_newer("1.2.0-nightly.20260831", "1.1.0"))
        self.assertTrue(is_version_newer("1.2.0", "1.2.0-rc1"))
        self.assertFalse(is_version_newer("1.1.0", "1.2.0"))
        self.assertFalse(is_version_newer("1.1.0", "1.1.0"))
        self.assertFalse(is_version_newer("1.2.0-rc1", "1.2.0"))

    def test_is_user_installation_development_mode(self):
        # Current repo location should NOT be identified as user installation (~/.local/share/opendictate)
        self.assertFalse(is_user_installation())

    def test_config_update_fields_persistence(self):
        self.config["available_update_version"] = "1.5.0"
        self.config["available_update_url"] = "https://github.com/test/release"
        self.config["available_update_notes"] = "Test release notes"
        self.config["update_dismissed_version"] = "1.4.0"
        self.config_manager.save_config(self.config)

        # Reload from fresh DB instance
        new_mgr = ConfigManager(base_dir=self.test_dir)
        loaded = new_mgr.load_config()

        self.assertEqual(loaded.get("available_update_version"), "1.5.0")
        self.assertEqual(loaded.get("available_update_url"), "https://github.com/test/release")
        self.assertEqual(loaded.get("available_update_notes"), "Test release notes")
        self.assertEqual(loaded.get("update_dismissed_version"), "1.4.0")

    @patch("urllib.request.urlopen")
    def test_check_for_updates_found(self, mock_urlopen):
        fake_response = MagicMock()
        fake_response.status = 200
        fake_response.read.return_value = b'''{
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/ThePartyAcolyte/opendictate/releases/tag/v99.0.0",
            "body": "Major update features",
            "tarball_url": "https://api.github.com/repos/ThePartyAcolyte/opendictate/tarball/v99.0.0"
        }'''
        mock_urlopen.return_value.__enter__.return_value = fake_response

        found_event = []

        def on_found(info):
            found_event.append(info)

        check_for_updates(
            self.config,
            self.config_manager,
            force=True,
            on_update_found=on_found
        )

        import time
        time.sleep(0.5)

        self.assertEqual(self.config.get("available_update_version"), "99.0.0")
        self.assertEqual(self.config.get("available_update_url"), "https://github.com/ThePartyAcolyte/opendictate/releases/tag/v99.0.0")
        self.assertEqual(self.config.get("available_update_notes"), "Major update features")


if __name__ == "__main__":
    unittest.main()
