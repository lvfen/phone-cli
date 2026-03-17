"""Tests for phone_cli.cli.commands module."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

from phone_cli.cli.commands import dispatch_command, CoordConverter


# ── CoordConverter tests ──────────────────────────────────────────────

def test_coord_converter_center():
    conv = CoordConverter(screen_width=1440, screen_height=3120)
    x, y = conv.to_absolute(500, 500)
    assert x == 720
    assert y == 1561  # int(500 / 999 * 3120) = 1561


def test_coord_converter_origin():
    conv = CoordConverter(screen_width=1080, screen_height=2400)
    x, y = conv.to_absolute(0, 0)
    assert x == 0
    assert y == 0


def test_coord_converter_max():
    conv = CoordConverter(screen_width=1080, screen_height=2400)
    x, y = conv.to_absolute(999, 999)
    assert x == 1079
    assert y == 2399


# ── dispatch_command tests ────────────────────────────────────────────

def test_dispatch_unknown_command():
    result = dispatch_command("nonexistent", {}, MagicMock())
    parsed = json.loads(result)
    assert parsed["status"] == "error"
    assert parsed["error_code"] == "UNKNOWN_COMMAND"


def test_dispatch_status_command():
    mock_daemon = MagicMock()
    mock_daemon.status.return_value = {"status": "running", "device_type": "adb"}
    result = dispatch_command("status", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["data"]["status"] == "running"


def test_dispatch_devices_adb():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "adb"}
    with patch("phone_cli.adb.list_devices") as mock_list:
        mock_dev = MagicMock()
        mock_dev.device_id = "abc123"
        mock_dev.model = "Pixel"
        mock_dev.status = "device"
        mock_list.return_value = [mock_dev]
        result = dispatch_command("devices", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert len(parsed["data"]["devices"]) == 1
    assert parsed["data"]["devices"][0]["device_id"] == "abc123"


def test_dispatch_set_device():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "adb"}
    result = dispatch_command("set_device", {"device_id": "dev1"}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_daemon._write_state.assert_called_once()


def test_dispatch_device_info():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "adb",
        "device_id": "dev1",
        "screen_size": [1080, 2400],
    }
    result = dispatch_command("device_info", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["data"]["device_id"] == "dev1"


def test_dispatch_tap():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "adb",
        "device_id": "dev1",
        "screen_size": [1080, 2400],
    }
    with patch("phone_cli.adb.tap") as mock_tap:
        result = dispatch_command("tap", {"x": 500, "y": 500}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_tap.assert_called_once()


def test_dispatch_swipe():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "adb",
        "device_id": "dev1",
        "screen_size": [1080, 2400],
    }
    with patch("phone_cli.adb.swipe") as mock_swipe:
        result = dispatch_command(
            "swipe",
            {"start_x": 100, "start_y": 100, "end_x": 900, "end_y": 900, "duration_ms": 500},
            mock_daemon,
        )
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_swipe.assert_called_once()


def test_dispatch_type_adb():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "adb",
        "device_id": "dev1",
    }
    with patch("phone_cli.adb.detect_and_set_adb_keyboard", return_value="orig_ime"), \
         patch("phone_cli.adb.clear_text"), \
         patch("phone_cli.adb.type_text"), \
         patch("phone_cli.adb.restore_keyboard") as mock_restore:
        result = dispatch_command("type", {"text": "hello"}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_restore.assert_called_once_with("orig_ime", device_id="dev1")


def test_dispatch_type_hdc():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "hdc",
        "device_id": "dev1",
    }
    with patch("phone_cli.hdc.type_text") as mock_type:
        result = dispatch_command("type", {"text": "hello"}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_type.assert_called_once_with("hello", device_id="dev1")


def test_dispatch_back():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "adb", "device_id": "dev1"}
    with patch("phone_cli.adb.back") as mock_back:
        result = dispatch_command("back", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_back.assert_called_once()


def test_dispatch_home():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "adb", "device_id": "dev1"}
    with patch("phone_cli.adb.home") as mock_home:
        result = dispatch_command("home", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_home.assert_called_once()


def test_dispatch_launch():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "adb", "device_id": "dev1"}
    with patch("phone_cli.adb.launch_app", return_value=True):
        result = dispatch_command("launch", {"app_name": "WeChat"}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"


def test_dispatch_launch_not_found():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "adb", "device_id": "dev1"}
    with patch("phone_cli.adb.launch_app", return_value=False):
        result = dispatch_command("launch", {"app_name": "FakeApp"}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "error"
    assert parsed["error_code"] == "APP_NOT_FOUND"


def test_dispatch_get_current_app():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "adb", "device_id": "dev1"}
    with patch("phone_cli.adb.get_current_app", return_value="WeChat"):
        result = dispatch_command("get_current_app", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["data"]["app_name"] == "WeChat"


def test_dispatch_screenshot():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "adb",
        "device_id": "dev1",
        "screen_size": [1080, 2400],
    }
    mock_daemon.screenshot_dir = tempfile.mkdtemp()
    mock_screenshot = MagicMock()
    mock_screenshot.base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAEUlEQVR4nGP8z4AATEhsPBwAM9EBBzDn4UwAAAAASUVORK5CYII="
    mock_screenshot.width = 1080
    mock_screenshot.height = 2400
    with patch("phone_cli.adb.get_screenshot", return_value=mock_screenshot):
        result = dispatch_command("screenshot", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["data"]["width"] == 4


def test_dispatch_screenshot_with_step():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "adb",
        "device_id": "dev1",
        "screen_size": [1080, 2400],
    }
    mock_daemon.screenshot_dir = tempfile.mkdtemp()
    mock_screenshot = MagicMock()
    mock_screenshot.base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAEUlEQVR4nGP8z4AATEhsPBwAM9EBBzDn4UwAAAAASUVORK5CYII="
    mock_screenshot.width = 1080
    mock_screenshot.height = 2400
    with patch("phone_cli.adb.get_screenshot", return_value=mock_screenshot):
        result = dispatch_command("screenshot", {"step": 3}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert "step_3.png" in parsed["data"]["path"]


def test_dispatch_ui_tree_adb():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "adb", "device_id": "dev1"}
    xml_content = '<?xml version="1.0"?><hierarchy><node bounds="[0,0][100,100]" text="hi" resource-id="id1" class="View" /></hierarchy>'
    with patch("subprocess.run") as mock_run:
        # First call: dump command, second call: pull content
        mock_run.side_effect = [
            MagicMock(returncode=0),  # dump
            MagicMock(returncode=0, stdout=xml_content),  # shell cat
        ]
        result = dispatch_command("ui_tree", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert "elements" in parsed["data"]


def test_dispatch_ui_tree_hdc():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {"device_type": "hdc", "device_id": "dev1"}
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='{"some": "layout"}')
        result = dispatch_command("ui_tree", {}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"


def test_dispatch_clean_screenshots():
    mock_daemon = MagicMock()
    mock_daemon.screenshot_dir = tempfile.mkdtemp()
    # Create a temp file to be cleaned
    test_file = os.path.join(mock_daemon.screenshot_dir, "test.png")
    with open(test_file, "w") as f:
        f.write("x")
    result = dispatch_command("clean_screenshots", {"all": True}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert parsed["data"]["removed"] >= 1


def test_dispatch_log():
    mock_daemon = MagicMock()
    mock_daemon.log_dir = tempfile.mkdtemp()
    log_file = os.path.join(mock_daemon.log_dir, "phone-cli.log")
    with open(log_file, "w") as f:
        f.write("[2026-03-16 10:00:00] [INFO] [test] line1\n")
        f.write("[2026-03-16 10:00:01] [INFO] [test] line2\n")
    result = dispatch_command("log", {"lines": 10}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    assert len(parsed["data"]["entries"]) == 2


def test_dispatch_double_tap():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "adb",
        "device_id": "dev1",
        "screen_size": [1080, 2400],
    }
    with patch("phone_cli.adb.double_tap") as mock_dt:
        result = dispatch_command("double_tap", {"x": 500, "y": 500}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_dt.assert_called_once()


def test_dispatch_long_press():
    mock_daemon = MagicMock()
    mock_daemon._read_state.return_value = {
        "device_type": "adb",
        "device_id": "dev1",
        "screen_size": [1080, 2400],
    }
    with patch("phone_cli.adb.long_press") as mock_lp:
        result = dispatch_command("long_press", {"x": 500, "y": 500}, mock_daemon)
    parsed = json.loads(result)
    assert parsed["status"] == "ok"
    mock_lp.assert_called_once()
