import json
import os
import socket
import tempfile
import threading
import time
from phone_cli.daemon.server import DaemonServer

class TestDaemonLifecycle:
    def test_start_creates_pid_and_socket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)
            assert os.path.exists(server.pid_path)
            assert os.path.exists(server.socket_path)
            server.shutdown()
            t.join(timeout=2)

    def test_shutdown_removes_pid_and_socket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)
            server.shutdown()
            t.join(timeout=2)
            assert not os.path.exists(server.pid_path)
            assert not os.path.exists(server.socket_path)

    def test_stale_pid_cleaned_on_start(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_path = os.path.join(tmpdir, "phone-cli.pid")
            with open(pid_path, "w") as f:
                f.write("99999999")
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)
            assert os.path.exists(server.pid_path)
            with open(server.pid_path) as f:
                assert f.read().strip() == str(os.getpid())
            server.shutdown()
            t.join(timeout=2)

class TestDaemonIPC:
    def test_status_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(server.socket_path)
            sock.sendall(json.dumps({"cmd": "status"}).encode())
            sock.shutdown(socket.SHUT_WR)
            data = sock.recv(65536).decode()
            sock.close()
            resp = json.loads(data)
            assert resp["ok"] is True
            server.shutdown()
            t.join(timeout=2)

    def test_invalid_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server = DaemonServer(home_dir=tmpdir)
            t = threading.Thread(target=server.run_foreground)
            t.daemon = True
            t.start()
            time.sleep(0.3)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(server.socket_path)
            sock.sendall(json.dumps({"cmd": "bogus"}).encode())
            sock.shutdown(socket.SHUT_WR)
            data = sock.recv(65536).decode()
            sock.close()
            resp = json.loads(data)
            assert resp["ok"] is False
            assert resp["error"] == "invalid_request"
            server.shutdown()
            t.join(timeout=2)
