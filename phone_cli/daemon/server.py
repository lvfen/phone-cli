"""守护进程主循环：PID/socket 管理，accept loop，命令分发。"""
import json
import logging
import os
import signal
import socket
import threading
import time
from typing import Any

from phone_cli.daemon.device import DeviceManager
from phone_cli.daemon.protocol import error_response, ok_response, parse_request
from phone_cli.daemon.session import SessionManager
from phone_cli.daemon.watchdog import TimeoutWatchdog
from phone_cli.config.ports import is_port_available

logger = logging.getLogger(__name__)

class DaemonServer:
    """中央守护进程。"""
    def __init__(self, home_dir: str = "~/.phone-cli") -> None:
        self.home_dir = os.path.expanduser(home_dir)
        os.makedirs(self.home_dir, exist_ok=True)
        self.pid_path = os.path.join(self.home_dir, "phone-cli.pid")
        self.socket_path = os.path.join(self.home_dir, "phone-cli.sock")
        self.session_mgr = SessionManager()
        self.device_mgr = DeviceManager()
        self.watchdog = TimeoutWatchdog(
            self.session_mgr, self.device_mgr, on_expire=self._on_session_expire,
        )
        self._stop_event = threading.Event()
        self._server_socket: socket.socket | None = None
        self._handlers: dict[str, Any] = {
            "status": self._cmd_status,
            "acquire": self._cmd_acquire,
            "operate": self._cmd_operate,
            "release": self._cmd_release,
            "heartbeat": self._cmd_heartbeat,
            "list_devices": self._cmd_list_devices,
        }

    def run_foreground(self) -> None:
        self._cleanup_stale()
        self._write_pid()
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, lambda *_: self.shutdown())
        self.watchdog.start()
        self._run_socket_server()

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._server_socket:
            try: self._server_socket.close()
            except OSError: pass
        self.watchdog.stop()
        for slot in self.device_mgr.all_slots():
            if slot.process and slot.process.poll() is None:
                slot.process.terminate()
        for slot in self.device_mgr.all_slots():
            if slot.process and slot.process.poll() is None:
                try: slot.process.wait(timeout=5)
                except Exception: slot.process.kill()
        self._cleanup_files()

    def _run_socket_server(self) -> None:
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self.socket_path)
        self._server_socket.listen(10)
        self._server_socket.settimeout(1.0)
        while not self._stop_event.is_set():
            try:
                conn, _ = self._server_socket.accept()
            except socket.timeout: continue
            except OSError: break
            threading.Thread(target=self._handle_connection, args=(conn,), daemon=True).start()

    def _handle_connection(self, conn: socket.socket) -> None:
        try:
            data = conn.recv(65536).decode("utf-8")
            if not data: return
            response = self._dispatch(data)
            conn.sendall(response.encode("utf-8"))
        except Exception:
            logger.exception("Error handling connection")
        finally:
            conn.close()

    def _dispatch(self, raw: str) -> str:
        req = parse_request(raw)
        if req is None:
            return error_response("invalid_request", "Malformed request")
        handler = self._handlers.get(req.cmd)
        if handler is None:
            return error_response("invalid_request", f"Unknown command: {req.cmd}")
        try:
            return handler(req.args)
        except Exception as e:
            logger.exception("Command %s failed", req.cmd)
            return error_response("operation_failed", str(e))

    # ── Commands ──

    def _cmd_status(self, args: dict) -> str:
        sessions = [
            {"session_id": s.session_id, "device_id": s.device_id,
             "device_type": s.device_type, "status": s.status,
             "idle_seconds": round(time.time() - s.last_active_at, 1)}
            for s in self.session_mgr.active_sessions()
        ]
        devices = [
            {"device_id": slot.device_id, "device_type": slot.device_type,
             "port": slot.port, "status": "occupied" if slot.current_session_id else "idle"}
            for slot in self.device_mgr.all_slots()
        ]
        return ok_response({"sessions": sessions, "devices": devices})

    def _cmd_acquire(self, args: dict) -> str:
        device_type = args.get("device_type")
        if not device_type:
            return error_response("invalid_request", "device_type is required")
        timeout = float(args.get("timeout", 300))
        discovered = self.device_mgr.discover(device_type)
        if not discovered:
            return error_response("no_device_available", f"No {device_type} devices found")
        discovered_ids = [d.device_id for d in discovered]
        free_id = self.device_mgr.find_free_device(discovered_ids)
        if free_id:
            slot = self.device_mgr.get_slot(free_id)
            if slot is None:
                port = self.device_mgr.allocate_port(self._port_type(device_type))
                slot = self.device_mgr.create_slot(free_id, device_type, port)
            session = self.session_mgr.create(device_type, device_id=free_id, timeout=timeout)
            self.device_mgr.assign_session(free_id, session.session_id)
            return ok_response({
                "session_id": session.session_id, "status": "active",
                "device_id": free_id, "device_type": device_type, "port": slot.port,
            })
        # All busy → queue (non-blocking v1)
        queue_device = self.device_mgr.find_shortest_queue_device(discovered_ids)
        if not queue_device:
            return error_response("no_device_available", "No devices to queue on")
        session = self.session_mgr.create(device_type, device_id=None, timeout=timeout, status="queued")
        pos = self.device_mgr.enqueue_session(queue_device, session.session_id)
        return ok_response({"session_id": session.session_id, "status": "queued", "queue_position": pos})

    def _cmd_operate(self, args: dict) -> str:
        session_id = args.get("session_id")
        session = self.session_mgr.get(session_id) if session_id else None
        if not session:
            return error_response("session_not_found", "Unknown session")
        if session.status == "expired":
            return error_response("session_expired", "Session has expired")
        if session.status != "active":
            return error_response("session_not_found", f"Session status: {session.status}")
        self.session_mgr.touch(session_id)

        action = args.get("action", "")
        slot = self.device_mgr.get_slot(session.device_id) if session.device_id else None
        if not slot:
            return error_response("device_disconnected", "Device slot not found")

        with slot.lock:
            try:
                result = self._execute_device_action(slot, session, action, args)
                return ok_response({"action": action, "result": result})
            except Exception as e:
                return error_response("operation_failed", str(e))

    def _execute_device_action(self, slot, session, action: str, args: dict) -> dict:
        """将操作路由到对应平台模块。"""
        device_type = slot.device_type
        device_id = slot.device_id
        if device_type == "adb":
            from phone_cli import adb
            module = adb
        elif device_type == "hdc":
            from phone_cli import hdc
            module = hdc
        elif device_type == "ios":
            from phone_cli import ios
            module = ios
        else:
            raise ValueError(f"Unknown device type: {device_type}")
        method = getattr(module, action, None)
        if method is None:
            raise ValueError(f"Unknown action: {action} for {device_type}")
        op_args = {k: v for k, v in args.items() if k not in ("session_id", "action")}
        result = method(device_id=device_id, **op_args)
        return result if isinstance(result, dict) else {"raw": result}

    def _cmd_release(self, args: dict) -> str:
        session_id = args.get("session_id")
        session = self.session_mgr.release(session_id) if session_id else None
        if not session:
            return error_response("session_not_found", "Unknown session")
        if session.device_id:
            next_sid = self.device_mgr.release_session(session.device_id)
            if next_sid:
                self.session_mgr.activate(next_sid, session.device_id)
        return ok_response({"released": True})

    def _cmd_heartbeat(self, args: dict) -> str:
        session_id = args.get("session_id")
        session = self.session_mgr.get(session_id) if session_id else None
        if not session:
            return error_response("session_not_found", "Unknown session")
        self.session_mgr.touch(session_id)
        return ok_response({"alive": True})

    def _cmd_list_devices(self, args: dict) -> str:
        device_type = args.get("device_type")
        if not device_type:
            return error_response("invalid_request", "device_type is required")
        discovered = self.device_mgr.discover(device_type)
        devices = [{"device_id": d.device_id, "status": getattr(d, "status", "unknown")} for d in discovered]
        return ok_response({"devices": devices})

    # ── Internal ──

    @staticmethod
    def _port_type(device_type: str) -> str:
        return {"ios": "wda", "adb": "adb", "hdc": "hdc"}[device_type]

    def _on_session_expire(self, session_id: str) -> None:
        session = self.session_mgr.get(session_id)
        if session and session.device_id:
            next_sid = self.device_mgr.release_session(session.device_id)
            if next_sid:
                self.session_mgr.activate(next_sid, session.device_id)

    def _cleanup_stale(self) -> None:
        if os.path.exists(self.pid_path):
            try:
                with open(self.pid_path) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                raise RuntimeError(f"Daemon already running (pid={pid})")
            except (ProcessLookupError, PermissionError, ValueError):
                os.remove(self.pid_path)
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

    def _write_pid(self) -> None:
        with open(self.pid_path, "w") as f:
            f.write(str(os.getpid()))

    def _cleanup_files(self) -> None:
        for path in [self.pid_path, self.socket_path]:
            if os.path.exists(path):
                os.remove(path)
