import json
import os
import socket
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch
from phone_cli.daemon.server import DaemonServer

def _start_server(tmpdir):
    server = DaemonServer(home_dir=tmpdir)
    t = threading.Thread(target=server.run_foreground, daemon=True)
    t.start()
    time.sleep(0.3)
    return server, t

def _ipc(socket_path, cmd, args=None):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(socket_path)
    sock.sendall(json.dumps({"cmd": cmd, "args": args or {}}).encode())
    sock.shutdown(socket.SHUT_WR)
    data = sock.recv(65536).decode()
    sock.close()
    return json.loads(data)

class TestOperateRouting:
    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_tap_routes_to_device(self, mock_list):
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                resp = _ipc(server.socket_path, "acquire", {"device_type": "adb"})
                assert resp["ok"] is True
                sid = resp["session_id"]

                with patch.object(server, "_execute_device_action") as mock_exec:
                    mock_exec.return_value = {"tapped": True}
                    resp = _ipc(server.socket_path, "operate", {
                        "session_id": sid, "action": "tap", "x": 100, "y": 200,
                    })
                    assert resp["ok"] is True
                    mock_exec.assert_called_once()
            finally:
                server.shutdown()
                t.join(timeout=2)
