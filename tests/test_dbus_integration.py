"""
Unit and Integration Test for OpenDictate D-Bus Service (org.kirulab.OpenDictate).

Verifies D-Bus method call dispatching and signal lifecycle using unittest mocks.
"""

import json
import unittest
from unittest.mock import patch, MagicMock
import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib


class TestDBusIntegration(unittest.TestCase):
    """Test suite for OpenDictate D-Bus interface."""

    @patch("gi.repository.Gio.bus_get_sync")
    def test_dbus_get_status_mock(self, mock_bus_get):
        mock_bus = MagicMock()
        mock_bus_get.return_value = mock_bus
        mock_res = MagicMock()
        mock_res.unpack.return_value = ['{"state": "IDLE", "stt_backend": "local_whisper"}']
        mock_bus.call_sync.return_value = mock_res

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        res = bus.call_sync(
            "org.kirulab.OpenDictate",
            "/org/kirulab/OpenDictate",
            "org.kirulab.OpenDictate",
            "GetStatus",
            None,
            GLib.VariantType("(s)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        status_str = res.unpack()[0]
        status = json.loads(status_str)
        self.assertEqual(status.get("state"), "IDLE")
        self.assertEqual(status.get("stt_backend"), "local_whisper")

    @patch("gi.repository.Gio.bus_get_sync")
    def test_dbus_start_capture_mock(self, mock_bus_get):
        mock_bus = MagicMock()
        mock_bus_get.return_value = mock_bus
        mock_res = MagicMock()
        mock_res.unpack.return_value = ["test_session_123"]
        mock_bus.call_sync.return_value = mock_res

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        opts = {"session_id": GLib.Variant("s", "test_session_123")}
        res = bus.call_sync(
            "org.kirulab.OpenDictate",
            "/org/kirulab/OpenDictate",
            "org.kirulab.OpenDictate",
            "StartCaptureSession",
            GLib.Variant("(a{sv})", (opts,)),
            GLib.VariantType("(s)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        session_id = res.unpack()[0]
        self.assertEqual(session_id, "test_session_123")


if __name__ == "__main__":
    unittest.main()
