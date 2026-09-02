"""
D-Bus Session Service for OpenDictate (org.kirulab.OpenDictate).

Exposes methods and signals on the user session bus for headless external integration:
- StartCaptureSession(a{sv} options) -> s session_id
- StopCaptureSession(s session_id)
- CancelCaptureSession(s session_id)
- ReserveCaptureSession(a{sv} options) -> s session_id
- ReleaseReservedSession(s session_id)
- GetStatus() -> s status_json

Signals:
- SessionStarted(s session_id)
- SessionFinished(s session_id, s raw_text, s processed_text, s status)
- SessionCancelled(s session_id)
- SessionReserved(s session_id, s app_name, s accent_color)
- SessionReservationReleased(s session_id)
- InterimText(s session_id, s interim_text)
"""

import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib


DBUS_INTROSPECTION_XML = """
<node>
  <interface name="org.kirulab.OpenDictate">
    <method name="StartCaptureSession">
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="s" name="session_id" direction="out"/>
    </method>
    <method name="StopCaptureSession">
      <arg type="s" name="session_id" direction="in"/>
    </method>
    <method name="CancelCaptureSession">
      <arg type="s" name="session_id" direction="in"/>
    </method>
    <method name="ReserveCaptureSession">
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="s" name="session_id" direction="out"/>
    </method>
    <method name="ReleaseReservedSession">
      <arg type="s" name="session_id" direction="in"/>
    </method>
    <method name="GetStatus">
      <arg type="s" name="status_json" direction="out"/>
    </method>
    <signal name="SessionStarted">
      <arg type="s" name="session_id"/>
    </signal>
    <signal name="SessionFinished">
      <arg type="s" name="session_id"/>
      <arg type="s" name="raw_text"/>
      <arg type="s" name="processed_text"/>
      <arg type="s" name="status"/>
    </signal>
    <signal name="SessionCancelled">
      <arg type="s" name="session_id"/>
    </signal>
    <signal name="SessionReserved">
      <arg type="s" name="session_id"/>
      <arg type="s" name="app_name"/>
      <arg type="s" name="accent_color"/>
    </signal>
    <signal name="SessionReservationReleased">
      <arg type="s" name="session_id"/>
    </signal>
    <signal name="InterimText">
      <arg type="s" name="session_id"/>
      <arg type="s" name="interim_text"/>
    </signal>
  </interface>
</node>
"""


class OpenDictateDBusService:
    """Manages org.kirulab.OpenDictate D-Bus interface registration and signal emission."""

    BUS_NAME = "org.kirulab.OpenDictate"
    OBJECT_PATH = "/org/kirulab/OpenDictate"
    INTERFACE_NAME = "org.kirulab.OpenDictate"

    def __init__(
        self,
        on_start_capture: Callable[[Dict[str, Any]], str],
        on_stop_capture: Callable[[str], None],
        on_cancel_capture: Callable[[str], None],
        on_reserve_capture: Callable[[Dict[str, Any]], str],
        on_release_reserved: Callable[[str], None],
        on_get_status: Callable[[], Dict[str, Any]],
    ) -> None:
        self.on_start_capture = on_start_capture
        self.on_stop_capture = on_stop_capture
        self.on_cancel_capture = on_cancel_capture
        self.on_reserve_capture = on_reserve_capture
        self.on_release_reserved = on_release_reserved
        self.on_get_status = on_get_status

        self.connection: Optional[Gio.DBusConnection] = None
        self.owner_id: Optional[int] = None
        self.registration_id: Optional[int] = None

        self._node_info = Gio.DBusNodeInfo.new_for_xml(DBUS_INTROSPECTION_XML)
        self._interface_info = self._node_info.interfaces[0]

    def start(self) -> None:
        """Acquire bus name on the user session bus."""
        try:
            self.owner_id = Gio.bus_own_name(
                Gio.BusType.SESSION,
                self.BUS_NAME,
                Gio.BusNameOwnerFlags.NONE,
                self._on_bus_acquired,
                self._on_name_acquired,
                self._on_name_lost,
            )
            logging.info(f"D-Bus service name registration requested for {self.BUS_NAME}")
        except Exception as e:
            logging.error(f"Failed to start D-Bus service: {e}", exc_info=True)

    def stop(self) -> None:
        """Unregister D-Bus object and release bus name."""
        if self.connection and self.registration_id:
            try:
                self.connection.unregister_object(self.registration_id)
            except Exception:
                pass
            self.registration_id = None

        if self.owner_id:
            Gio.bus_unown_name(self.owner_id)
            self.owner_id = None

    def _on_bus_acquired(self, connection: Gio.DBusConnection, name: str) -> None:
        self.connection = connection
        try:
            self.registration_id = connection.register_object(
                self.OBJECT_PATH,
                self._interface_info,
                self._handle_method_call,
                None,
                None,
            )
            logging.info(f"D-Bus object exported at {self.OBJECT_PATH} on {name}")
        except Exception as e:
            logging.error(f"Error registering D-Bus object: {e}", exc_info=True)

    def _on_name_acquired(self, connection: Gio.DBusConnection, name: str) -> None:
        logging.info(f"D-Bus name acquired: {name}")

    def _on_name_lost(self, connection: Gio.DBusConnection, name: str) -> None:
        logging.warning(f"D-Bus name lost: {name}")

    def _handle_method_call(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        try:
            if method_name == "StartCaptureSession":
                raw_options = parameters.unpack()[0] if parameters else {}
                options = self._unpack_options(raw_options)
                session_id = self.on_start_capture(options)
                invocation.return_value(GLib.Variant("(s)", (session_id,)))

            elif method_name == "ReserveCaptureSession":
                raw_options = parameters.unpack()[0] if parameters else {}
                options = self._unpack_options(raw_options)
                session_id = self.on_reserve_capture(options)
                invocation.return_value(GLib.Variant("(s)", (session_id,)))

            elif method_name == "ReleaseReservedSession":
                session_id = parameters.unpack()[0] if parameters else ""
                self.on_release_reserved(session_id)
                invocation.return_value(None)

            elif method_name == "StopCaptureSession":
                session_id = parameters.unpack()[0] if parameters else ""
                self.on_stop_capture(session_id)
                invocation.return_value(None)

            elif method_name == "CancelCaptureSession":
                session_id = parameters.unpack()[0] if parameters else ""
                self.on_cancel_capture(session_id)
                invocation.return_value(None)

            elif method_name == "GetStatus":
                status_dict = self.on_get_status()
                status_json = json.dumps(status_dict) if isinstance(status_dict, dict) else str(status_dict)
                invocation.return_value(GLib.Variant("(s)", (status_json,)))

            else:
                invocation.return_error_literal(
                    Gio.dbus_error_quark(),
                    Gio.DBusError.UNKNOWN_METHOD,
                    f"Unknown method {method_name}",
                )
        except Exception as e:
            logging.error(f"Error handling D-Bus method {method_name}: {e}", exc_info=True)
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.FAILED,
                str(e),
            )

    @staticmethod
    def _unpack_options(raw_options: Any) -> Dict[str, Any]:
        options: Dict[str, Any] = {}
        if isinstance(raw_options, dict):
            for k, v in raw_options.items():
                options[k] = v.unpack() if hasattr(v, "unpack") else v
        return options

    # -------------------------------------------------------------------------
    # Signals
    # -------------------------------------------------------------------------

    def emit_session_started(self, session_id: str) -> None:
        """Broadcast SessionStarted signal."""
        if not self.connection:
            return
        try:
            self.connection.emit_signal(
                None,
                self.OBJECT_PATH,
                self.INTERFACE_NAME,
                "SessionStarted",
                GLib.Variant("(s)", (str(session_id),)),
            )
        except Exception as e:
            logging.debug(f"Failed to emit SessionStarted signal: {e}")

    def emit_session_finished(
        self,
        session_id: str,
        raw_text: str,
        processed_text: str,
        status: str = "ok",
    ) -> None:
        """Broadcast SessionFinished signal with raw and AI-processed transcripts."""
        if not self.connection:
            return
        try:
            self.connection.emit_signal(
                None,
                self.OBJECT_PATH,
                self.INTERFACE_NAME,
                "SessionFinished",
                GLib.Variant("(ssss)", (str(session_id), str(raw_text), str(processed_text), str(status))),
            )
            logging.info(f"D-Bus SessionFinished emitted for session='{session_id}' (status='{status}')")
        except Exception as e:
            logging.debug(f"Failed to emit SessionFinished signal: {e}")

    def emit_session_cancelled(self, session_id: str) -> None:
        """Broadcast SessionCancelled signal."""
        if not self.connection:
            return
        try:
            self.connection.emit_signal(
                None,
                self.OBJECT_PATH,
                self.INTERFACE_NAME,
                "SessionCancelled",
                GLib.Variant("(s)", (str(session_id),)),
            )
        except Exception as e:
            logging.debug(f"Failed to emit SessionCancelled signal: {e}")

    def emit_session_reserved(self, session_id: str, app_name: str, accent_color: str) -> None:
        """Broadcast SessionReserved signal."""
        if not self.connection:
            return
        try:
            self.connection.emit_signal(
                None,
                self.OBJECT_PATH,
                self.INTERFACE_NAME,
                "SessionReserved",
                GLib.Variant("(sss)", (str(session_id), str(app_name), str(accent_color))),
            )
        except Exception as e:
            logging.debug(f"Failed to emit SessionReserved signal: {e}")

    def emit_session_reservation_released(self, session_id: str) -> None:
        """Broadcast SessionReservationReleased signal."""
        if not self.connection:
            return
        try:
            self.connection.emit_signal(
                None,
                self.OBJECT_PATH,
                self.INTERFACE_NAME,
                "SessionReservationReleased",
                GLib.Variant("(s)", (str(session_id),)),
            )
        except Exception as e:
            logging.debug(f"Failed to emit SessionReservationReleased signal: {e}")

    def emit_interim_text(self, session_id: str, interim_text: str) -> None:
        """Broadcast real-time InterimText signal."""
        if not self.connection or not session_id:
            return
        try:
            self.connection.emit_signal(
                None,
                self.OBJECT_PATH,
                self.INTERFACE_NAME,
                "InterimText",
                GLib.Variant("(ss)", (str(session_id), str(interim_text))),
            )
        except Exception as e:
            logging.debug(f"Failed to emit InterimText signal: {e}")
