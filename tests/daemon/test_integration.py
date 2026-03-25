"""集成测试：通过 PhoneClient 和真实 DaemonServer 验证完整流程。"""
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch
from phone_cli.client import PhoneClient
from phone_cli.daemon.server import DaemonServer

def _start_server(tmpdir):
    server = DaemonServer(home_dir=tmpdir)
    t = threading.Thread(target=server.run_foreground, daemon=True)
    t.start()
    time.sleep(0.3)
    return server, t

class TestFullLifecycle:
    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_acquire_operate_release(self, mock_list):
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client = PhoneClient(socket_path=server.socket_path)
                resp = client.acquire(device_type="adb")
                assert resp["ok"] is True
                assert resp["status"] == "active"
                assert resp["device_id"] == "emu-5554"
                assert client.session_id is not None
                status = client.status()
                assert len(status["sessions"]) == 1
                resp = client.release()
                assert resp["ok"] is True
                status = client.status()
                assert len(status["sessions"]) == 0
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_multiple_sessions_different_devices(self, mock_list):
        mock_list.return_value = [
            MagicMock(device_id="emu-5554", status="device"),
            MagicMock(device_id="emu-5556", status="device"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client1 = PhoneClient(socket_path=server.socket_path)
                client2 = PhoneClient(socket_path=server.socket_path)
                resp1 = client1.acquire(device_type="adb")
                resp2 = client2.acquire(device_type="adb")
                assert resp1["ok"] is True
                assert resp2["ok"] is True
                assert resp1["device_id"] != resp2["device_id"]
                assert resp1["port"] != resp2["port"]
                client1.release()
                client2.release()
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_queue_when_all_busy(self, mock_list):
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client1 = PhoneClient(socket_path=server.socket_path)
                client2 = PhoneClient(socket_path=server.socket_path)
                resp1 = client1.acquire(device_type="adb")
                assert resp1["ok"] is True
                assert resp1["status"] == "active"
                resp2 = client2.acquire(device_type="adb")
                assert resp2["ok"] is True
                assert resp2["status"] == "queued"
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_session_timeout_expiry(self, mock_list):
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            # Use fast watchdog for testing
            from phone_cli.daemon.watchdog import TimeoutWatchdog
            server.watchdog = TimeoutWatchdog(
                server.session_mgr, server.device_mgr, check_interval=0.05
            )
            t = threading.Thread(target=server.run_foreground, daemon=True)
            t.start()
            time.sleep(0.3)
            try:
                client = PhoneClient(socket_path=server.socket_path)
                resp = client.acquire(device_type="adb", timeout=0.1)
                assert resp["ok"] is True
                time.sleep(0.3)
                resp = client.operate("tap", x=100, y=200)
                assert resp["ok"] is False
                assert resp["error"] == "session_expired"
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_concurrent_acquire_no_duplicate_ports(self, mock_list):
        """多线程并发 acquire 不应分配重复端口。"""
        mock_list.return_value = [
            MagicMock(device_id=f"emu-{i}", status="device") for i in range(10)
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                results = []
                errors = []
                def _acquire(idx):
                    try:
                        client = PhoneClient(socket_path=server.socket_path)
                        resp = client.acquire(device_type="adb")
                        results.append(resp)
                    except Exception as e:
                        errors.append(e)
                threads = [threading.Thread(target=_acquire, args=(i,)) for i in range(5)]
                for th in threads: th.start()
                for th in threads: th.join(timeout=5)
                assert not errors
                active = [r for r in results if r.get("status") == "active"]
                ports = [r["port"] for r in active]
                device_ids = [r["device_id"] for r in active]
                assert len(ports) == len(set(ports))
                assert len(device_ids) == len(set(device_ids))
            finally:
                server.shutdown()
                t.join(timeout=2)

    @patch("phone_cli.daemon.device.adb_list_devices")
    def test_queue_activation_after_release(self, mock_list):
        """释放设备后，排队会话应被激活。"""
        mock_list.return_value = [MagicMock(device_id="emu-5554", status="device")]
        with tempfile.TemporaryDirectory() as tmpdir:
            server, t = _start_server(tmpdir)
            try:
                client1 = PhoneClient(socket_path=server.socket_path)
                client2 = PhoneClient(socket_path=server.socket_path)
                resp1 = client1.acquire(device_type="adb")
                assert resp1["status"] == "active"
                resp2 = client2.acquire(device_type="adb")
                assert resp2["status"] == "queued"
                queued_sid = resp2["session_id"]
                client1.release()
                session = server.session_mgr.get(queued_sid)
                assert session.status == "active"
                assert session.device_id == "emu-5554"
            finally:
                server.shutdown()
                t.join(timeout=2)
