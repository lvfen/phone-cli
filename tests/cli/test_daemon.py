import json
import os
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

from phone_cli.cli.daemon import PhoneCLIDaemon
from phone_cli.ios.runtime.discovery import RuntimeCandidate, RuntimeDiscoveryResult


def test_daemon_init_creates_home_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        assert os.path.isdir(tmpdir)
        assert daemon.pid_path == os.path.join(tmpdir, "phone-cli.pid")
        assert daemon.state_path == os.path.join(tmpdir, "state.json")
        assert daemon.socket_path == os.path.join(tmpdir, "phone-cli.sock")


def test_daemon_init_with_instance_uses_isolated_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir, instance_name="ios")
        instance_home = os.path.join(tmpdir, "instances", "ios")
        assert daemon.home_dir == instance_home
        assert daemon.pid_path == os.path.join(instance_home, "phone-cli.pid")
        assert daemon.state_path == os.path.join(instance_home, "state.json")
        assert daemon.socket_path == os.path.join(instance_home, "phone-cli.sock")


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


def test_daemon_get_command_timeout_extends_wait_for_app():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        assert daemon._get_command_timeout("wait_for_app", {"timeout": 42}) == 47.0
        assert daemon._get_command_timeout("wait_for_app", {}) == 35.0
        assert daemon._get_command_timeout("install", {}) == 120.0
        assert daemon._get_command_timeout("tap", {}) == 15.0


def test_daemon_is_pid_alive_returns_false_for_nonexistent():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
    assert daemon._is_pid_alive(99999999) is False


def test_daemon_resolver_status_reports_multiple_running_instances():
    with tempfile.TemporaryDirectory() as tmpdir:
        adb_daemon = PhoneCLIDaemon(
            home_dir=tmpdir,
            instance_name="adb",
            resolve_instances=False,
        )
        ios_daemon = PhoneCLIDaemon(
            home_dir=tmpdir,
            instance_name="ios",
            resolve_instances=False,
        )
        with open(adb_daemon.pid_path, "w") as f:
            f.write(str(os.getpid()))
        adb_daemon._write_state({"device_type": "adb", "device_status": "connected"})

        with open(ios_daemon.pid_path, "w") as f:
            f.write(str(os.getpid()))
        ios_daemon._write_state({"device_type": "ios", "device_status": "connected"})

        resolver = PhoneCLIDaemon(home_dir=tmpdir, resolve_instances=True)
        status = resolver.status()

        assert status["status"] == "multi_running"
        assert {item["instance_name"] for item in status["instances"]} == {"adb", "ios"}


def test_daemon_resolver_send_command_requires_instance_when_multiple_running():
    with tempfile.TemporaryDirectory() as tmpdir:
        adb_daemon = PhoneCLIDaemon(
            home_dir=tmpdir,
            instance_name="adb",
            resolve_instances=False,
        )
        ios_daemon = PhoneCLIDaemon(
            home_dir=tmpdir,
            instance_name="ios",
            resolve_instances=False,
        )
        with open(adb_daemon.pid_path, "w") as f:
            f.write(str(os.getpid()))
        adb_daemon._write_state({"device_type": "adb", "device_status": "connected"})

        with open(ios_daemon.pid_path, "w") as f:
            f.write(str(os.getpid()))
        ios_daemon._write_state({"device_type": "ios", "device_status": "connected"})

        resolver = PhoneCLIDaemon(home_dir=tmpdir, resolve_instances=True)
        parsed = json.loads(resolver.send_command("devices"))

        assert parsed["status"] == "error"
        assert parsed["error_code"] == "INSTANCE_SELECTION_REQUIRED"


def test_daemon_resolver_stop_all_stops_every_running_instance():
    with tempfile.TemporaryDirectory() as tmpdir:
        resolver = PhoneCLIDaemon(home_dir=tmpdir, resolve_instances=True)
        adb_daemon = MagicMock()
        adb_daemon.instance_name = "adb"
        adb_daemon.stop.return_value = {"status": "stopped"}
        ios_daemon = MagicMock()
        ios_daemon.instance_name = "ios"
        ios_daemon.stop.return_value = {"status": "stopped"}

        with patch.object(
            resolver,
            "_list_running_instances",
            return_value=[
                (adb_daemon, {"instance_name": "adb"}),
                (ios_daemon, {"instance_name": "ios"}),
            ],
        ):
            result = resolver.stop(all_instances=True)

        assert result == {
            "status": "stopped",
            "stopped_instances": ["adb", "ios"],
        }


def test_daemon_start_ios_auto_selects_single_candidate():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        discovery = RuntimeDiscoveryResult(
            candidates=[
                RuntimeCandidate(
                    runtime="simulator",
                    target_id="sim-1",
                    label="iPhone 16 Pro (Booted)",
                )
            ],
            reasons=[],
        )
        with patch("phone_cli.cli.daemon.PhoneCLIDaemon.status", return_value={"status": "stopped"}), \
             patch("phone_cli.ios.runtime.discovery.detect_ios_runtimes", return_value=discovery), \
             patch("phone_cli.ios.get_capabilities", return_value={"launch": False}), \
             patch("phone_cli.cli.daemon.PhoneCLIDaemon._run_background") as mock_run:
            mock_run.return_value = {"status": "running", "ios_runtime": "simulator"}
            result = daemon.start(device_type="ios")
        assert result["ios_runtime"] == "simulator"
        start_state = mock_run.call_args.args[0]
        assert start_state["ios_runtime"] == "simulator"
        assert start_state["device_id"] == "sim-1"
        assert start_state["target_id"] == "sim-1"


def test_daemon_start_ios_requires_selection_for_multiple_candidates():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        discovery = RuntimeDiscoveryResult(
            candidates=[
                RuntimeCandidate(runtime="device", target_id="dev-1", label="iPhone"),
                RuntimeCandidate(runtime="simulator", target_id="sim-1", label="Simulator"),
            ],
            reasons=[],
        )
        with patch("phone_cli.cli.daemon.PhoneCLIDaemon.status", return_value={"status": "stopped"}), \
             patch("phone_cli.ios.runtime.discovery.detect_ios_runtimes", return_value=discovery):
            result = daemon.start(device_type="ios")
        assert result["error_code"] == "RUNTIME_SELECTION_REQUIRED"


def test_daemon_start_ios_explicit_runtime_must_be_available():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        discovery = RuntimeDiscoveryResult(candidates=[], reasons=[])
        with patch("phone_cli.cli.daemon.PhoneCLIDaemon.status", return_value={"status": "stopped"}), \
             patch("phone_cli.ios.runtime.discovery.detect_ios_runtimes", return_value=discovery):
            result = daemon.start(device_type="ios", ios_runtime="simulator")
        assert result["error_code"] == "RUNTIME_NOT_SUPPORTED"


def test_daemon_start_ios_explicit_runtime_with_multiple_targets_requires_device_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        discovery = RuntimeDiscoveryResult(
            candidates=[
                RuntimeCandidate(runtime="simulator", target_id="sim-1", label="Sim 1"),
                RuntimeCandidate(runtime="simulator", target_id="sim-2", label="Sim 2"),
            ],
            reasons=[],
        )
        with patch("phone_cli.cli.daemon.PhoneCLIDaemon.status", return_value={"status": "stopped"}), \
             patch("phone_cli.ios.runtime.discovery.detect_ios_runtimes", return_value=discovery):
            result = daemon.start(device_type="ios", ios_runtime="simulator")
        assert result["error_code"] == "TARGET_NOT_SELECTED"


def test_start_heartbeat_refreshes_companion_health_payload():
    with tempfile.TemporaryDirectory() as tmpdir:
        daemon = PhoneCLIDaemon(home_dir=tmpdir)
        initial_state = {
            "device_type": "adb",
            "device_id": "dev1",
            "companion_status": "ready",
        }
        daemon._write_state(initial_state)

        stop_called = threading.Event()

        def fake_wait(timeout=None):
            if stop_called.is_set():
                return True
            stop_called.set()
            return False

        manager = MagicMock()
        manager.is_port_forwarded.return_value = True
        manager.get_status.return_value = {
            "ready": False,
            "issue_codes": ["HTTP_NOT_READY"],
            "issues": ["Companion HTTP 服务未就绪"],
        }

        with patch.object(daemon._stop_event, "wait", side_effect=fake_wait), \
             patch("phone_cli.adb.list_devices") as mock_devices, \
             patch("phone_cli.adb.companion_manager.CompanionManager", return_value=manager):
            mock_device = MagicMock()
            mock_device.device_id = "dev1"
            mock_devices.return_value = [mock_device]
            daemon._start_heartbeat(initial_state)
            for _ in range(20):
                state = daemon._read_state()
                if "device_status" in state:
                    break
                time.sleep(0.01)

        state = daemon._read_state()
        assert state["device_status"] == "connected"
        assert state["companion_status"] == "degraded"
        assert state["companion_health"]["issue_codes"] == ["HTTP_NOT_READY"]
        assert "companion_last_checked_at" in state
