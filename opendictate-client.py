#!/usr/bin/env python3
import sys
import socket
import os
import sys

# Allow running from the install directory or the repo root
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from core.ipc import SOCKET_PATH

def main():
    if "--record" in sys.argv or "record" in sys.argv:
        cmd = "record"
    elif "--pause" in sys.argv or "pause" in sys.argv:
        cmd = "pause"
    elif "--cancel" in sys.argv or "cancel" in sys.argv:
        cmd = "cancel"
    elif "--send" in sys.argv or "send" in sys.argv:
        cmd = "send"
    elif "--finish-normal" in sys.argv or "finish-normal" in sys.argv:
        cmd = "finish-normal"
    elif "--finish-ai" in sys.argv or "finish-ai" in sys.argv:
        cmd = "finish-ai"
    elif "--toggle-bubble" in sys.argv:
        cmd = "toggle-bubble"
    elif "--toggle-record-send" in sys.argv:
        cmd = "toggle-record-send"
    elif "--cycle-model" in sys.argv:
        cmd = "cycle-model"
    elif "--toggle-ai" in sys.argv:
        cmd = "toggle-ai"
    elif "--toggle-autosend" in sys.argv:
        cmd = "toggle-autosend"
    elif "--toggle-realtime" in sys.argv:
        cmd = "toggle-realtime"
    elif "--settings" in sys.argv or "settings" in sys.argv:
        cmd = "settings"
    elif "--wizard" in sys.argv or "wizard" in sys.argv:
        cmd = "wizard"
    else:
        print("Usage: opendictate [--record|--pause|--cancel|--finish-normal|--finish-ai|--settings|--wizard|--toggle-bubble|--toggle-record-send|--toggle-ai|--toggle-autosend|--toggle-realtime|--cycle-model]")
        sys.exit(0)

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCKET_PATH)
        s.sendall(cmd.encode('utf-8'))
        s.close()
    except Exception as e:
        print(f"Error connecting to daemon: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
