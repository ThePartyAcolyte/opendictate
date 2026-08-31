"""
IPC Unix Domain Socket server module for OpenDictate daemon.

Listens for incoming CLI, GNOME Shell Extension, and OpenDeck plugin socket commands.
"""

import os
import socket
import logging
from typing import Callable, Dict, Optional

SOCKET_PATH = "/tmp/opendictate.socket"


class IPCServer:
    """Unix Domain Socket listener and command router."""

    def __init__(self, command_handlers: Dict[str, Callable[[], None]]) -> None:
        """Initialize IPC server with command map.

        Args:
            command_handlers: Dictionary mapping command strings to callable handlers.
        """
        self.command_handlers = command_handlers
        self.running = False
        self.sock: Optional[socket.socket] = None

    def start(self) -> None:
        """Start socket listener loop (should run in a daemon thread)."""
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except Exception as e:
                logging.error(f"Error removing old socket file: {e}")

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(SOCKET_PATH)
        self.sock.listen(16)
        self.running = True
        logging.info(f"IPC Socket server bound and listening at {SOCKET_PATH}")

        while self.running:
            try:
                conn, _ = self.sock.accept()
                try:
                    conn.settimeout(0.5)
                    data = conn.recv(1024).decode('utf-8').strip()
                finally:
                    conn.close()

                if not data:
                    continue

                logging.info(f"Received socket command: {data}")
                handler = self.command_handlers.get(data)
                if handler:
                    handler()
                else:
                    logging.warning(f"Unknown IPC command: {data}")
            except Exception as e:
                if self.running:
                    logging.error(f"IPC Socket error: {e}")

    def stop(self) -> None:
        """Stop socket server and clean up socket file."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if os.path.exists(SOCKET_PATH):
            try:
                os.remove(SOCKET_PATH)
            except Exception:
                pass
