"""
Comprehensive Integration Test for OpenDictate D-Bus Service (org.kirulab.OpenDictate),
including direct sessions, targeted reserved sessions, and smart double-cancellation.
"""

import sys
import time
import json
import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib


def test_dbus_lifecycle():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    # -------------------------------------------------------------------------
    # Test 1: GetStatus
    # -------------------------------------------------------------------------
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
    print("✔ 1. GetStatus returned:", status_str)

    # -------------------------------------------------------------------------
    # Test 2: StartCaptureSession and CancelCaptureSession
    # -------------------------------------------------------------------------
    print("\n▶ 2. Testing StartCaptureSession & direct Cancel...")
    loop1 = GLib.MainLoop()
    events_1 = []

    def on_sig_1(conn, sender, path, iface, name, params):
        val = params.unpack() if params else ()
        print(f"📡 Signal 1: {name} {val}")
        events_1.append(name)
        if name == "SessionCancelled":
            loop1.quit()

    sub_1 = bus.signal_subscribe(
        "org.kirulab.OpenDictate",
        "org.kirulab.OpenDictate",
        None,
        "/org/kirulab/OpenDictate",
        None,
        Gio.DBusSignalFlags.NONE,
        on_sig_1,
    )

    opts1 = {
        "session_id": GLib.Variant("s", "test_cancel_session"),
        "ai_processing": GLib.Variant("b", False)
    }
    bus.call_sync(
        "org.kirulab.OpenDictate",
        "/org/kirulab/OpenDictate",
        "org.kirulab.OpenDictate",
        "StartCaptureSession",
        GLib.Variant("(a{sv})", (opts1,)),
        GLib.VariantType("(s)"),
        Gio.DBusCallFlags.NONE,
        2000,
        None,
    )

    GLib.timeout_add(1000, lambda: (
        bus.call_sync(
            "org.kirulab.OpenDictate",
            "/org/kirulab/OpenDictate",
            "org.kirulab.OpenDictate",
            "CancelCaptureSession",
            GLib.Variant("(s)", ("test_cancel_session",)),
            None,
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        ),
        False
    )[-1])

    GLib.timeout_add(5000, loop1.quit)
    loop1.run()
    bus.signal_unsubscribe(sub_1)

    assert "SessionStarted" in events_1, "SessionStarted was not caught in test 2!"
    assert "SessionCancelled" in events_1, "SessionCancelled was not caught in test 2!"
    print("✔ Test 2 PASSED!")

    # -------------------------------------------------------------------------
    # Test 3: ReserveCaptureSession -> Cancel while recording (Retry) -> Stop recording (Fulfill)
    # -------------------------------------------------------------------------
    print("\n▶ 3. Testing ReserveCaptureSession with Smart Double Cancellation...")
    loop3 = GLib.MainLoop()
    events_3 = []

    def on_sig_3(conn, sender, path, iface, name, params):
        val = params.unpack() if params else ()
        print(f"📡 Signal 3: {name} {val}")
        events_3.append((name, val))
        if name == "SessionFinished":
            loop3.quit()

    sub_3 = bus.signal_subscribe(
        "org.kirulab.OpenDictate",
        "org.kirulab.OpenDictate",
        None,
        "/org/kirulab/OpenDictate",
        None,
        Gio.DBusSignalFlags.NONE,
        on_sig_3,
    )

    # Step A: Arm reservation for "OmaWrite" with purple accent
    opts_reserve = {
        "session_id": GLib.Variant("s", "note_omawrite_99"),
        "app_name": GLib.Variant("s", "OmaWrite"),
        "accent_color": GLib.Variant("s", "#9C27B0"),
        "ai_processing": GLib.Variant("b", False)
    }
    res_res = bus.call_sync(
        "org.kirulab.OpenDictate",
        "/org/kirulab/OpenDictate",
        "org.kirulab.OpenDictate",
        "ReserveCaptureSession",
        GLib.Variant("(a{sv})", (opts_reserve,)),
        GLib.VariantType("(s)"),
        Gio.DBusCallFlags.NONE,
        2000,
        None,
    )
    sid_reserved = res_res.unpack()[0]
    assert sid_reserved == "note_omawrite_99"
    print("✔ Reservation armed for OmaWrite. Checking daemon status...")

    # Verify daemon state shows armed reservation
    st = json.loads(bus.call_sync(
        "org.kirulab.OpenDictate", "/org/kirulab/OpenDictate", "org.kirulab.OpenDictate", "GetStatus", None, GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 2000, None
    ).unpack()[0])
    assert st.get("reserved_session", {}).get("app_name") == "OmaWrite", "Status does not reflect armed reservation!"

    # Step B: Start recording using the normal trigger
    print("▶ Starting recording (simulating user pressing SUPER+D)...")
    import subprocess
    subprocess.run(["opendictate", "--record"], capture_output=True)

    # Step C: Cancel mid-recording (simulating user hitting cancel to retry)
    def do_mid_cancel():
        print("⏹ User hit cancel mid-recording (simulating noisy room retry)...")
        subprocess.run(["opendictate", "--cancel"], capture_output=True)
        time.sleep(0.5)
        # Check that reservation is STILL ARMED!
        st2 = json.loads(bus.call_sync(
            "org.kirulab.OpenDictate", "/org/kirulab/OpenDictate", "org.kirulab.OpenDictate", "GetStatus", None, GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 2000, None
        ).unpack()[0])
        assert st2.get("reserved_session", {}).get("session_id") == "note_omawrite_99", "Reservation was prematurely destroyed by mid-recording cancel!"
        print("✔ Verified: Reservation remains ARMED after mid-stream cancel! Now re-recording...")

        # Step D: User speaks again and finishes
        subprocess.run(["opendictate", "--record"], capture_output=True)
        GLib.timeout_add(1500, lambda: (
            print("📤 User finishes speech (simulating send)..."),
            subprocess.run(["opendictate", "--send"], capture_output=True),
            False
        )[-1])
        return False

    GLib.timeout_add(1500, do_mid_cancel)
    GLib.timeout_add(30000, loop3.quit)
    loop3.run()
    bus.signal_unsubscribe(sub_3)

    sig3_names = [e[0] for e in events_3]
    print("Signals received in test 3:", sig3_names)
    assert "SessionReserved" in sig3_names, "SessionReserved was not caught!"
    assert "SessionFinished" in sig3_names, "SessionFinished was not emitted!"

    # -------------------------------------------------------------------------
    # Test 4: ReserveCaptureSession -> Cancel while IDLE (Un-reserve)
    # -------------------------------------------------------------------------
    print("\n▶ 4. Testing ReserveCaptureSession and Cancel while IDLE...")
    loop4 = GLib.MainLoop()
    events_4 = []

    def on_sig_4(conn, sender, path, iface, name, params):
        val = params.unpack() if params else ()
        print(f"📡 Signal 4: {name} {val}")
        events_4.append(name)
        if name == "SessionReservationReleased":
            loop4.quit()

    sub_4 = bus.signal_subscribe(
        "org.kirulab.OpenDictate",
        "org.kirulab.OpenDictate",
        None,
        "/org/kirulab/OpenDictate",
        None,
        Gio.DBusSignalFlags.NONE,
        on_sig_4,
    )

    opts4 = {
        "session_id": GLib.Variant("s", "test_idle_unreserve"),
        "app_name": GLib.Variant("s", "IdleApp"),
        "accent_color": GLib.Variant("s", "#00BCD4"),
    }
    bus.call_sync(
        "org.kirulab.OpenDictate",
        "/org/kirulab/OpenDictate",
        "org.kirulab.OpenDictate",
        "ReserveCaptureSession",
        GLib.Variant("(a{sv})", (opts4,)),
        GLib.VariantType("(s)"),
        Gio.DBusCallFlags.NONE,
        2000,
        None,
    )

    # Cancel while IDLE
    GLib.timeout_add(1000, lambda: (
        print("⏹ User pressed cancel while IDLE with reservation armed..."),
        subprocess.run(["opendictate", "--cancel"], capture_output=True),
        False
    )[-1])

    GLib.timeout_add(5000, loop4.quit)
    loop4.run()
    bus.signal_unsubscribe(sub_4)

    print("Signals in test 4:", events_4)
    assert "SessionReserved" in events_4, "SessionReserved missing in test 4!"
    assert "SessionReservationReleased" in events_4, "SessionReservationReleased missing in test 4!"

    # Verify daemon state is clear
    st4 = json.loads(bus.call_sync(
        "org.kirulab.OpenDictate", "/org/kirulab/OpenDictate", "org.kirulab.OpenDictate", "GetStatus", None, GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 2000, None
    ).unpack()[0])
    assert st4.get("reserved_session") is None, "Reservation was not cleared after IDLE cancel!"
    # -------------------------------------------------------------------------
    # Test 5: Multi-Application Eviction (App A reserved -> App B arrives -> App A evicted)
    # -------------------------------------------------------------------------
    print("\n▶ 5. Testing Multi-App Eviction with Client UUIDs...")
    loop5 = GLib.MainLoop()
    events_5 = []

    def on_sig_5(conn, sender, path, iface, name, params):
        val = params.unpack() if params else ()
        print(f"📡 Signal 5: {name} {val}")
        events_5.append((name, val))
        if name == "SessionFinished" and val and val[0] == "uuid-app-b-456":
            loop5.quit()

    sub_5 = bus.signal_subscribe(
        "org.kirulab.OpenDictate",
        "org.kirulab.OpenDictate",
        None,
        "/org/kirulab/OpenDictate",
        None,
        Gio.DBusSignalFlags.NONE,
        on_sig_5,
    )

    # 1. App A (UUID-A) reserves
    opts_app_a = {
        "session_id": GLib.Variant("s", "uuid-app-a-123"),
        "app_name": GLib.Variant("s", "App A"),
        "accent_color": GLib.Variant("s", "#E91E63"),
    }
    bus.call_sync(
        "org.kirulab.OpenDictate",
        "/org/kirulab/OpenDictate",
        "org.kirulab.OpenDictate",
        "ReserveCaptureSession",
        GLib.Variant("(a{sv})", (opts_app_a,)),
        GLib.VariantType("(s)"),
        Gio.DBusCallFlags.NONE,
        2000,
        None,
    )
    print("✔ App A reserved session.")

    # 2. App B (UUID-B) arrives and evicts App A
    time.sleep(0.3)
    opts_app_b = {
        "session_id": GLib.Variant("s", "uuid-app-b-456"),
        "app_name": GLib.Variant("s", "App B"),
        "accent_color": GLib.Variant("s", "#4CAF50"),
    }
    bus.call_sync(
        "org.kirulab.OpenDictate",
        "/org/kirulab/OpenDictate",
        "org.kirulab.OpenDictate",
        "ReserveCaptureSession",
        GLib.Variant("(a{sv})", (opts_app_b,)),
        GLib.VariantType("(s)"),
        Gio.DBusCallFlags.NONE,
        2000,
        None,
    )
    print("✔ App B reserved session (evicting App A).")

    # 3. User records and sends
    time.sleep(0.3)
    subprocess.run(["opendictate", "--record"], capture_output=True)
    GLib.timeout_add(1500, lambda: (
        print("📤 User sends audio..."),
        subprocess.run(["opendictate", "--send"], capture_output=True),
        False
    )[-1])

    GLib.timeout_add(30000, loop5.quit)
    loop5.run()
    bus.signal_unsubscribe(sub_5)

    # Validate signal trail
    app_a_cancelled = any(e[0] == "SessionCancelled" and e[1] == ("uuid-app-a-123",) for e in events_5)
    app_b_finished = any(e[0] == "SessionFinished" and e[1][0] == "uuid-app-b-456" for e in events_5)
    assert app_a_cancelled, "App A (uuid-app-a-123) did not receive eviction SessionCancelled signal!"
    assert app_b_finished, "App B (uuid-app-b-456) did not receive SessionFinished signal!"
    print("✔ Test 5 PASSED: Multi-app eviction works flawlessly!")

    print("\n🎉 ALL ADVANCED D-BUS TESTS (INCLUDING MULTI-APP EVICTION) PASSED! 🎉")


if __name__ == "__main__":
    test_dbus_lifecycle()
