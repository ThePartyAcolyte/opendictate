"""
Unit test for WizardTUI module import and initialization check.
"""

import unittest


class TestWizardTUI(unittest.TestCase):
    """Test suite for WizardTUI terminal onboarding wizard."""

    def test_import_wizard(self):
        """Test that ui.wizard_tui imports cleanly and defines WizardTUI class."""
        try:
            import ui.wizard_tui
            self.assertIsNotNone(ui.wizard_tui.WizardTUI)
        except ImportError as e:
            self.fail(f"Failed to import ui.wizard_tui: {e}")


if __name__ == "__main__":
    unittest.main()
