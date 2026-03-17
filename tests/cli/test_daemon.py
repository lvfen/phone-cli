import json
import os
import tempfile
from unittest.mock import patch

from phone_cli.cli.daemon import PhoneCLIDaemon


def test_daemon_init_creates_home_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        assert os.path.isdir(tmpdir)
        assert daemon.pid_path == os.path.join(tmpdir, "phone-cli.pid")
        assert daemon.state_path == os.path.join(tmpdir, "state.json")
        assert daemon.socket_path == os.path.join(tmpdir, "phone-cli.sock")


def test_daemon_status_when_not_running():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        status = daemon.status()
        assert status["status"] == "stopped"


def test_daemon_status_detects_stale_pid():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        with open(daemon.pid_path, "w") as f:
            f.write("99999999")
        status = daemon.status()
        assert status["status"] == "stopped"
        assert not os.path.exists(daemon.pid_path)


def test_daemon_write_and_read_state():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        state = {
            "status": "running",
            "device_type": "adb",
            "device_id": "emulator-5554",
        }
        daemon._write_state(state)
        read_state = daemon._read_state()
        assert read_state["device_type"] == "adb"
        assert read_state["device_id"] == "emulator-5554"


def test_daemon_is_pid_alive_returns_false_for_nonexistent():
    daemon = PhoneCLIDaemon()
    assert daemon._is_pid_alive(99999999) is False
