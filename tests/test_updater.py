"""
Unit tests for updater version comparison logic.
"""

import unittest
from core.updater import _parse_version


class TestUpdater(unittest.TestCase):

    def test_version_parsing(self):
        self.assertEqual(_parse_version("1.1.0"), [1, 1, 0])
        self.assertEqual(_parse_version("v1.1.0"), [1, 1, 0])
        self.assertEqual(_parse_version("1.0.0"), [1, 0, 0])
        self.assertEqual(_parse_version("2.0"), [2, 0])

    def test_version_comparison(self):
        self.assertTrue(_parse_version("1.1.0") > _parse_version("1.0.0"))
        self.assertTrue(_parse_version("1.1.1") > _parse_version("1.1.0"))
        self.assertTrue(_parse_version("2.0.0") > _parse_version("1.9.9"))
        self.assertFalse(_parse_version("1.0.0") > _parse_version("1.0.0"))
        self.assertFalse(_parse_version("1.0.0") > _parse_version("1.1.0"))


if __name__ == "__main__":
    unittest.main()
