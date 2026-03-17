"""Daemon lifecycle management for phone-cli."""

import json
import logging
import os
import signal
import socket
import threading
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Any

DEFAULT_HOME = os.path.expanduser("~/.phone-cli")
MAX_QUEUE_DEPTH = 10
HEARTBEAT_INTERVAL = 30  # seconds


def _setup_logger(log_dir: str) -> logging.Logger:
    """Set up file logger with daily rotation, 30-day retention."""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("phone-cli")
    logger.setLevel(logging.INFO)
    # Guard against duplicate handlers on repeated init
    if not logger.handlers:
        handler = TimedRotatingFileHandler(
            os.path.join(log_dir, "phone-cli.log"),
            when="midnight", backupCount=30, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s"
        ))
        logger.addHandler(handler)
    return logger


class PhoneCLIDaemon:
    """Manages the phone-cli background daemon process."""

    def __init__(self, home_dir: str = DEFAULT_HOME):
        self.home_dir = home_dir
        os.makedirs(home_dir, exist_ok=True)

        self.pid_path = os.path.join(home_dir, "phone-cli.pid")
        self.state_path = os.path.join(home_dir, "state.json")
        self.socket_path = os.path.join(home_dir, "phone-cli.sock")
        self.lock_path = os.path.join(home_dir, "phone-cli.lock")
        self.log_dir = os.path.join(home_dir, "logs")
        self.screenshot_dir = os.path.join(home_dir, "screenshots")
        self.logger = _setup_logger(self.log_dir)
        self._stop_event = threading.Event()

    def status(self) -> dict[str, Any]:
        """Check daemon status. Returns status dict."""
        if not os.path.exists(self.pid_path):
            return {"status": "stopped"}

        try:
            with open(self.pid_path, "r") as f:
                pid = int(f.read().strip())
        except (ValueError, FileNotFoundError):
            return {"status": "stopped"}

        if not self._is_pid_alive(pid):
            self._cleanup_pid()
            return {"status": "stopped"}

        state = self._read_state()
        state["status"] = "running"
        state["pid"] = pid
        return state

    def start(
        self,
        device_type: str = "adb",
        device_id: str | None = None,
        foreground: bool = False,
    ) -> dict[str, Any]:
        """Start the daemon. Returns status dict."""
        current = self.status()
        if current["status"] == "running":
            return {"status": "already_running", "pid": current.get("pid")}

        if foreground:
            return self._run_foreground(device_type, device_id)
        else:
            return self._run_background(device_type, device_id)

    def stop(self) -> dict[str, Any]:
        """Stop the daemon."""
        current = self.status()
        if current["status"] != "running":
            return {"status": "not_running"}

        pid = current.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                for _ in range(50):
                    if not self._is_pid_alive(pid):
                        break
                    time.sleep(0.1)
            except ProcessLookupError:
                pass

        self._cleanup_pid()
        self._cleanup_socket()
        return {"status": "stopped"}

    def _run_foreground(
        self, device_type: str, device_id: str | None
    ) -> dict[str, Any]:
        """Run daemon in foreground (blocks until stopped).

        This method writes state, starts the heartbeat thread, registers
        a SIGTERM handler, then enters the blocking socket-server loop.
        It only returns after the daemon is signalled to stop.
        """
        with open(self.pid_path, "w") as f:
            f.write(str(os.getpid()))

        state = {
            "status": "running",
            "device_type": device_type,
            "device_id": device_id,
            "device_status": "connected",
            "started_at": datetime.now().isoformat(),
        }
        self._write_state(state)

        # Register SIGTERM handler for graceful shutdown
        def _handle_sigterm(signum: int, frame: Any) -> None:
            self.logger.info("Received SIGTERM, shutting down")
            self._stop_event.set()
            self._cleanup_pid()
            self._cleanup_socket()

        signal.signal(signal.SIGTERM, _handle_sigterm)

        self._stop_event.clear()
        self._start_heartbeat(device_type, device_id)
        # _start_socket_server blocks until _stop_event is set
        self._start_socket_server()
        return state

    def _run_background(
        self, device_type: str, device_id: str | None
    ) -> dict[str, Any]:
        """Fork daemon to background."""
        import subprocess
        import sys

        cmd = [
            sys.executable, "-m", "phone_cli.cli.main",
            "start", "--device-type", device_type, "--foreground",
        ]
        if device_id:
            cmd.extend(["--device-id", device_id])

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        time.sleep(1)
        return self.status()

    def _start_socket_server(self) -> None:
        """Start Unix socket server for IPC with queue depth limit.

        This is the daemon's main loop — it blocks until _stop_event is set.
        """
        self._cleanup_socket()

        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self.socket_path)
        self._server_socket.listen(10)
        self._pending_count = 0
        self._lock = threading.Lock()

        while not self._stop_event.is_set():
            try:
                self._server_socket.settimeout(1.0)
                try:
                    conn, _ = self._server_socket.accept()
                except socket.timeout:
                    continue

                with self._lock:
                    if self._pending_count >= MAX_QUEUE_DEPTH:
                        from phone_cli.cli.output import ErrorCode, error_response
                        conn.sendall(
                            error_response(
                                ErrorCode.QUEUE_FULL, "Request queue full"
                            ).encode("utf-8")
                        )
                        conn.close()
                        continue
                    self._pending_count += 1

                data = conn.recv(65536).decode("utf-8")
                if data:
                    response = self._handle_request(data)
                    conn.sendall(response.encode("utf-8"))
                conn.close()

                with self._lock:
                    self._pending_count -= 1
            except OSError:
                break

    def _start_heartbeat(
        self, device_type: str, device_id: str | None
    ) -> None:
        """Start a background thread to check device connectivity."""

        def _heartbeat_loop() -> None:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=HEARTBEAT_INTERVAL)
                if self._stop_event.is_set():
                    break
                try:
                    if device_type == "adb":
                        from phone_cli import adb
                        devices = adb.list_devices()
                    elif device_type == "hdc":
                        from phone_cli import hdc
                        devices = hdc.list_devices()
                    elif device_type == "ios":
                        from phone_cli import ios
                        devices = ios.list_devices()
                    else:
                        continue

                    device_ids = [d.device_id for d in devices]
                    state = self._read_state()
                    target_id = device_id or state.get("device_id")

                    if target_id and target_id not in device_ids:
                        state["device_status"] = "disconnected"
                    else:
                        state["device_status"] = "connected"
                    self._write_state(state)
                except Exception:
                    self.logger.exception("Heartbeat check failed")

        self._stop_event.clear()
        t = threading.Thread(target=_heartbeat_loop, daemon=True)
        t.start()

    def _handle_request(self, data: str) -> str:
        """Handle a single IPC request. Returns JSON response."""
        try:
            request = json.loads(data)
            cmd = request.get("cmd")
            args = request.get("args", {})
            from phone_cli.cli.commands import dispatch_command
            return dispatch_command(cmd, args, self)
        except Exception as e:
            from phone_cli.cli.output import ErrorCode, error_response
            return error_response(ErrorCode.UNKNOWN_COMMAND, str(e))

    def send_command(self, cmd: str, args: dict | None = None) -> str:
        """Send a command to the running daemon via socket. Returns JSON string."""
        if not os.path.exists(self.socket_path):
            from phone_cli.cli.output import ErrorCode, error_response
            return error_response(
                ErrorCode.DAEMON_NOT_RUNNING, "Daemon is not running"
            )

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self.socket_path)
            sock.settimeout(15.0)
            payload = json.dumps({"cmd": cmd, "args": args or {}})
            sock.sendall(payload.encode("utf-8"))
            response = sock.recv(1048576).decode("utf-8")
            return response
        except socket.timeout:
            from phone_cli.cli.output import ErrorCode, error_response
            return error_response(
                ErrorCode.COMMAND_TIMEOUT, "Command timed out"
            )
        except ConnectionRefusedError:
            from phone_cli.cli.output import ErrorCode, error_response
            return error_response(
                ErrorCode.DAEMON_NOT_RUNNING, "Cannot connect to daemon"
            )
        finally:
            sock.close()

    def _write_state(self, state: dict[str, Any]) -> None:
        """Write state dict to disk atomically via tmp + os.replace."""
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.state_path)

    def _read_state(self) -> dict[str, Any]:
        if not os.path.exists(self.state_path):
            return {}
        try:
            with open(self.state_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _is_pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _cleanup_pid(self) -> None:
        for path in [self.pid_path, self.lock_path]:
            if os.path.exists(path):
                os.remove(path)

    def _cleanup_socket(self) -> None:
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
