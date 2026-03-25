import json
import os
import socket
import tempfile
import threading
import time
from unittest.mock import patch
from phone_cli.client import PhoneClient
from phone_cli.daemon.server import DaemonServer

def _start_server(tmpdir: str) -> tuple[DaemonServer, threading.Thread]:
    server = DaemonServer(home_dir=tmpdir)
    t = threading.Thread(target=server.run_foreground, daemon=True)
    t.start()
    time.sleep(0.3)
    return server, t

class TestPhoneClientAcquireRelease:
    def test_acquire_and_release(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("phone_cli.daemon.device.adb_list_devices", return_value=[]):
                server, t = _start_server(tmpdir)
                try:
                    client = PhoneClient(socket_path=server.socket_path)
                    resp = client.acquire(device_type="adb")
                    assert resp["ok"] is False
                    assert resp["error"] == "no_device_available"
                finally:
                    server.shutdown()
                    t.join(timeout=2)

class TestPhoneClientHeartbeat:
    def test_heartbeat_unknown_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client = PhoneClient(socket_path=server.socket_path)
                resp = client.heartbeat()
                assert resp["ok"] is False
                assert resp["error"] == "session_not_found"
            finally:
                server.shutdown()
                t.join(timeout=2)

class TestPhoneClientStatus:
    def test_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client = PhoneClient(socket_path=server.socket_path)
                resp = client.status()
                assert resp["ok"] is True
                assert "sessions" in resp
                assert "devices" in resp
            finally:
                server.shutdown()
                t.join(timeout=2)
