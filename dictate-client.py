#!/usr/bin/env python3
import sys
import socket

SOCKET_PATH = "/tmp/dictate_daemon.socket"

def main():
    if "--record" in sys.argv or "record" in sys.argv:
        cmd = "record"
    elif "--pause" in sys.argv or "pause" in sys.argv:
        cmd = "pause"
    elif "--cancel" in sys.argv or "cancel" in sys.argv:
        cmd = "cancel"
    elif "--send" in sys.argv or "send" in sys.argv:
        cmd = "send"
    elif "--preview" in sys.argv or "preview" in sys.argv:
        cmd = "preview"
    elif "--finish-normal" in sys.argv or "finish-normal" in sys.argv:
        cmd = "finish-normal"
    elif "--finish-ai" in sys.argv or "finish-ai" in sys.argv:
        cmd = "finish-ai"
    elif "--autosend-activate" in sys.argv or "autosend-activate" in sys.argv:
        cmd = "autosend-activate"
    elif "--autosend-deactivate" in sys.argv or "autosend-deactivate" in sys.argv:
        cmd = "autosend-deactivate"
    elif "--toggle-autopause" in sys.argv:
        cmd = "toggle-autopause"
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
    else:
        print("Uso: dictate-client.py [--record|--pause|--cancel|--preview|--finish-normal|--finish-ai|--autosend-activate|--autosend-deactivate|--toggle-autopause|--toggle-bubble|--toggle-record-send|--toggle-ai|--toggle-autosend|--toggle-realtime|--cycle-model]")
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
