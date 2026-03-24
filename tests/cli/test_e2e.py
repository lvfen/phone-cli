"""End-to-end tests for phone-cli (requires running emulator)."""

import json
import os
import subprocess
import time

import pytest

PHONE_CLI = "phone-cli"

# Skip entire module if SKIP_E2E is set
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_E2E") == "1",
    reason="E2E tests require connected device (set SKIP_E2E=1 to skip)"
)


def _run_cli(*args, instance: str | None = None) -> dict:
    """Run phone-cli command and parse JSON output."""
    cmd = [PHONE_CLI]
    if instance:
        cmd.extend(["--instance", instance])
    cmd.extend(args)
    result = subprocess.run(
        cmd,
        capture_output=True, text=True, timeout=30,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw_stdout": result.stdout, "raw_stderr": result.stderr, "exit_code": result.returncode}


@pytest.fixture(scope="module", autouse=True)
def start_daemon():
    """Start daemon before tests, stop after."""
    _run_cli("start", "--device-type", "adb", instance="adb")
    time.sleep(2)
    devices_result = _run_cli("devices", instance="adb")
    devices = devices_result.get("data", {}).get("devices", [])
    if devices_result.get("status") != "ok" or not devices:
        _run_cli("stop", instance="adb")
        pytest.skip("E2E tests require a connected ADB device or emulator")
    yield
    _run_cli("stop", instance="adb")


class TestPhoneCLIE2E:

    def test_status_running(self):
        result = _run_cli("status", instance="adb")
        assert result["status"] == "ok"
        assert result["data"]["status"] == "running"

    def test_devices(self):
        result = _run_cli("devices", instance="adb")
        assert result["status"] == "ok"
        assert len(result["data"]["devices"]) > 0

    def test_screenshot(self):
        result = _run_cli("screenshot", "--resize", "720", instance="adb")
        assert result["status"] == "ok"
        assert os.path.exists(result["data"]["path"])
        assert result["data"]["width"] == 720

    def test_get_current_app(self):
        result = _run_cli("get-current-app", instance="adb")
        assert result["status"] == "ok"
        assert "app_name" in result["data"]

    def test_home(self):
        result = _run_cli("home", instance="adb")
        assert result["status"] == "ok"

    def test_tap(self):
        result = _run_cli("tap", "500", "500", instance="adb")
        assert result["status"] == "ok"

    def test_back(self):
        result = _run_cli("back", instance="adb")
        assert result["status"] == "ok"
