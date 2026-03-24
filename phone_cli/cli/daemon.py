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

from phone_cli.cli.output import ErrorCode

DEFAULT_HOME = os.path.expanduser("~/.phone-cli")
INSTANCE_DIRNAME = "instances"
MANAGED_INSTANCE_NAMES = ("adb", "hdc", "ios")
MAX_QUEUE_DEPTH = 10
HEARTBEAT_INTERVAL = 30  # seconds


def _setup_logger(log_dir: str, *, logger_name: str) -> logging.Logger:
    """Set up file logger with daily rotation, 30-day retention."""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_path = os.path.join(log_dir, "phone-cli.log")
    handler_exists = any(
        getattr(handler, "baseFilename", None) == os.path.abspath(log_path)
        for handler in logger.handlers
    )
    if not handler_exists:
        handler = TimedRotatingFileHandler(
            log_path,
            when="midnight", backupCount=30, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s"
        ))
        logger.addHandler(handler)
    return logger


class PhoneCLIDaemon:
    """Manages the phone-cli background daemon process."""

    def __init__(
        self,
        home_dir: str = DEFAULT_HOME,
        instance_name: str | None = None,
        resolve_instances: bool | None = None,
    ):
        self.base_home_dir = home_dir
        self.instance_name = instance_name
        if resolve_instances is None:
            resolve_instances = (
                instance_name is None
                and os.path.abspath(home_dir) == os.path.abspath(DEFAULT_HOME)
            )
        self.resolve_instances = resolve_instances
        self.home_dir = self._resolve_home_dir(home_dir, instance_name)
        os.makedirs(self.home_dir, exist_ok=True)

        self.pid_path = os.path.join(self.home_dir, "phone-cli.pid")
        self.state_path = os.path.join(self.home_dir, "state.json")
        self.socket_path = os.path.join(self.home_dir, "phone-cli.sock")
        self.lock_path = os.path.join(self.home_dir, "phone-cli.lock")
        self.log_dir = os.path.join(self.home_dir, "logs")
        self.screenshot_dir = os.path.join(self.home_dir, "screenshots")
        self.logger = _setup_logger(
            self.log_dir,
            logger_name=f"phone-cli.{instance_name or ('resolver' if self.resolve_instances else 'default')}",
        )
        self._stop_event = threading.Event()

    def status(self) -> dict[str, Any]:
        """Check daemon status. Returns status dict."""
        if self.resolve_instances:
            running_instances = [
                status
                for _, status in self._list_running_instances()
            ]
            if not running_instances:
                return {"status": "stopped"}
            if len(running_instances) == 1:
                return running_instances[0]
            return {
                "status": "multi_running",
                "instances": running_instances,
            }

        return self._status_current_instance()

    def _status_current_instance(self) -> dict[str, Any]:
        """Check status for the current concrete daemon instance."""
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
        if self.instance_name:
            state["instance_name"] = self.instance_name
        return state

    def start(
        self,
        device_type: str = "adb",
        device_id: str | None = None,
        ios_runtime: str | None = None,
        foreground: bool = False,
    ) -> dict[str, Any]:
        """Start the daemon. Returns status dict."""
        if self.resolve_instances:
            return self._instance_daemon(device_type).start(
                device_type=device_type,
                device_id=device_id,
                ios_runtime=ios_runtime,
                foreground=foreground,
            )

        if self.instance_name and self.instance_name != device_type:
            return self._error_result(
                ErrorCode.COMMAND_FAILED,
                f"Daemon instance {self.instance_name} does not match device type {device_type}.",
            )

        current = self.status()
        if current["status"] == "running":
            return {"status": "already_running", "pid": current.get("pid")}

        start_state = self._resolve_start_state(
            device_type=device_type,
            device_id=device_id,
            ios_runtime=ios_runtime,
        )
        if start_state.get("error_code"):
            return start_state

        if foreground:
            return self._run_foreground(start_state)
        else:
            return self._run_background(start_state)

    def stop(self, all_instances: bool = False) -> dict[str, Any]:
        """Stop the daemon."""
        if self.resolve_instances:
            running_instances = self._list_running_instances()
            if not running_instances:
                return {"status": "not_running"}
            if all_instances:
                stopped_instances = []
                for daemon, status in running_instances:
                    result = daemon.stop()
                    if result.get("status") == "stopped":
                        stopped_instances.append(
                            status.get("instance_name")
                            or daemon.instance_name
                            or status.get("device_type")
                            or "legacy"
                        )
                return {
                    "status": "stopped",
                    "stopped_instances": stopped_instances,
                }
            if len(running_instances) > 1:
                return self._error_result(
                    ErrorCode.INSTANCE_SELECTION_REQUIRED,
                    "Multiple daemon instances are running; specify --instance adb|hdc|ios or use stop --all.",
                )
            daemon, _ = running_instances[0]
            return daemon.stop()

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

    def _run_foreground(self, start_state: dict[str, Any]) -> dict[str, Any]:
        """Run daemon in foreground (blocks until stopped).

        This method writes state, starts the heartbeat thread, registers
        a SIGTERM handler, then enters the blocking socket-server loop.
        It only returns after the daemon is signalled to stop.
        """
        with open(self.pid_path, "w") as f:
            f.write(str(os.getpid()))

        state = dict(start_state)
        state["status"] = "running"
        state["started_at"] = datetime.now().isoformat()
        if self.instance_name:
            state["instance_name"] = self.instance_name
        self._write_state(state)

        # Register SIGTERM handler for graceful shutdown
        def _handle_sigterm(signum: int, frame: Any) -> None:
            self.logger.info("Received SIGTERM, shutting down")
            self._stop_event.set()
            self._cleanup_pid()
            self._cleanup_socket()

        signal.signal(signal.SIGTERM, _handle_sigterm)

        self._stop_event.clear()
        self._start_heartbeat(state)
        # _start_socket_server blocks until _stop_event is set
        self._start_socket_server()
        return state

    def _run_background(self, start_state: dict[str, Any]) -> dict[str, Any]:
        """Fork daemon to background."""
        import subprocess
        import sys

        cmd = [
            sys.executable, "-m", "phone_cli.cli.main",
            "start", "--device-type", start_state["device_type"], "--foreground",
        ]
        if start_state.get("device_id"):
            cmd.extend(["--device-id", start_state["device_id"]])
        if start_state.get("ios_runtime"):
            runtime = str(start_state["ios_runtime"]).replace("_", "-")
            cmd.extend(["--runtime", runtime])

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

    def _start_heartbeat(self, initial_state: dict[str, Any]) -> None:
        """Start a background thread to check device connectivity."""

        def _heartbeat_loop() -> None:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=HEARTBEAT_INTERVAL)
                if self._stop_event.is_set():
                    break
                try:
                    state = self._read_state()
                    device_type = state.get(
                        "device_type",
                        initial_state.get("device_type"),
                    )
                    if device_type == "adb":
                        from phone_cli import adb
                        devices = adb.list_devices()
                        target_id = state.get("device_id") or initial_state.get("device_id")
                        device_ids = [d.device_id for d in devices]
                        connected = bool(device_ids) if not target_id else target_id in device_ids
                    elif device_type == "hdc":
                        from phone_cli import hdc
                        devices = hdc.list_devices()
                        target_id = state.get("device_id") or initial_state.get("device_id")
                        device_ids = [d.device_id for d in devices]
                        connected = bool(device_ids) if not target_id else target_id in device_ids
                    elif device_type == "ios":
                        connected = self._check_ios_connectivity(state or initial_state)
                    else:
                        continue

                    state["device_status"] = "connected" if connected else "disconnected"
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
        if self.resolve_instances:
            running_instances = self._list_running_instances()
            if not running_instances:
                from phone_cli.cli.output import ErrorCode, error_response

                return error_response(
                    ErrorCode.DAEMON_NOT_RUNNING,
                    "No daemon instance is running",
                )
            if len(running_instances) > 1:
                from phone_cli.cli.output import ErrorCode, error_response

                return error_response(
                    ErrorCode.INSTANCE_SELECTION_REQUIRED,
                    "Multiple daemon instances are running; specify --instance adb|hdc|ios.",
                )
            daemon, _ = running_instances[0]
            return daemon.send_command(cmd, args)

        if not os.path.exists(self.socket_path):
            from phone_cli.cli.output import ErrorCode, error_response
            return error_response(
                ErrorCode.DAEMON_NOT_RUNNING, "Daemon is not running"
            )

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self.socket_path)
            resolved_args = args or {}
            sock.settimeout(self._get_command_timeout(cmd, resolved_args))
            payload = json.dumps({"cmd": cmd, "args": resolved_args})
            sock.sendall(payload.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8")
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

    def _get_command_timeout(self, cmd: str, args: dict[str, Any]) -> float:
        """Return a client-side IPC timeout for the given command."""

        base_timeout = 15.0
        if cmd == "wait_for_app":
            requested_timeout = float(args.get("timeout", 30) or 30)
            return max(base_timeout, requested_timeout + 5.0)
        if cmd == "install":
            return 120.0
        return base_timeout

    @staticmethod
    def _resolve_home_dir(base_home_dir: str, instance_name: str | None) -> str:
        """Resolve a concrete daemon home directory for the given instance."""

        if not instance_name:
            return base_home_dir
        return os.path.join(base_home_dir, INSTANCE_DIRNAME, instance_name)

    def _instance_daemon(self, instance_name: str) -> "PhoneCLIDaemon":
        """Create a concrete daemon bound to a specific managed instance."""

        return PhoneCLIDaemon(
            home_dir=self.base_home_dir,
            instance_name=instance_name,
            resolve_instances=False,
        )

    def _legacy_daemon(self) -> "PhoneCLIDaemon":
        """Create a concrete daemon for the legacy single-instance layout."""

        return PhoneCLIDaemon(
            home_dir=self.base_home_dir,
            resolve_instances=False,
        )

    def _list_running_instances(self) -> list[tuple["PhoneCLIDaemon", dict[str, Any]]]:
        """List all currently running concrete daemon instances."""

        instances: list[tuple["PhoneCLIDaemon", dict[str, Any]]] = []
        seen_home_dirs: set[str] = set()

        for daemon in [
            *(self._instance_daemon(name) for name in MANAGED_INSTANCE_NAMES),
            self._legacy_daemon(),
        ]:
            resolved_home_dir = os.path.abspath(daemon.home_dir)
            if resolved_home_dir in seen_home_dirs:
                continue
            seen_home_dirs.add(resolved_home_dir)

            status = daemon._status_current_instance()
            if status.get("status") != "running":
                continue
            if not status.get("instance_name"):
                status["instance_name"] = (
                    daemon.instance_name
                    or status.get("device_type")
                    or "legacy"
                )
            instances.append((daemon, status))

        return instances

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

    def _resolve_start_state(
        self,
        device_type: str,
        device_id: str | None,
        ios_runtime: str | None,
    ) -> dict[str, Any]:
        """Resolve runtime-specific startup state before the daemon boots."""

        state = {
            "device_type": device_type,
            "device_id": device_id,
            "target_id": device_id,
            "device_status": "connected",
            "bundle_id": None,
            "window_id": None,
            "capabilities": {},
        }

        if device_type != "ios":
            return state

        from phone_cli import ios
        from phone_cli.ios.runtime.discovery import detect_ios_runtimes, resolve_runtime_selection
        from phone_cli.ios.runtime.router import normalize_runtime

        discovery = detect_ios_runtimes()
        selected_candidate = None

        if ios_runtime:
            resolved_runtime = normalize_runtime(ios_runtime)
            matching_candidates = [
                candidate
                for candidate in discovery.candidates
                if candidate.runtime == resolved_runtime
            ]
            if not matching_candidates:
                return self._error_result(
                    ErrorCode.RUNTIME_NOT_SUPPORTED,
                    f"Requested iOS runtime is not available: {resolved_runtime}",
                )

            if device_id:
                selected_candidate = next(
                    (
                        candidate
                        for candidate in matching_candidates
                        if candidate.target_id == device_id
                    ),
                    None,
                )
                if selected_candidate is None and resolved_runtime != "app_on_mac":
                    return self._error_result(
                        ErrorCode.TARGET_NOT_SELECTED,
                        f"Requested iOS target was not found for runtime {resolved_runtime}: {device_id}",
                    )
            elif len(matching_candidates) == 1:
                selected_candidate = matching_candidates[0]
            elif len(matching_candidates) > 1:
                return self._error_result(
                    ErrorCode.TARGET_NOT_SELECTED,
                    f"Multiple iOS targets were detected for runtime {resolved_runtime}; specify --device-id.",
                )
        else:
            selection = resolve_runtime_selection(discovery)
            if selection.mode == "unavailable":
                return self._error_result(
                    selection.error_code or ErrorCode.NO_AVAILABLE_IOS_RUNTIME,
                    selection.message or "No available iOS runtime candidates were detected.",
                )
            if selection.mode == "selection_required":
                return self._error_result(
                    selection.error_code or ErrorCode.RUNTIME_SELECTION_REQUIRED,
                    (
                        selection.message
                        or "Multiple iOS runtime candidates were detected; use detect-runtimes or specify --runtime."
                    ),
                )
            selected_candidate = selection.candidate
            resolved_runtime = selected_candidate.runtime if selected_candidate else "device"

        target_id = None
        resolved_device_id = device_id
        if selected_candidate is not None:
            target_id = selected_candidate.target_id
            if selected_candidate.runtime != "app_on_mac":
                resolved_device_id = selected_candidate.target_id
        elif resolved_runtime == "app_on_mac":
            target_id = "local-mac"
            resolved_device_id = None
        else:
            target_id = device_id

        capabilities = ios.get_capabilities(runtime=resolved_runtime)
        state.update(
            {
                "ios_runtime": resolved_runtime,
                "device_id": resolved_device_id,
                "target_id": target_id,
                "device_status": "connected",
                "capabilities": capabilities,
            }
        )

        if target_id:
            try:
                width, height = ios.get_screen_size(
                    device_id=target_id,
                    runtime=resolved_runtime,
                )
                state["screen_size"] = [width, height]
            except Exception:
                pass

        return state

    def _check_ios_connectivity(self, state: dict[str, Any]) -> bool:
        """Check connectivity for the currently selected iOS runtime."""

        runtime = state.get("ios_runtime", "device")
        target_id = state.get("target_id") or state.get("device_id")

        if runtime in {"device", "simulator"}:
            from phone_cli import ios

            targets = ios.list_devices(runtime=runtime)
            target_ids = [target.device_id for target in targets]
            return bool(target_ids) if not target_id else target_id in target_ids

        if runtime == "app_on_mac":
            from phone_cli.ios.host import check_app_on_mac_host_support, get_window

            if not check_app_on_mac_host_support().supported:
                return False
            window_id = state.get("window_id")
            if window_id is None:
                return True
            try:
                get_window(window_id)
                return True
            except Exception:
                return False

        return False

    def _error_result(self, error_code: str, error_msg: str) -> dict[str, Any]:
        """Return a structured error payload for CLI-level command handling."""

        return {
            "error_code": error_code,
            "error_msg": error_msg,
        }
