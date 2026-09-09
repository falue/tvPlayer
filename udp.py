"""
Reusable UDP module for Raspberry Pi Python projects.
=====================================================

Usage in main script:
    1. Create a UDPNode with config
    2. Call start() to begin listening in a background thread
    3. Either pass on_command=... to handle commands in the listener thread,
       or call listen() / listen_all() in your main loop to poll them
    4. Call send(msg) to send to the default target
    5. Call send(msg, ip, port) to send to a specific target

prepend (device name):
    Only packets starting with this prefix are accepted.
    The prefix is stripped before returning the command.
    When such a packet arrives, an acknowledgment (reply) is sent back
    to the sender automatically.

TEST CONNECTION IN TERMINAL:
    Send:    echo -n "devicename_test" | nc -u <PI_IP> <PORT>
    Listen:  nc -u -l <PORT>
"""

from __future__ import annotations

import socket
import threading
import traceback
from queue import Empty, Queue
from typing import Callable, Optional


class UDPNode:
    """
    General-purpose UDP communication node.

    Mirrors the pattern of network.cpp / network.h from _basic_udp (Arduino),
    adapted for Python threading on Raspberry Pi.
    """

    def __init__(
        self,
        local_port: int,
        remote_ip: str,
        remote_port: int,
        prepend: str = "",
        reply: str = "",
        device_name: str = "unnamed",
        listen_ip: str = "0.0.0.0",
        on_command: Optional[Callable[[str, tuple], None]] = None,
        verbose: bool = False,
    ) -> None:
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.prepend = prepend
        self.reply = reply
        self.device_name = device_name
        self.listen_ip = listen_ip
        self.on_command = on_command
        self.verbose = verbose

        self._queue: Queue[str] = Queue()
        self._stop_event = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def stop_event(self) -> threading.Event:
        return self._stop_event

    def start(self) -> None:
        """Start the UDP listener thread."""
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="UDPNode",
        )
        self._thread.start()

        print(f"[UDP] DEVICE_NAME: {self.device_name}", flush=True)
        print(f"[UDP] listening on {self.listen_ip}:{self.local_port}", flush=True)
        print(f"[UDP] sending to {self.remote_ip}:{self.remote_port}", flush=True)

    def listen(self) -> str:
        """
        Non-blocking check for received commands.

        Returns the stripped command string (prefix removed) if a valid
        packet was received, or "" otherwise.
        """
        try:
            return self._queue.get_nowait()
        except Empty:
            return ""

    def listen_all(self) -> list:
        """
        Drain all pending commands from the queue.

        Returns a list of stripped command strings.
        """
        commands = []
        while True:
            try:
                commands.append(self._queue.get_nowait())
            except Empty:
                break
        return commands

    def send(
        self,
        message: str,
        target_ip: Optional[str] = None,
        target_port: Optional[int] = None,
    ) -> None:
        """Send a UDP message to the target (or default remote)."""
        ip = target_ip if target_ip is not None else self.remote_ip
        port = target_port if target_port is not None else self.remote_port

        data = message.encode("utf-8")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(data, (ip, port))

            if self.verbose:
                print(f"[UDP] sent '{message}' -> {ip}:{port}", flush=True)
        except OSError as exc:
            print(f"[UDP] send failed: {exc}", flush=True)

    def stop(self) -> None:
        """Stop the listener thread and close the socket."""
        self._stop_event.set()
        self._close_socket()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _listen_loop(self) -> None:
        """Background thread: receive, filter, acknowledge, dispatch."""
        try:
            self._sock = socket.socket(
                socket.AF_INET,
                socket.SOCK_DGRAM,
            )
            self._sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1,
            )
            self._sock.bind((self.listen_ip, self.local_port))
            self._sock.settimeout(0.5)

            while not self._stop_event.is_set():
                try:
                    data, address = self._sock.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break

                message = data.decode("utf-8", errors="replace").strip()

                if not message:
                    continue

                # Check prepend prefix
                if self.prepend and not message.startswith(self.prepend):
                    print(
                        f"[UDP] Ignored message from {address[0]}:{address[1]}: "
                        f"{message} (msg should start with '{self.prepend}')",
                        flush=True,
                    )
                    continue

                # Send acknowledgment back to sender
                if self.reply:
                    try:
                        self._sock.sendto(
                            self.reply.encode("utf-8"),
                            address,
                        )
                    except OSError:
                        pass

                # Strip prepend prefix (and separator character after it)
                if self.prepend:
                    offset = len(self.prepend)
                    if offset < len(message) and message[offset] in ("_", " ", "-"):
                        offset += 1
                    command = message[offset:]
                else:
                    command = message

                if not command:
                    continue

                if self.on_command:
                    try:
                        self.on_command(command, address)
                    except Exception:
                        print(f"[UDP] Error in command callback:", flush=True)
                        traceback.print_exc()
                else:
                    self._queue.put(command)

        except Exception:
            print("[UDP] listener failed:", flush=True)
            traceback.print_exc()
            self._stop_event.set()
        finally:
            self._close_socket()

    def _close_socket(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
